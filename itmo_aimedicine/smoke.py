from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .config import Settings
from .llm import Completion, LLMError, get_provider


class SmokeReply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]
    message: str = Field(min_length=1, max_length=200)


SYSTEM = 'Return JSON with status="ok" and a short message confirming receipt. This is a connectivity test.'
PAYLOAD = {"task": "connectivity_test", "text": "ITMO AIMedicine test; no patient data."}


def run_smoke(settings: Settings, *, transport=None) -> Completion:
    if settings.mode == "mock":
        # Explicit fixture: it is never presented as a model response or live success.
        return Completion(SmokeReply(status="ok", message="Локальный тестовый ответ. Модели не вызывались."),
                          "mock", "fixture-v1", "mock", 0, 0, {})
    if settings.mode != "live":
        raise LLMError("LLM_MODE должен быть mock или live.")
    provider = get_provider(settings)
    if transport is not None:
        provider.transport = transport
    return provider.complete(SYSTEM, PAYLOAD, SmokeReply)
