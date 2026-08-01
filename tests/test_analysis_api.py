import importlib
import sys
from collections.abc import Generator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.dependencies import get_ticket_analysis_service
from app.ai.exceptions import ProviderOutputValidationError, ProviderTimeoutError
from app.ai.schemas import (
    ProviderAnalysis,
    ProviderUsage,
    TicketAnalysisInput,
    TicketAnalysisResult,
    TicketCategory,
    TicketPriority,
)
from app.config import AISettings
from app.database.dependencies import get_db, get_session_factory
from app.main import app
from app.services.ticket_analysis_service import TicketAnalysisService

DATABASE_MODULES = ("app.models.ticket", "app.database.database")


class FakeExternalProvider:
    name = "llm"
    model = "synthetic-model"
    is_external = True

    def __init__(self) -> None:
        self.calls = 0

    async def analyze(self, ticket: TicketAnalysisInput) -> ProviderAnalysis:
        self.calls += 1
        return ProviderAnalysis(
            analysis=TicketAnalysisResult(
                category=TicketCategory.TECHNICAL,
                priority=TicketPriority.MEDIUM,
                summary=f"Synthetic analysis {self.calls}: {ticket.title}",
                suggested_reply="Synthetic draft for operator review.",
                confidence=0.91,
                reasoning_tags=["synthetic_signal"],
            ),
            provider_used=self.name,
            model_used=self.model,
            request_id=f"req_synthetic_{self.calls}",
            usage=ProviderUsage(input_tokens=11, output_tokens=13),
            provider_attempts=1,
            repair_attempts=0,
        )

    async def close(self) -> None:
        return None


class FailingExternalProvider(FakeExternalProvider):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    async def analyze(self, ticket: TicketAnalysisInput) -> ProviderAnalysis:
        del ticket
        self.calls += 1
        if (
            isinstance(self.error, ProviderTimeoutError)
            and self.error.provider_attempts == 0
        ):
            self.error.set_execution_metadata(
                provider_attempts=1,
                repair_attempts=0,
                input_tokens=self.error.input_tokens,
                output_tokens=self.error.output_tokens,
            )
        raise self.error


class MaliciousResultProvider(FakeExternalProvider):
    def __init__(self, field_name: str, value: object) -> None:
        super().__init__()
        self.field_name = field_name
        self.value = value

    async def analyze(self, ticket: TicketAnalysisInput) -> ProviderAnalysis:
        result = await super().analyze(ticket)
        return result.model_copy(update={self.field_name: self.value})


class MaliciousIdentityProvider(FakeExternalProvider):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name


class MaliciousErrorProvider(FakeExternalProvider):
    async def analyze(self, ticket: TicketAnalysisInput) -> ProviderAnalysis:
        del ticket
        error = ProviderTimeoutError()
        error.request_id = "r" * 300
        error.category = "provider_timeout\nSYNTHETIC_LOG_SENTINEL"
        raise error


def clear_database_modules() -> None:
    for module_name in DATABASE_MODULES:
        sys.modules.pop(module_name, None)


def llm_settings(**overrides: object) -> AISettings:
    values: dict[str, object] = {
        "provider": "llm",
        "model": "synthetic-model",
        "api_key": "synthetic-api-key-placeholder",
        "fallback_enabled": False,
    }
    values.update(overrides)
    return AISettings.model_validate(values)


@contextmanager
def api_client(
    monkeypatch: pytest.MonkeyPatch,
    service: TicketAnalysisService,
) -> Generator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("AI_PROVIDER", "deterministic")
    monkeypatch.delenv("AI_API_KEY", raising=False)
    clear_database_modules()
    database_module = importlib.import_module("app.database.database")
    importlib.import_module("app.models.ticket")

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, class_=Session)
    database_module.Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session]:
        with testing_session_local() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: testing_session_local
    app.dependency_overrides[get_ticket_analysis_service] = lambda: service
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        database_module.Base.metadata.drop_all(bind=engine)
        engine.dispose()
        clear_database_modules()


def create_ticket(client: TestClient, description: str = "Synthetic error") -> int:
    response = client.post(
        "/tickets",
        json={"title": "Synthetic ticket", "description": description},
    )
    assert response.status_code == 201
    return int(response.json()["id"])


def test_fake_llm_analysis_and_audit_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeExternalProvider()
    settings = llm_settings()
    service = TicketAnalysisService(provider=provider, settings=settings)

    with api_client(monkeypatch, service) as client:
        ticket_id = create_ticket(client)
        response = client.post(f"/tickets/{ticket_id}/analyze")
        persisted = client.get(f"/tickets/{ticket_id}").json()

    assert response.status_code == 200
    data = response.json()
    assert data["category"] == "technical"
    assert data["confidence"] == 0.91
    assert data["provider_requested"] == "llm"
    assert data["provider_used"] == "llm"
    assert data["fallback_used"] is False
    assert data["model_requested"] == "synthetic-model"
    assert data["model_used"] == "synthetic-model"
    assert data["prompt_version"] == "ticket-analysis-v1"
    assert data["input_tokens"] == 11
    assert data["output_tokens"] == 13
    assert data["provider_attempts"] == 1
    assert data["repair_attempts"] == 0
    assert data["provider_request_id"] == "req_synthetic_1"
    assert persisted["analysis_status"] == "completed"
    assert persisted["analyzed_at"]


def test_successful_fallback_is_transparent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FailingExternalProvider(ProviderTimeoutError("req_failed"))
    settings = llm_settings(fallback_enabled=True)
    service = TicketAnalysisService(provider=provider, settings=settings)

    with api_client(monkeypatch, service) as client:
        ticket_id = create_ticket(client, "Payment failed, please help.")
        response = client.post(f"/tickets/{ticket_id}/analyze")

    assert response.status_code == 200
    data = response.json()
    assert data["provider_requested"] == "llm"
    assert data["provider_used"] == "deterministic"
    assert data["fallback_used"] is True
    assert data["analysis_status"] == "completed_with_fallback"
    assert data["error_category"] == "provider_timeout"
    assert data["provider_request_id"] == "req_failed"
    assert data["model_requested"] == "synthetic-model"
    assert data["model_used"] is None
    assert data["provider_attempts"] == 1


def test_fallback_preserves_known_primary_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = ProviderTimeoutError("req_failed")
    error.set_execution_metadata(
        provider_attempts=2,
        repair_attempts=1,
        input_tokens=21,
        output_tokens=34,
    )
    provider = FailingExternalProvider(error)
    service = TicketAnalysisService(
        provider=provider,
        settings=llm_settings(fallback_enabled=True),
    )

    with api_client(monkeypatch, service) as client:
        ticket_id = create_ticket(client)
        response = client.post(f"/tickets/{ticket_id}/analyze")

    data = response.json()
    assert response.status_code == 200
    assert data["input_tokens"] == 21
    assert data["output_tokens"] == 34
    assert data["provider_attempts"] == 2
    assert data["repair_attempts"] == 1


def test_fallback_disabled_returns_controlled_error_and_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FailingExternalProvider(ProviderTimeoutError("req_failed"))
    settings = llm_settings(fallback_enabled=False)
    service = TicketAnalysisService(provider=provider, settings=settings)

    with api_client(monkeypatch, service) as client:
        ticket_id = create_ticket(client)
        response = client.post(f"/tickets/{ticket_id}/analyze")
        persisted = client.get(f"/tickets/{ticket_id}").json()

    assert response.status_code == 504
    assert response.json() == {
        "error": {
            "code": "provider_timeout",
            "message": "The configured analysis provider timed out.",
            "request_id": "req_failed",
        }
    }
    assert persisted["analysis_status"] == "failed"
    assert persisted["provider_used"] is None
    assert persisted["error_category"] == "provider_timeout"


def test_oversized_input_returns_controlled_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeExternalProvider()
    settings = llm_settings(max_input_chars=256)
    service = TicketAnalysisService(provider=provider, settings=settings)

    with api_client(monkeypatch, service) as client:
        ticket_id = create_ticket(client, "x" * 300)
        response = client.post(f"/tickets/{ticket_id}/analyze")

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "input_too_large"
    assert provider.calls == 0


def test_repeated_analysis_is_explicit_and_updates_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeExternalProvider()
    service = TicketAnalysisService(provider=provider, settings=llm_settings())

    with api_client(monkeypatch, service) as client:
        ticket_id = create_ticket(client)
        first = client.post(f"/tickets/{ticket_id}/analyze")
        second = client.post(f"/tickets/{ticket_id}/analyze")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["summary"].startswith("Synthetic analysis 1")
    assert second.json()["summary"].startswith("Synthetic analysis 2")
    assert provider.calls == 2


def test_provider_raw_output_and_api_key_never_reach_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_output = "SYNTHETIC_RAW_PROVIDER_RESPONSE"
    api_key = "synthetic-api-key-placeholder"
    provider = FailingExternalProvider(ProviderOutputValidationError("req_invalid"))
    service = TicketAnalysisService(provider=provider, settings=llm_settings())

    with api_client(monkeypatch, service) as client:
        ticket_id = create_ticket(client)
        response = client.post(f"/tickets/{ticket_id}/analyze")
        persisted_response = client.get(f"/tickets/{ticket_id}")

    serialized_response = response.text
    serialized_persisted = persisted_response.text
    assert response.status_code == 502
    assert raw_output not in serialized_response
    assert raw_output not in serialized_persisted
    assert api_key not in serialized_response
    assert api_key not in serialized_persisted
    assert "UNTRUSTED_TICKET_JSON" not in serialized_persisted
    assert "stack" not in serialized_response.lower()


@pytest.mark.parametrize(
    "provider_name",
    [
        "x" * 100,
        "llm\nSYNTHETIC_LOG_SENTINEL",
        "llm\u202econfusable",
    ],
)
def test_invalid_requested_provider_metadata_is_controlled_and_not_persisted(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    provider_name: str,
) -> None:
    provider = MaliciousIdentityProvider(provider_name)
    service = TicketAnalysisService(provider=provider, settings=llm_settings())

    with api_client(monkeypatch, service) as client:
        ticket_id = create_ticket(client)
        response = client.post(f"/tickets/{ticket_id}/analyze")
        persisted = client.get(f"/tickets/{ticket_id}").json()

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_provider_metadata"
    assert persisted["provider_requested"] is None
    assert persisted["provider_used"] is None
    assert provider_name not in caplog.text


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("request_id", "r" * 300),
        ("model_used", "synthetic\nmodel"),
        ("provider_used", "llm\u202econfusable"),
    ],
)
def test_invalid_result_metadata_is_controlled_and_not_persisted(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    field_name: str,
    value: str,
) -> None:
    provider = MaliciousResultProvider(field_name, value)
    service = TicketAnalysisService(provider=provider, settings=llm_settings())

    with api_client(monkeypatch, service) as client:
        ticket_id = create_ticket(client)
        response = client.post(f"/tickets/{ticket_id}/analyze")
        persisted = client.get(f"/tickets/{ticket_id}").json()

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_provider_metadata"
    assert persisted["provider_used"] is None
    assert persisted["model_used"] is None
    assert value not in caplog.text


def test_invalid_prompt_metadata_is_controlled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeExternalProvider()
    settings = llm_settings()
    settings.prompt_version = "invalid\nprompt"
    service = TicketAnalysisService(provider=provider, settings=settings)

    with api_client(monkeypatch, service) as client:
        ticket_id = create_ticket(client)
        response = client.post(f"/tickets/{ticket_id}/analyze")
        persisted = client.get(f"/tickets/{ticket_id}").json()

    assert response.status_code == 502
    assert persisted["prompt_version"] is None
    assert provider.calls == 0


def test_invalid_error_metadata_is_not_logged_or_persisted(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = MaliciousErrorProvider()
    service = TicketAnalysisService(provider=provider, settings=llm_settings())

    with api_client(monkeypatch, service) as client:
        ticket_id = create_ticket(client)
        response = client.post(f"/tickets/{ticket_id}/analyze")
        persisted = client.get(f"/tickets/{ticket_id}").json()

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_provider_metadata"
    assert persisted["analysis_status"] is None
    assert "SYNTHETIC_LOG_SENTINEL" not in caplog.text
