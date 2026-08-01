from dataclasses import dataclass

from app.ai.deterministic_provider import analyze_deterministically


@dataclass(frozen=True)
class TicketAnalysis:
    category: str
    priority: str
    summary: str
    suggested_reply: str


def analyze_ticket(title: str, description: str) -> TicketAnalysis:
    """Backward-compatible wrapper around the offline deterministic provider."""

    result = analyze_deterministically(title=title, description=description)
    return TicketAnalysis(
        category=result.category.value,
        priority=result.priority.value,
        summary=result.summary,
        suggested_reply=result.suggested_reply,
    )
