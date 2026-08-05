import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import openai
from openai import AsyncOpenAI
from pydantic import ValidationError

from app.ai.exceptions import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderMetadataError,
    ProviderOutputValidationError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.ai.limits import DailyRequestQuota
from app.ai.pii import prepare_external_text
from app.ai.prompts.ticket_analysis_v1 import DEVELOPER_PROMPT, build_ticket_prompt
from app.ai.retry import exponential_backoff_seconds
from app.ai.schemas import (
    ProviderAnalysis,
    ProviderUsage,
    TicketAnalysisInput,
    TicketAnalysisResult,
    build_provider_ticket_analysis_schema,
)
from app.config import AISettings

logger = logging.getLogger(__name__)

SleepFunction = Callable[[float], Awaitable[None]]


@dataclass
class _ExecutionState:
    provider_attempts: int = 0
    repair_attempts: int = 0
    transient_retries: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    has_input_tokens: bool = False
    has_output_tokens: bool = False

    def add_response_usage(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        response_input = getattr(usage, "input_tokens", None)
        response_output = getattr(usage, "output_tokens", None)
        if isinstance(response_input, int) and response_input >= 0:
            self.input_tokens += response_input
            self.has_input_tokens = True
        if isinstance(response_output, int) and response_output >= 0:
            self.output_tokens += response_output
            self.has_output_tokens = True

    def usage(self) -> ProviderUsage:
        return ProviderUsage(
            input_tokens=self.input_tokens if self.has_input_tokens else None,
            output_tokens=self.output_tokens if self.has_output_tokens else None,
        )

    def attach(self, error: ProviderError) -> ProviderError:
        usage = self.usage()
        error.set_execution_metadata(
            provider_attempts=self.provider_attempts,
            repair_attempts=self.repair_attempts,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
        return error


class OpenAILLMTicketAnalysisProvider:
    """External LLM provider using the official async OpenAI Responses API."""

    def __init__(
        self,
        settings: AISettings,
        *,
        client: AsyncOpenAI | None = None,
        sleep: SleepFunction = asyncio.sleep,
        quota: DailyRequestQuota | None = None,
    ) -> None:
        if settings.api_key is None or settings.model is None:
            raise ValueError("An API key and model are required for the LLM provider")
        self._settings = settings
        self._sleep = sleep
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
        self._quota = quota or DailyRequestQuota(settings.daily_request_limit)
        self._owns_client = client is None
        self._client = client or AsyncOpenAI(
            api_key=settings.api_key.get_secret_value(),
            base_url=settings.effective_base_url,
            timeout=settings.timeout_seconds,
            max_retries=0,
        )

    @property
    def name(self) -> str:
        return "llm"

    @property
    def model(self) -> str:
        model = self._settings.model
        if model is None:  # Protected by validated configuration and constructor.
            raise RuntimeError("LLM model is not configured")
        return model

    @property
    def is_external(self) -> bool:
        return True

    async def analyze(self, ticket: TicketAnalysisInput) -> ProviderAnalysis:
        redacted_title = prepare_external_text(ticket.title)
        redacted_description = prepare_external_text(ticket.description)
        started = perf_counter()
        state = _ExecutionState()

        async with self._semaphore:
            # One accepted user analysis consumes one daily operation. Waiting for
            # the semaphore, including cancellation while waiting, consumes none.
            await self._quota.consume()
            try:
                analysis, response = await self._run_bounded_operation(
                    title=redacted_title,
                    description=redacted_description,
                    state=state,
                )
            except asyncio.CancelledError:
                raise
            except ProviderError as error:
                raise state.attach(error) from error.__cause__

        usage = state.usage()
        request_id = _safe_request_id(getattr(response, "_request_id", None))
        raw_response_model = getattr(response, "model", None)
        response_model = _safe_model_identifier(raw_response_model)
        if raw_response_model is not None and response_model is None:
            error = state.attach(ProviderMetadataError())
            raise error
        latency_ms = round((perf_counter() - started) * 1000)
        logger.info(
            "ticket analysis completed provider=llm model=%s request_id=%s "
            "latency_ms=%s provider_attempts=%s repair_attempts=%s",
            self.model,
            request_id,
            latency_ms,
            state.provider_attempts,
            state.repair_attempts,
        )
        return ProviderAnalysis(
            analysis=analysis,
            provider_used=self.name,
            model_used=response_model or self.model,
            request_id=request_id,
            usage=usage,
            provider_attempts=state.provider_attempts,
            repair_attempts=state.repair_attempts,
        )

    async def _run_bounded_operation(
        self,
        *,
        title: str,
        description: str,
        state: _ExecutionState,
    ) -> tuple[TicketAnalysisResult, Any]:
        total_attempt_budget = (
            1 + self._settings.max_retries + self._settings.max_repairs
        )
        repair = False
        repair_started = False

        while state.provider_attempts < total_attempt_budget:
            state.provider_attempts += 1
            if repair:
                state.repair_attempts += 1
            try:
                response = await self._request_once(
                    title=title,
                    description=description,
                    repair=repair,
                )
            except asyncio.CancelledError:
                raise
            except ProviderError as error:
                can_retry = (
                    error.retryable
                    and state.transient_retries < self._settings.max_retries
                    and state.provider_attempts < total_attempt_budget
                )
                if not can_retry:
                    logger.warning(
                        "ticket analysis failed provider=llm model=%s category=%s "
                        "request_id=%s provider_attempts=%s repair_attempts=%s",
                        self.model,
                        error.category,
                        error.request_id,
                        state.provider_attempts,
                        state.repair_attempts,
                    )
                    raise
                delay = exponential_backoff_seconds(state.transient_retries)
                state.transient_retries += 1
                await self._sleep(delay)
                continue

            state.add_response_usage(response)
            try:
                return self._validate_response(response), response
            except ProviderOutputValidationError as error:
                can_repair = (
                    not repair_started
                    and self._settings.max_repairs > 0
                    and state.provider_attempts < total_attempt_budget
                )
                if not can_repair:
                    raise error
                repair = True
                repair_started = True

        raise ProviderRequestError()

    async def _request_once(
        self,
        *,
        title: str,
        description: str,
        repair: bool,
    ) -> Any:
        try:
            async with asyncio.timeout(self._settings.timeout_seconds):
                return await self._client.responses.create(
                    model=self.model,
                    instructions=DEVELOPER_PROMPT,
                    input=build_ticket_prompt(
                        title,
                        description,
                        repair=repair,
                    ),
                    max_output_tokens=self._settings.max_output_tokens,
                    store=False,
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "ticket_analysis",
                            "description": "Validated support copilot result",
                            "schema": build_provider_ticket_analysis_schema(),
                            "strict": True,
                        }
                    },
                )
        except asyncio.CancelledError:
            raise
        except (TimeoutError, openai.APITimeoutError) as exc:
            raise ProviderTimeoutError(_request_id(exc)) from exc
        except openai.AuthenticationError as exc:
            raise ProviderAuthenticationError(_request_id(exc)) from exc
        except openai.RateLimitError as exc:
            raise ProviderRateLimitError(_request_id(exc)) from exc
        except openai.APIConnectionError as exc:
            raise ProviderUnavailableError(_request_id(exc)) from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderUnavailableError(_request_id(exc)) from exc
            raise ProviderRequestError(_request_id(exc)) from exc

    @staticmethod
    def _validate_response(response: Any) -> TicketAnalysisResult:
        request_id = _safe_request_id(getattr(response, "_request_id", None))
        try:
            output_text = response.output_text
            if not output_text:
                raise ValueError("empty model output")
            return TicketAnalysisResult.model_validate_json(output_text)
        except (AttributeError, TypeError, ValueError, ValidationError) as exc:
            raise ProviderOutputValidationError(request_id) from exc

    async def close(self) -> None:
        if self._owns_client:
            await self._client.close()


def _request_id(exc: Exception) -> str | None:
    return _safe_request_id(getattr(exc, "request_id", None))


def _safe_request_id(value: object) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,255}", value):
        return value
    return None


def _safe_model_identifier(value: object) -> str | None:
    if isinstance(value, str) and re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,254}",
        value,
    ):
        return value
    return None
