from pathlib import Path
import os

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_MISTRAL_URL = "https://api.mistral.ai/v1"
FREETHEAI_URL = "https://api.freetheai.org/v1"
ROUTER_URL = "https://router-ai-pe.ai360.group"
ROUTER_MODELS = ("gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.6-flash",
                 "gemini-3.8-flash", "gemma-4-26b-a4b-it", "gemma-4-31b-it")
FREE_GLM_MODELS = ("fta/zai/glm-5.3", "fta/zai/glm-5.3-flash")


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)
    provider: str = "mistral"
    mode: str = "mock"
    api_key: SecretStr = SecretStr("")
    model: str = Field(default="ministral-8b-2512", min_length=1)
    base_url: str = OFFICIAL_MISTRAL_URL
    temperature: float = Field(default=0.1, ge=0, le=1)
    max_tokens: int = Field(default=512, ge=1, le=65536)
    max_attempts: int = Field(default=3, ge=1, le=3)
    timeout_seconds: float = Field(default=30, gt=0, le=120)
    poll_interval_seconds: float = Field(default=10, ge=10, le=60)
    job_timeout_seconds: float = Field(default=600, ge=10, le=3600)

    @classmethod
    def from_env(cls, *, provider=None, env_file=None):
        # Parse dotenv as data: never execute a supplied shell file or interpolate it.
        config = dict(dotenv_values(ROOT / ".env", interpolate=False))
        if env_file is not None:
            config.update(dotenv_values(env_file, interpolate=False))
        config.update(os.environ)
        get = config.get
        provider = provider or get("LLM_PROVIDER", "mistral")
        if provider == "router":
            key = get("ANTEI_ROUTER_API_KEY", "")
            key_file = get("ANTEI_ROUTER_KEY_FILE", "")
            if not key and key_file:
                try:
                    key = Path(key_file).expanduser().read_text(encoding="utf-8").strip()
                except (OSError, UnicodeError):
                    raise ValueError("Не удалось прочитать локальный файл ключа Router.") from None
            return cls(
                provider="router", mode=get("LLM_MODE", "mock"), api_key=key,
                model=get("ANTEI_ROUTER_MODEL", "gemini-3.5-flash-lite"),
                base_url=ROUTER_URL, max_tokens=get("ANTEI_ROUTER_MAX_TOKENS", "4096"),
                max_attempts=1, timeout_seconds=30,
                job_timeout_seconds=get("ANTEI_ROUTER_JOB_TIMEOUT", "600"),
            )
        if provider == "glm":
            return cls(
                provider="glm", mode=get("LLM_MODE", "mock"),
                api_key=get("FREETHEAI_API_KEY", ""),
                model=get("FREETHEAI_GLM_MODEL", FREE_GLM_MODELS[0]),
                base_url=get("FREETHEAI_BASE_URL", FREETHEAI_URL).rstrip("/"),
                temperature=0, max_tokens=1024, max_attempts=1, timeout_seconds=120,
            )
        return cls(
            provider=provider,
            mode=get("LLM_MODE", "mock"),
            api_key=get("MISTRAL_API_KEY", ""),
            model=get("MISTRAL_MODEL", "ministral-8b-2512"),
            base_url=get("MISTRAL_BASE_URL", OFFICIAL_MISTRAL_URL).rstrip("/"),
            temperature=get("MISTRAL_TEMPERATURE", "0.1"),
            max_tokens=get("MISTRAL_MAX_TOKENS", "512"),
            max_attempts=get("MISTRAL_MAX_ATTEMPTS", "3"),
            timeout_seconds=get("MISTRAL_TIMEOUT_SECONDS", "30"),
        )
