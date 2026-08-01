from typing import TypeVar

from app.ai.schemas import (
    ProviderAnalysis,
    TicketAnalysisInput,
    TicketAnalysisResult,
    TicketCategory,
    TicketPriority,
)

RuleValue = TypeVar("RuleValue", bound=str)

CATEGORY_RULES: tuple[tuple[TicketCategory, tuple[str, ...]], ...] = (
    (TicketCategory.AUTHENTICATION, ("login", "password", "account", "auth")),
    (TicketCategory.BILLING, ("payment", "invoice", "billing")),
    (TicketCategory.TECHNICAL, ("bug", "error", "crash", "fail")),
    (TicketCategory.CUSTOMER_REQUEST, ("refund", "cancel")),
    (TicketCategory.DELIVERY, ("delivery", "shipment", "courier")),
    (TicketCategory.RETURN, ("return", "send back")),
    (TicketCategory.ORDER_CHANGE, ("change order", "modify order")),
)

PRIORITY_RULES: tuple[tuple[TicketPriority, tuple[str, ...]], ...] = (
    (TicketPriority.HIGH, ("urgent", "down", "outage", "critical")),
    (TicketPriority.MEDIUM, ("please", "help", "problem", "error")),
)


def find_first_match(
    text: str,
    rules: tuple[tuple[RuleValue, tuple[str, ...]], ...],
    default: RuleValue,
) -> tuple[RuleValue, bool]:
    for value, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return value, True
    return default, False


def build_summary(title: str, description: str) -> str:
    clean_description = " ".join(description.split())
    if len(clean_description) > 140:
        clean_description = f"{clean_description[:137].rstrip()}..."
    return f"{title}: {clean_description}"


def build_suggested_reply(
    category: TicketCategory,
    priority: TicketPriority,
) -> str:
    return (
        f"Thanks for contacting support. We classified this as a {priority.value} "
        f"priority {category.value} issue and will review it shortly."
    )


def analyze_deterministically(
    title: str,
    description: str,
) -> TicketAnalysisResult:
    text = f"{title} {description}".lower()
    category, category_matched = find_first_match(
        text,
        CATEGORY_RULES,
        TicketCategory.GENERAL,
    )
    priority, priority_matched = find_first_match(
        text,
        PRIORITY_RULES,
        TicketPriority.LOW,
    )
    tags = []
    if category_matched:
        tags.append("category_keyword")
    if priority_matched:
        tags.append("priority_keyword")
    if not tags:
        tags.append("default_rules")

    return TicketAnalysisResult(
        category=category,
        priority=priority,
        summary=build_summary(title=title, description=description),
        suggested_reply=build_suggested_reply(
            category=category,
            priority=priority,
        ),
        confidence=0.85 if category_matched else 0.5,
        reasoning_tags=tags,
    )


class DeterministicTicketAnalysisProvider:
    """Offline rule provider. It is deterministic and is not an LLM."""

    @property
    def name(self) -> str:
        return "deterministic"

    @property
    def model(self) -> None:
        return None

    @property
    def is_external(self) -> bool:
        return False

    async def analyze(self, ticket: TicketAnalysisInput) -> ProviderAnalysis:
        return ProviderAnalysis(
            analysis=analyze_deterministically(ticket.title, ticket.description),
            provider_used=self.name,
            model_used=None,
            provider_attempts=0,
            repair_attempts=0,
        )

    async def close(self) -> None:
        return None
