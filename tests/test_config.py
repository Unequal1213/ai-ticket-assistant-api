import pytest
from pydantic import ValidationError

from app.config import OFFICIAL_OPENAI_BASE_URL, AIProviderName, AISettings


def test_default_ai_mode_is_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "AI_PROVIDER",
        "AI_MODEL",
        "AI_API_KEY",
        "AI_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = AISettings.from_env()

    assert settings.provider is AIProviderName.DETERMINISTIC
    assert settings.api_key is None
    assert settings.model is None
    assert settings.effective_base_url == OFFICIAL_OPENAI_BASE_URL


def test_llm_mode_requires_api_key() -> None:
    with pytest.raises(ValidationError, match="AI_API_KEY"):
        AISettings(provider="llm", model="synthetic-model", api_key=None)


@pytest.mark.parametrize("model", [None, "", "   "])
def test_llm_mode_requires_explicit_model(model: str | None) -> None:
    with pytest.raises(ValidationError, match="AI_MODEL"):
        AISettings(
            provider="llm",
            model=model,
            api_key="synthetic-secret-placeholder",
        )


def test_api_key_is_masked_in_repr() -> None:
    settings = AISettings(
        provider="llm",
        model="synthetic-model",
        api_key="synthetic-secret-placeholder",
    )

    assert "synthetic-secret-placeholder" not in repr(settings)


@pytest.mark.parametrize(
    "base_url",
    [
        "http://provider.invalid/v1",
        "https://user:password@provider.invalid/v1",
    ],
)
def test_external_base_url_rejects_insecure_values(base_url: str) -> None:
    with pytest.raises(ValidationError, match="AI_BASE_URL"):
        AISettings(
            provider="llm",
            model="synthetic-model",
            api_key="synthetic-secret-placeholder",
            base_url=base_url,
        )


def test_llm_with_explicit_model_and_key_is_valid() -> None:
    settings = AISettings(
        provider="llm",
        model=" synthetic-model ",
        api_key="synthetic-secret-placeholder",
    )

    assert settings.model == "synthetic-model"


def test_insecure_loopback_requires_explicit_test_only_flag() -> None:
    with pytest.raises(ValidationError, match="test-only"):
        AISettings(
            provider="llm",
            model="synthetic-model",
            api_key="synthetic-secret-placeholder",
            base_url="http://127.0.0.1:43199/v1",
        )

    settings = AISettings(
        provider="llm",
        model="synthetic-model",
        api_key="synthetic-secret-placeholder",
        base_url="http://127.0.0.1:43199/v1",
        allow_insecure_local_base_url=True,
    )
    assert settings.effective_base_url == "http://127.0.0.1:43199/v1"


def test_configuration_error_does_not_expose_key() -> None:
    secret = "SYNTHETIC_SECRET_SENTINEL_90210"
    with pytest.raises(ValidationError) as exc_info:
        AISettings(
            provider="llm",
            model=None,
            api_key=secret,
        )

    assert secret not in str(exc_info.value)
