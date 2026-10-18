from pathlib import Path
import os

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_MISTRAL_URL = "https://api.mistral.ai/v1"


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
    def from_env(cls):
        load_dotenv(ROOT / ".env", override=False)
        return cls(
            provider=os.getenv("LLM_PROVIDER", "mistral"),
            mode=os.getenv("LLM_MODE", "mock"),
            api_key=os.getenv("MISTRAL_API_KEY", ""),
            model=os.getenv("MISTRAL_MODEL", "ministral-8b-2512"),
            base_url=os.getenv("MISTRAL_BASE_URL", OFFICIAL_MISTRAL_URL).rstrip("/"),
            temperature=os.getenv("MISTRAL_TEMPERATURE", "0.1"),
            max_tokens=os.getenv("MISTRAL_MAX_TOKENS", "512"),
            max_attempts=os.getenv("MISTRAL_MAX_ATTEMPTS", "3"),
            timeout_seconds=os.getenv("MISTRAL_TIMEOUT_SECONDS", "30"),
        )
