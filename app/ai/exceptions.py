class TicketAnalysisError(Exception):
    """Base error safe to translate into a controlled API response."""

    def __init__(
        self,
        *,
        category: str,
        public_message: str,
        http_status: int,
        retryable: bool = False,
        request_id: str | None = None,
        provider_attempts: int = 0,
        repair_attempts: int = 0,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        super().__init__(public_message)
        self.category = category
        self.public_message = public_message
        self.http_status = http_status
        self.retryable = retryable
        self.request_id = request_id
        self.provider_attempts = provider_attempts
        self.repair_attempts = repair_attempts
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def set_execution_metadata(
        self,
        *,
        provider_attempts: int,
        repair_attempts: int,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None:
        self.provider_attempts = provider_attempts
        self.repair_attempts = repair_attempts
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class ProviderError(TicketAnalysisError):
    pass


class ProviderTimeoutError(ProviderError):
    def __init__(self, request_id: str | None = None) -> None:
        super().__init__(
            category="provider_timeout",
            public_message="The configured analysis provider timed out.",
            http_status=504,
            retryable=True,
            request_id=request_id,
        )


class ProviderRateLimitError(ProviderError):
    def __init__(self, request_id: str | None = None) -> None:
        super().__init__(
            category="provider_rate_limit",
            public_message="The configured analysis provider is temporarily busy.",
            http_status=503,
            retryable=True,
            request_id=request_id,
        )


class ProviderUnavailableError(ProviderError):
    def __init__(self, request_id: str | None = None) -> None:
        super().__init__(
            category="provider_unavailable",
            public_message="The configured analysis provider is unavailable.",
            http_status=503,
            retryable=True,
            request_id=request_id,
        )


class ProviderAuthenticationError(ProviderError):
    def __init__(self, request_id: str | None = None) -> None:
        super().__init__(
            category="provider_authentication",
            public_message="The configured analysis provider is unavailable.",
            http_status=503,
            retryable=False,
            request_id=request_id,
        )


class ProviderRequestError(ProviderError):
    def __init__(self, request_id: str | None = None) -> None:
        super().__init__(
            category="provider_request",
            public_message="The analysis provider rejected the configured request.",
            http_status=502,
            retryable=False,
            request_id=request_id,
        )


class ProviderOutputValidationError(ProviderError):
    def __init__(self, request_id: str | None = None) -> None:
        super().__init__(
            category="invalid_provider_output",
            public_message=(
                "The analysis provider returned an invalid structured result."
            ),
            http_status=502,
            retryable=False,
            request_id=request_id,
        )


class ProviderMetadataError(ProviderError):
    def __init__(self) -> None:
        super().__init__(
            category="invalid_provider_metadata",
            public_message="The analysis provider returned invalid metadata.",
            http_status=502,
            retryable=False,
        )


class DailyQuotaExceededError(ProviderError):
    def __init__(self) -> None:
        super().__init__(
            category="daily_quota_exceeded",
            public_message=(
                "The daily external analysis request limit has been reached."
            ),
            http_status=429,
            retryable=False,
        )


class InputTooLargeError(TicketAnalysisError):
    def __init__(self, max_chars: int) -> None:
        super().__init__(
            category="input_too_large",
            public_message=(
                f"Ticket text exceeds the configured limit of {max_chars} characters."
            ),
            http_status=413,
            retryable=False,
        )


class TicketChangedError(TicketAnalysisError):
    def __init__(self) -> None:
        super().__init__(
            category="ticket_changed_during_analysis",
            public_message=(
                "The ticket changed while analysis was running; analyze it again."
            ),
            http_status=409,
            retryable=False,
        )
