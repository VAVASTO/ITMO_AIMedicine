"""ANTEI job API: one submission, bounded polling, no hidden model fallback."""
import json
import re
import time

import httpx

from .config import ROUTER_MODELS, ROUTER_URL, Settings
from .llm import Completion, LLMError


def response_schema(schema: dict, *, array_bounds: bool = True) -> dict:
    """Convert Pydantic JSON Schema to the documented Gemini schema subset."""
    definitions = schema.get("$defs", {})

    def visit(node):
        if "$ref" in node:
            ref = node["$ref"]
            if not ref.startswith("#/$defs/"):
                raise LLMError("Неподдерживаемая ссылка в схеме результата.")
            return visit(definitions[ref.split("/")[-1]])
        if "anyOf" in node:
            options = [x for x in node["anyOf"] if x.get("type") != "null"]
            if len(options) != 1:
                raise LLMError("Схема Router допускает один тип и null.")
            return {**visit(options[0]), "nullable": True}
        result = {}
        for k in ("description", "enum", "required", "minimum", "maximum", "minItems", "maxItems", "format"):
            if not array_bounds and k in ("minItems", "maxItems"):
                continue
            if k in node:
                result[k] = node[k]
        if "type" in node:
            result["type"] = node["type"].upper()
        if "const" in node:
            result["enum"] = [node["const"]]
        if "properties" in node:
            result["properties"] = {k: visit(v) for k, v in node["properties"].items()}
            result["propertyOrdering"] = list(node["properties"])
        if "items" in node:
            result["items"] = visit(node["items"])
        return result

    return visit(schema)


def normalize_json_wrapper(text):
    """Remove only a whole-response Markdown wrapper; never extract an inner object."""
    value=text.strip()
    if value.startswith('```json\n') and value.endswith('\n```'):
        return value[len('```json\n'):-len('\n```')], True
    if value.startswith('```\n') and value.endswith('\n```'):
        return value[len('```\n'):-len('\n```')], True
    if not value.startswith('```') and value.endswith('\n```'):
        return value[:-len('\n```')], True
    return value, False


class RouterClient:
    def __init__(self, settings: Settings, *, transport=None, sleep=time.sleep, clock=time.monotonic, on_submit=None,
                 normalize_wrapper=False, schema_array_bounds=True):
        if settings.base_url != ROUTER_URL or settings.model not in ROUTER_MODELS:
            raise LLMError("Неизвестный адрес или модель ANTEI Router.")
        self.settings, self.transport, self.sleep, self.clock = settings, transport, sleep, clock
        self.on_submit = on_submit
        # Experiments keep strict decoding by default. The UI may tolerate only
        # a Markdown fence, and records that cleanup without changing JSON data.
        self.normalize_wrapper = normalize_wrapper
        # Some serving backends reject bounded arrays in complex output schemas.
        # Opting out affects the provider schema only; Pydantic still checks bounds.
        self.schema_array_bounds = schema_array_bounds

    def _request(self, client, method, path, **kwargs):
        try:
            response = client.request(method, ROUTER_URL + path, **kwargs)
        except httpx.HTTPError:
            raise LLMError("Сетевая ошибка Router. Повторная отправка задания не выполнена.") from None
        if response.status_code not in (200, 202):
            raise LLMError(f"Router HTTP {response.status_code}. Проверьте доступ и квоту; задание не повторено.")
        try:
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError
            return body
        except ValueError:
            raise LLMError("Router вернул некорректный ответ API.") from None

    def complete(self, system, payload, schema):
        key = self.settings.api_key.get_secret_value()
        if not key or not key.startswith("rtr_") or any(c.isspace() for c in key):
            raise LLMError("ANTEI_ROUTER_API_KEY не задан или имеет неверный формат.")
        request = {
            "model": self.settings.model, "fallback": False,
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}],
            "config": {"responseMimeType": "application/json", "responseSchema": response_schema(schema.model_json_schema(), array_bounds=self.schema_array_bounds),
                       "maxOutputTokens": self.settings.max_tokens, "thinkingLevel": "minimal"},
        }
        started = self.clock()
        with httpx.Client(transport=self.transport, timeout=self.settings.timeout_seconds,
                          follow_redirects=False, headers={"Authorization": "Bearer " + key}) as client:
            submitted = self._request(client, "POST", "/api/v1/jobs", json=request)
            job_id = submitted.get("id")
            if not isinstance(job_id, str) or not re.fullmatch(r"job_[A-Za-z0-9_-]+", job_id):
                raise LLMError("Router не вернул допустимый id задания; повтор не выполнен.")
            if self.on_submit:
                self.on_submit(job_id)
            while self.clock() - started < self.settings.job_timeout_seconds:
                self.sleep(self.settings.poll_interval_seconds)
                try:
                    job = self._request(client, "GET", "/api/v1/jobs/" + job_id)
                except LLMError as error:
                    raise LLMError(f"{error} id={job_id}") from None
                if job.get("id") != job_id or job.get("model") != self.settings.model:
                    raise LLMError("Router вернул другое задание или модель.")
                state = job.get("status")
                if state in ("queued", "running"):
                    continue
                if state in ("blocked", "failed"):
                    raise LLMError(f"Задание Router завершилось со статусом {state}; повтор не выполнен. id={job_id}")
                if state != "done":
                    raise LLMError("Router вернул неизвестный статус задания.")
                try:
                    if job.get("fallback"):
                        raise ValueError("Unexpected fallback")
                    result = job["result"]
                    if result.get("finishReason") != "STOP":
                        raise ValueError("Incomplete output")
                    text = result['text']
                    normalized = False
                    if self.normalize_wrapper:
                        text, normalized = normalize_json_wrapper(text)
                    answer = schema.model_validate_json(text)
                    usage = {k: int(result.get("usage", {}).get(k, 0)) for k in ("input", "output", "thoughts", "total")}
                    if any(x < 0 for x in usage.values()):
                        raise ValueError("Invalid usage")
                except (ValueError, KeyError, TypeError, AttributeError):
                    raise LLMError(f"Ответ Router не прошёл проверку схемы или полноты. id={job_id}") from None
                return Completion(answer, "router", self.settings.model, "live", 1,
                                  round((self.clock() - started) * 1000), usage, job_id,
                                  'markdown_fence_removed' if normalized else None)
        raise LLMError(f"Истекло время ожидания Router; задание не отправлено повторно. id={job_id}")
