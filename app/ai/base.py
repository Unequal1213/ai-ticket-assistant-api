from typing import Protocol, runtime_checkable

from app.ai.schemas import ProviderAnalysis, TicketAnalysisInput


@runtime_checkable
class TicketAnalysisProvider(Protocol):
    """Contract implemented by offline and external ticket analyzers."""

    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str | None: ...

    @property
    def is_external(self) -> bool: ...

    async def analyze(self, ticket: TicketAnalysisInput) -> ProviderAnalysis: ...

    async def close(self) -> None: ...
