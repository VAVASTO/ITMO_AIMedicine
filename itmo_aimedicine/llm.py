"""Transport approach adapted from VAVASTO/AIMedicine, commit e2f4877.

Mistral is the initial provider because Google AI Studio could not be set up:
it redirected to available-regions. Gemini/Gemma remain deferred, untested.
A future Gemini adapter implements StructuredProvider without changing callers.
"""
from dataclasses import dataclass
import json
import time
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel

from .config import OFFICIAL_MISTRAL_URL, Settings

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Safe to show: no credentials, provider response body, or patient payload."""


@dataclass(frozen=True)
class Completion:
    result: BaseModel
    provider: str
    model: str
    mode: str
    attempts: int
    latency_ms: int
    usage: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "result": self.result.model_dump()}


class StructuredProvider(Protocol):
    def complete(self, system: str, payload: dict, schema: type[T]) -> Completion: ...


class MistralClient:
    def __init__(self, settings: Settings, *, transport=None, sleep=time.sleep):
        if settings.base_url != OFFICIAL_MISTRAL_URL:
            raise LLMError("Разрешён только официальный HTTPS API Mistral.")
        self.settings = settings
        self.transport = transport
        self.sleep = sleep

    def complete(self, system: str, payload: dict, schema: type[T]) -> Completion:
        if not self.settings.api_key.get_secret_value():
            raise LLMError("MISTRAL_API_KEY не задан. Добавьте ключ в локальный .env.")
        request = {
            "model": self.settings.model,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": schema.__name__, "schema": schema.model_json_schema(), "strict": True,
            }},
        }
        started = time.monotonic()
        # Redirects are disabled so the credential never follows another host.
        with httpx.Client(timeout=httpx.Timeout(self.settings.timeout_seconds, connect=10),
                          transport=self.transport, follow_redirects=False) as client:
            for attempt in range(1, self.settings.max_attempts + 1):
                try:
                    response = client.post(self.settings.base_url + "/chat/completions",
                                           json=request, headers={"Authorization": "Bearer " +
                                               self.settings.api_key.get_secret_value()})
                except httpx.HTTPError:
                    # Retrying ambiguous transport failures can duplicate billed requests.
                    raise LLMError("Сетевая ошибка Mistral; автоматический повтор не выполнен.") from None
                status = response.status_code
                if status == 429 and response.headers.get("x-ratelimit-limit-req-minute") == "0":
                    raise LLMError("Квота выбранной модели равна нулю. Выберите доступную модель.")
                if status in (429, 502, 503, 504) and attempt < self.settings.max_attempts:
                    try:
                        delay = min(30.0, max(1.0, float(response.headers.get("retry-after", 2 ** attempt))))
                    except ValueError:
                        delay = 2 ** attempt
                    self.sleep(delay)
                    continue
                if status != 200:
                    raise LLMError(f"Mistral HTTP {status}. Проверьте ключ, модель и квоту.")
                try:
                    body = response.json()
                    choice = body["choices"][0]
                    if choice["finish_reason"] != "stop":
                        raise LLMError("Mistral не завершил ответ; частичный результат отклонён.")
                    content = choice["message"]["content"]
                    if isinstance(content, list):
                        if any(chunk.get("type") != "text" for chunk in content):
                            raise ValueError("Unexpected response chunk")
                        content = "".join(chunk["text"] for chunk in content)
                    result = schema.model_validate_json(content)
                    actual_model = body["model"]
                    if not isinstance(actual_model, str) or not actual_model:
                        raise ValueError("Missing model")
                    usage = {key: int(body.get("usage", {}).get(key, 0))
                             for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
                except (ValueError, KeyError, TypeError, IndexError, AttributeError):
                    raise LLMError("Mistral вернул ответ, не соответствующий схеме.") from None
                return Completion(result, "mistral", actual_model, "live", attempt,
                                  round((time.monotonic() - started) * 1000), usage)
        raise LLMError("Лимит попыток исчерпан.")


def get_provider(settings: Settings) -> StructuredProvider:
    if settings.provider != "mistral":
        # Gemini needs its own validated adapter, not just a different Mistral URL.
        raise LLMError("Провайдер ещё не реализован. Сейчас доступен только mistral; Gemini отложен.")
    return MistralClient(settings)
