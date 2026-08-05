from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from time import perf_counter

from anyio import to_thread
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.base import TicketAnalysisProvider
from app.ai.deterministic_provider import DeterministicTicketAnalysisProvider
from app.ai.exceptions import (
    InputTooLargeError,
    ProviderError,
    ProviderMetadataError,
    TicketAnalysisError,
    TicketChangedError,
)
from app.ai.schemas import (
    ProviderAnalysis,
    ProviderFailureMetadata,
    ProviderRequestMetadata,
    ProviderUsage,
    TicketAnalysisInput,
)
from app.config import AISettings
from app.database.dependencies import SessionFactory

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TicketSnapshot:
    id: int
    title: str
    description: str
    updated_at: datetime


class TicketAnalysisService:
    def __init__(
        self,
        *,
        provider: TicketAnalysisProvider,
        settings: AISettings,
        fallback_provider: TicketAnalysisProvider | None = None,
    ) -> None:
        self._provider = provider
        self._settings = settings
        self._fallback_provider = fallback_provider or (
            DeterministicTicketAnalysisProvider() if provider.is_external else None
        )

    async def analyze_existing_ticket(
        self,
        *,
        session_factory: SessionFactory,
        ticket_id: int,
    ):
        snapshot = await to_thread.run_sync(
            partial(self._load_snapshot, session_factory, ticket_id)
        )
        if snapshot is None:
            return None

        started = perf_counter()
        input_char_count = len(snapshot.title) + len(snapshot.description)
        try:
            request_metadata = self._validate_request_metadata(self._provider)
        except ProviderMetadataError as error:
            await self._save_failure_async(
                session_factory=session_factory,
                snapshot=snapshot,
                error=error,
                request_metadata=None,
                input_char_count=input_char_count,
                latency_ms=self._latency_ms(started),
            )
            raise

        analysis_input = TicketAnalysisInput(
            title=snapshot.title,
            description=snapshot.description,
        )
        if input_char_count > self._settings.max_input_chars:
            error = InputTooLargeError(self._settings.max_input_chars)
            await self._save_failure_async(
                session_factory=session_factory,
                snapshot=snapshot,
                error=error,
                request_metadata=request_metadata,
                input_char_count=input_char_count,
                latency_ms=self._latency_ms(started),
            )
            raise error

        try:
            raw_result = await self._provider.analyze(analysis_input)
            provider_result = self._validate_provider_result(
                raw_result,
                expected_provider=request_metadata.provider_requested,
            )
        except ProviderError as raw_error:
            error = self._validate_provider_error(raw_error)
            if self._can_fallback(error):
                return await self._run_fallback(
                    session_factory=session_factory,
                    snapshot=snapshot,
                    analysis_input=analysis_input,
                    request_metadata=request_metadata,
                    primary_error=error,
                    input_char_count=input_char_count,
                    started=started,
                )
            await self._save_failure_async(
                session_factory=session_factory,
                snapshot=snapshot,
                error=error,
                request_metadata=request_metadata,
                input_char_count=input_char_count,
                latency_ms=self._latency_ms(started),
            )
            raise error from raw_error

        ticket = await to_thread.run_sync(
            partial(
                self._save_success,
                session_factory,
                snapshot,
                request_metadata,
                provider_result,
                False,
                input_char_count,
                self._latency_ms(started),
                None,
                None,
                None,
            )
        )
        logger.info(
            "ticket analysis saved ticket_id=%s provider_requested=%s "
            "provider_used=%s fallback_used=false",
            snapshot.id,
            request_metadata.provider_requested,
            provider_result.provider_used,
        )
        return ticket

    def _can_fallback(self, error: ProviderError) -> bool:
        return (
            not isinstance(error, ProviderMetadataError)
            and self._settings.fallback_enabled
            and self._provider.is_external
            and self._fallback_provider is not None
        )

    async def _run_fallback(
        self,
        *,
        session_factory: SessionFactory,
        snapshot: TicketSnapshot,
        analysis_input: TicketAnalysisInput,
        request_metadata: ProviderRequestMetadata,
        primary_error: ProviderError,
        input_char_count: int,
        started: float,
    ):
        fallback_provider = self._fallback_provider
        if fallback_provider is None:
            raise RuntimeError("fallback provider is not configured")
        try:
            fallback_metadata = self._validate_request_metadata(fallback_provider)
            raw_result = await fallback_provider.analyze(analysis_input)
            fallback_result = self._validate_provider_result(
                raw_result,
                expected_provider=fallback_metadata.provider_requested,
            )
        except ProviderError as raw_fallback_error:
            fallback_error = self._validate_provider_error(raw_fallback_error)
            await self._save_failure_async(
                session_factory=session_factory,
                snapshot=snapshot,
                error=fallback_error,
                request_metadata=request_metadata,
                input_char_count=input_char_count,
                latency_ms=self._latency_ms(started),
            )
            raise fallback_error from raw_fallback_error

        primary_usage = ProviderUsage(
            input_tokens=primary_error.input_tokens,
            output_tokens=primary_error.output_tokens,
        )
        ticket = await to_thread.run_sync(
            partial(
                self._save_success,
                session_factory,
                snapshot,
                request_metadata,
                fallback_result,
                True,
                input_char_count,
                self._latency_ms(started),
                primary_error.category,
                primary_error.request_id,
                primary_usage,
                primary_error.provider_attempts,
                primary_error.repair_attempts,
            )
        )
        logger.warning(
            "ticket analysis fallback ticket_id=%s provider_requested=%s "
            "provider_used=%s category=%s",
            snapshot.id,
            request_metadata.provider_requested,
            fallback_result.provider_used,
            primary_error.category,
        )
        return ticket

    async def _save_failure_async(
        self,
        *,
        session_factory: SessionFactory,
        snapshot: TicketSnapshot,
        error: TicketAnalysisError,
        request_metadata: ProviderRequestMetadata | None,
        input_char_count: int,
        latency_ms: int,
    ) -> None:
        await to_thread.run_sync(
            partial(
                self._save_failure,
                session_factory,
                snapshot,
                error,
                request_metadata,
                input_char_count,
                latency_ms,
            )
        )
        logger.warning(
            "ticket analysis audit saved ticket_id=%s category=%s",
            snapshot.id,
            error.category,
        )

    @staticmethod
    def _load_snapshot(
        session_factory: SessionFactory,
        ticket_id: int,
    ) -> TicketSnapshot | None:
        from app.models.ticket import Ticket

        with session_factory() as db:
            ticket = db.get(Ticket, ticket_id)
            if ticket is None:
                return None
            return TicketSnapshot(
                id=ticket.id,
                title=ticket.title,
                description=ticket.description,
                updated_at=ticket.updated_at,
            )

    @staticmethod
    def _save_success(
        session_factory: SessionFactory,
        snapshot: TicketSnapshot,
        request_metadata: ProviderRequestMetadata,
        result: ProviderAnalysis,
        fallback_used: bool,
        input_char_count: int,
        latency_ms: int,
        error_category: str | None,
        failed_request_id: str | None,
        primary_usage: ProviderUsage | None,
        primary_provider_attempts: int = 0,
        primary_repair_attempts: int = 0,
    ):
        with session_factory() as db:
            ticket = TicketAnalysisService._current_ticket(db, snapshot)
            if ticket is None:
                return None
            analysis = result.analysis
            ticket.category = analysis.category.value
            ticket.priority = analysis.priority.value
            ticket.summary = analysis.summary
            ticket.suggested_reply = analysis.suggested_reply
            ticket.confidence = analysis.confidence
            ticket.reasoning_tags = analysis.reasoning_tags
            ticket.analysis_status = (
                "completed_with_fallback" if fallback_used else "completed"
            )
            ticket.provider_requested = request_metadata.provider_requested
            ticket.provider_used = result.provider_used
            ticket.model_requested = request_metadata.model_requested
            ticket.model_used = result.model_used
            ticket.prompt_version = request_metadata.prompt_version
            ticket.fallback_used = fallback_used
            ticket.input_char_count = input_char_count
            ticket.input_tokens = TicketAnalysisService._sum_optional(
                primary_usage.input_tokens if primary_usage else None,
                result.usage.input_tokens,
            )
            ticket.output_tokens = TicketAnalysisService._sum_optional(
                primary_usage.output_tokens if primary_usage else None,
                result.usage.output_tokens,
            )
            ticket.provider_attempts = (
                primary_provider_attempts + result.provider_attempts
            )
            ticket.repair_attempts = primary_repair_attempts + result.repair_attempts
            ticket.latency_ms = latency_ms
            ticket.error_category = error_category
            ticket.provider_request_id = result.request_id or failed_request_id
            ticket.analyzed_at = datetime.now(UTC)
            return TicketAnalysisService._commit_and_detach(db, ticket)

    @staticmethod
    def _save_failure(
        session_factory: SessionFactory,
        snapshot: TicketSnapshot,
        error: TicketAnalysisError,
        request_metadata: ProviderRequestMetadata | None,
        input_char_count: int,
        latency_ms: int,
    ):
        with session_factory() as db:
            ticket = TicketAnalysisService._current_ticket(db, snapshot)
            if ticket is None:
                return None
            ticket.analysis_status = "failed"
            ticket.provider_requested = (
                request_metadata.provider_requested if request_metadata else None
            )
            ticket.provider_used = None
            ticket.model_requested = (
                request_metadata.model_requested if request_metadata else None
            )
            ticket.model_used = None
            ticket.prompt_version = (
                request_metadata.prompt_version if request_metadata else None
            )
            ticket.fallback_used = False
            ticket.input_char_count = input_char_count
            ticket.input_tokens = error.input_tokens
            ticket.output_tokens = error.output_tokens
            ticket.provider_attempts = error.provider_attempts
            ticket.repair_attempts = error.repair_attempts
            ticket.latency_ms = latency_ms
            ticket.error_category = error.category
            ticket.provider_request_id = error.request_id
            ticket.analyzed_at = datetime.now(UTC)
            return TicketAnalysisService._commit_and_detach(db, ticket)

    @staticmethod
    def _current_ticket(db: Session, snapshot: TicketSnapshot):
        from app.models.ticket import Ticket

        ticket = db.get(Ticket, snapshot.id)
        if ticket is None:
            return None
        if ticket.updated_at != snapshot.updated_at:
            raise TicketChangedError
        return ticket

    @staticmethod
    def _commit_and_detach(db: Session, ticket):
        try:
            db.commit()
            db.refresh(ticket)
            db.expunge(ticket)
            return ticket
        except Exception:
            db.rollback()
            raise

    def _validate_request_metadata(
        self,
        provider: TicketAnalysisProvider,
    ) -> ProviderRequestMetadata:
        try:
            if not isinstance(provider.is_external, bool):
                raise TypeError("provider external flag must be boolean")
            metadata = ProviderRequestMetadata.model_validate(
                {
                    "provider_requested": provider.name,
                    "model_requested": provider.model,
                    "prompt_version": self._settings.prompt_version,
                },
                strict=True,
            )
            if provider.is_external and metadata.model_requested is None:
                raise ValueError("external provider requires a model")
            if (
                provider is self._provider
                and provider.is_external
                and metadata.model_requested != self._settings.model
            ):
                raise ValueError("provider model differs from configured model")
            return metadata
        except (AttributeError, TypeError, ValueError, ValidationError) as error:
            raise ProviderMetadataError from error

    @staticmethod
    def _validate_provider_result(
        result: object,
        *,
        expected_provider: str,
    ) -> ProviderAnalysis:
        try:
            validated = ProviderAnalysis.model_validate(result, strict=True)
        except (TypeError, ValidationError) as error:
            raise ProviderMetadataError from error
        if validated.provider_used != expected_provider:
            raise ProviderMetadataError
        return validated

    @staticmethod
    def _validate_provider_error(error: ProviderError) -> ProviderError:
        try:
            ProviderFailureMetadata.model_validate(
                {
                    "error_category": error.category,
                    "request_id": error.request_id,
                },
                strict=True,
            )
            if not all(
                isinstance(value, int) and 0 <= value <= 100
                for value in (error.provider_attempts, error.repair_attempts)
            ):
                raise ValueError("invalid provider attempt metadata")
            ProviderUsage(
                input_tokens=error.input_tokens,
                output_tokens=error.output_tokens,
            )
        except (
            AttributeError,
            TypeError,
            ValueError,
            ValidationError,
        ) as validation_error:
            raise ProviderMetadataError from validation_error
        return error

    @staticmethod
    def _sum_optional(first: int | None, second: int | None) -> int | None:
        if first is None and second is None:
            return None
        return (first or 0) + (second or 0)

    @staticmethod
    def _latency_ms(started: float) -> int:
        return max(0, round((perf_counter() - started) * 1000))

    async def close(self) -> None:
        await self._provider.close()
        if self._fallback_provider is not None:
            await self._fallback_provider.close()
