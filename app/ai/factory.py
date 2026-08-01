from app.ai.base import TicketAnalysisProvider
from app.ai.deterministic_provider import DeterministicTicketAnalysisProvider
from app.ai.llm_provider import OpenAILLMTicketAnalysisProvider
from app.config import AIProviderName, AISettings
from app.services.ticket_analysis_service import TicketAnalysisService


def create_analysis_provider(settings: AISettings) -> TicketAnalysisProvider:
    if settings.provider is AIProviderName.DETERMINISTIC:
        return DeterministicTicketAnalysisProvider()
    if settings.provider is AIProviderName.LLM:
        return OpenAILLMTicketAnalysisProvider(settings)
    raise ValueError(f"Unsupported analysis provider: {settings.provider}")


def create_ticket_analysis_service(settings: AISettings) -> TicketAnalysisService:
    return TicketAnalysisService(
        provider=create_analysis_provider(settings),
        settings=settings,
    )
