import os
from enum import StrEnum
from urllib.parse import urlparse

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator


class AIProviderName(StrEnum):
    DETERMINISTIC = "deterministic"
    LLM = "llm"


OFFICIAL_OPENAI_BASE_URL = "https://api.openai.com/v1"
MAX_PROVIDER_INPUT_CHARS = 20_255


class AISettings(BaseModel):
    provider: AIProviderName = AIProviderName.DETERMINISTIC
    model: str | None = Field(default=None, max_length=255)
    api_key: SecretStr | None = None
    base_url: str | None = None
    allow_insecure_local_base_url: bool = Field(default=False, exclude=True)
    timeout_seconds: float = Field(default=15.0, gt=0.0, le=120.0)
    max_retries: int = Field(default=2, ge=0, le=5)
    max_repairs: int = Field(default=1, ge=0, le=1)
    max_input_chars: int = Field(
        default=8000,
        ge=256,
        le=MAX_PROVIDER_INPUT_CHARS,
    )
    max_output_tokens: int = Field(default=800, ge=64, le=8000)
    fallback_enabled: bool = True
    daily_request_limit: int = Field(default=100, ge=0, le=1_000_000)
    max_concurrent_requests: int = Field(default=4, ge=1, le=100)
    prompt_version: str = "ticket-analysis-v1"

    @classmethod
    def from_env(cls) -> "AISettings":
        values: dict[str, str] = {}
        environment_fields = {
            "provider": "AI_PROVIDER",
            "model": "AI_MODEL",
            "api_key": "AI_API_KEY",
            "base_url": "AI_BASE_URL",
            "timeout_seconds": "AI_TIMEOUT_SECONDS",
            "max_retries": "AI_MAX_RETRIES",
            "max_repairs": "AI_MAX_REPAIRS",
            "max_input_chars": "AI_MAX_INPUT_CHARS",
            "max_output_tokens": "AI_MAX_OUTPUT_TOKENS",
            "fallback_enabled": "AI_FALLBACK_ENABLED",
            "daily_request_limit": "AI_DAILY_REQUEST_LIMIT",
            "max_concurrent_requests": "AI_MAX_CONCURRENT_REQUESTS",
            "prompt_version": "AI_PROMPT_VERSION",
        }
        for field_name, environment_name in environment_fields.items():
            value = os.getenv(environment_name)
            if value is not None and value != "":
                values[field_name] = value
        return cls.model_validate(values)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("AI_BASE_URL must use http or https")
        if parsed.username or parsed.password:
            raise ValueError("AI_BASE_URL must not contain credentials")
        return value.rstrip("/")

    @field_validator("model")
    @classmethod
    def validate_model_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        allowed = set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:/@+-"
        )
        if any(character not in allowed for character in stripped):
            raise ValueError("AI_MODEL contains invalid characters")
        return stripped

    @model_validator(mode="after")
    def validate_llm_configuration(self) -> "AISettings":
        if self.prompt_version != "ticket-analysis-v1":
            raise ValueError("Unsupported AI_PROMPT_VERSION")
        if self.base_url is not None:
            parsed = urlparse(self.base_url)
            is_loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            if parsed.scheme != "https" and not (
                self.allow_insecure_local_base_url and is_loopback
            ):
                raise ValueError(
                    "AI_BASE_URL must use https; insecure loopback is test-only"
                )
        if self.provider is AIProviderName.LLM:
            if self.api_key is None or not self.api_key.get_secret_value().strip():
                raise ValueError("AI_API_KEY is required when AI_PROVIDER=llm")
            if self.model is None:
                raise ValueError("AI_MODEL is required when AI_PROVIDER=llm")
        return self

    @property
    def effective_base_url(self) -> str:
        """Return an explicit validated endpoint so SDK env cannot override it."""

        return self.base_url or OFFICIAL_OPENAI_BASE_URL
