from pathlib import Path
import os

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_MISTRAL_URL = "https://api.mistral.ai/v1"
FREETHEAI_URL = "https://api.freetheai.org/v1"
FREE_GLM_MODELS = ("fta/zai/glm-5.3", "fta/zai/glm-5.3-flash")


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)
    provider: str = "mistral"
    mode: str = "mock"
    api_key: SecretStr = SecretStr("")
    model: str = Field(default="ministral-8b-2512", min_length=1)
    base_url: str = OFFICIAL_MISTRAL_URL
    temperature: float = Field(default=0.1, ge=0, le=1)
    max_tokens: int = Field(default=512, ge=1, le=3200)
    max_attempts: int = Field(default=3, ge=1, le=3)
    timeout_seconds: float = Field(default=30, gt=0, le=120)

    @classmethod
    def from_env(cls, *, provider=None, env_file=None):
        # Parse dotenv as data: never execute a supplied shell file or interpolate it.
        config = dict(dotenv_values(ROOT / ".env", interpolate=False))
        if env_file is not None:
            config.update(dotenv_values(env_file, interpolate=False))
        config.update(os.environ)
        get = config.get
        provider = provider or get("LLM_PROVIDER", "mistral")
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
