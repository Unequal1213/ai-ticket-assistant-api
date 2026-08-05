import threading
from pathlib import Path

import pytest
from anyio import to_thread
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai.exceptions import ProviderTimeoutError, TicketChangedError
from app.ai.schemas import (
    ProviderAnalysis,
    ProviderUsage,
    TicketAnalysisInput,
    TicketAnalysisResult,
    TicketCategory,
    TicketPriority,
)
from app.config import AISettings
from app.database.database import Base
from app.models.ticket import Ticket
from app.services.ticket_analysis_service import TicketAnalysisService


class TrackingSession(Session):
    active_sessions = 0
    operation_threads: set[int] = set()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tracking_closed = False
        type(self).active_sessions += 1

    def get(self, *args, **kwargs):
        type(self).operation_threads.add(threading.get_ident())
        return super().get(*args, **kwargs)

    def commit(self) -> None:
        type(self).operation_threads.add(threading.get_ident())
        return super().commit()

    def close(self) -> None:
        if not self._tracking_closed:
            type(self).active_sessions -= 1
            self._tracking_closed = True
        super().close()


class ObservingProvider:
    name = "llm"
    model = "synthetic-model"
    is_external = True

    def __init__(self) -> None:
        self.calls = 0
        self.saw_open_session = False

    async def analyze(self, ticket: TicketAnalysisInput) -> ProviderAnalysis:
        self.calls += 1
        self.saw_open_session = TrackingSession.active_sessions != 0
        return provider_result(ticket, self.calls)

    async def close(self) -> None:
        return None


class FailingProvider(ObservingProvider):
    async def analyze(self, ticket: TicketAnalysisInput) -> ProviderAnalysis:
        del ticket
        self.calls += 1
        self.saw_open_session = TrackingSession.active_sessions != 0
        error = ProviderTimeoutError("req_synthetic_failure")
        error.set_execution_metadata(
            provider_attempts=1,
            repair_attempts=0,
            input_tokens=None,
            output_tokens=None,
        )
        raise error


class DeletingProvider(ObservingProvider):
    def __init__(self, session_factory, ticket_id: int) -> None:
        super().__init__()
        self._session_factory = session_factory
        self._ticket_id = ticket_id

    async def analyze(self, ticket: TicketAnalysisInput) -> ProviderAnalysis:
        result = await super().analyze(ticket)
        await to_thread.run_sync(self._delete_ticket)
        return result

    def _delete_ticket(self) -> None:
        with self._session_factory() as db:
            ticket = db.get(Ticket, self._ticket_id)
            assert ticket is not None
            db.delete(ticket)
            db.commit()


class UpdatingProvider(ObservingProvider):
    def __init__(self, session_factory, ticket_id: int) -> None:
        super().__init__()
        self._session_factory = session_factory
        self._ticket_id = ticket_id

    async def analyze(self, ticket: TicketAnalysisInput) -> ProviderAnalysis:
        result = await super().analyze(ticket)
        await to_thread.run_sync(self._update_ticket)
        return result

    def _update_ticket(self) -> None:
        with self._session_factory() as db:
            ticket = db.get(Ticket, self._ticket_id)
            assert ticket is not None
            ticket.title = "Changed while provider was running"
            db.commit()


def provider_result(ticket: TicketAnalysisInput, call: int) -> ProviderAnalysis:
    return ProviderAnalysis(
        analysis=TicketAnalysisResult(
            category=TicketCategory.TECHNICAL,
            priority=TicketPriority.MEDIUM,
            summary=f"Synthetic result {call}: {ticket.title}",
            suggested_reply="Synthetic draft for operator review.",
            confidence=0.8,
            reasoning_tags=["synthetic_signal"],
        ),
        provider_used="llm",
        model_used="synthetic-model",
        request_id=f"req_synthetic_{call}",
        usage=ProviderUsage(input_tokens=10, output_tokens=12),
        provider_attempts=1,
        repair_attempts=0,
    )


def make_service(provider) -> TicketAnalysisService:
    settings = AISettings(
        provider="llm",
        model="synthetic-model",
        api_key="synthetic-api-key-placeholder",
        fallback_enabled=False,
    )
    return TicketAnalysisService(provider=provider, settings=settings)


@pytest.fixture()
def database(tmp_path: Path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'service.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=TrackingSession)
    with factory() as db:
        ticket = Ticket(title="Synthetic ticket", description="Synthetic error")
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        ticket_id = ticket.id
    TrackingSession.operation_threads.clear()
    try:
        yield factory, ticket_id
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
        TrackingSession.active_sessions = 0
        TrackingSession.operation_threads.clear()


@pytest.mark.anyio
async def test_db_units_close_before_provider_and_run_outside_event_loop(
    database,
) -> None:
    factory, ticket_id = database
    provider = ObservingProvider()
    service = make_service(provider)
    event_loop_thread = threading.get_ident()

    ticket = await service.analyze_existing_ticket(
        session_factory=factory,
        ticket_id=ticket_id,
    )

    assert ticket is not None
    assert ticket.analysis_status == "completed"
    assert provider.saw_open_session is False
    assert TrackingSession.active_sessions == 0
    assert TrackingSession.operation_threads
    assert event_loop_thread not in TrackingSession.operation_threads


@pytest.mark.anyio
async def test_provider_failure_saves_only_failure_audit(database) -> None:
    factory, ticket_id = database
    provider = FailingProvider()
    service = make_service(provider)

    with pytest.raises(ProviderTimeoutError):
        await service.analyze_existing_ticket(
            session_factory=factory,
            ticket_id=ticket_id,
        )

    with factory() as db:
        ticket = db.get(Ticket, ticket_id)
        assert ticket is not None
        assert ticket.category is None
        assert ticket.summary is None
        assert ticket.analysis_status == "failed"
        assert ticket.provider_attempts == 1
    assert provider.saw_open_session is False


@pytest.mark.anyio
async def test_ticket_deleted_between_read_and_save_returns_none(database) -> None:
    factory, ticket_id = database
    provider = DeletingProvider(factory, ticket_id)
    service = make_service(provider)

    ticket = await service.analyze_existing_ticket(
        session_factory=factory,
        ticket_id=ticket_id,
    )

    assert ticket is None
    assert TrackingSession.active_sessions == 0


@pytest.mark.anyio
async def test_ticket_changed_between_read_and_save_returns_conflict(database) -> None:
    factory, ticket_id = database
    provider = UpdatingProvider(factory, ticket_id)
    service = make_service(provider)

    with pytest.raises(TicketChangedError):
        await service.analyze_existing_ticket(
            session_factory=factory,
            ticket_id=ticket_id,
        )

    with factory() as db:
        ticket = db.get(Ticket, ticket_id)
        assert ticket is not None
        assert ticket.title == "Changed while provider was running"
        assert ticket.analysis_status is None


@pytest.mark.anyio
async def test_repeated_analysis_persists_consistent_latest_result(database) -> None:
    factory, ticket_id = database
    provider = ObservingProvider()
    service = make_service(provider)

    first = await service.analyze_existing_ticket(
        session_factory=factory,
        ticket_id=ticket_id,
    )
    second = await service.analyze_existing_ticket(
        session_factory=factory,
        ticket_id=ticket_id,
    )

    assert first is not None
    assert second is not None
    assert first.summary.startswith("Synthetic result 1")
    assert second.summary.startswith("Synthetic result 2")
    assert provider.calls == 2
