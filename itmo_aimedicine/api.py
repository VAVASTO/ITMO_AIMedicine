from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from .config import Settings
from .llm import LLMError
from .smoke import run_smoke

app = FastAPI(title="ITMO AIMedicine: подготовка", version="0.1.0")


def settings():
    try:
        return Settings.from_env()
    except ValidationError:
        raise HTTPException(503, "Некорректные настройки приложения.") from None


@app.get("/api/status")
def status():
    config = settings()
    return {"provider": config.provider, "model": config.model, "mode": config.mode,
            "key_configured": bool(config.api_key.get_secret_value()),
            "gemini_status": "deferred_region_access",
            "stage": "1: подготовка окружения"}


@app.post("/api/smoke")
def smoke():
    try:
        return run_smoke(settings()).as_dict()
    except LLMError as error:
        raise HTTPException(502, str(error)) from None
