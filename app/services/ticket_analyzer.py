from dataclasses import dataclass


@dataclass(frozen=True)
class TicketAnalysis:
    category: str
    priority: str
    summary: str
    suggested_reply: str


CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("authentication", ("login", "password", "account", "auth")),
    ("billing", ("payment", "invoice", "billing")),
    ("technical", ("bug", "error", "crash", "fail")),
    ("customer_request", ("refund", "cancel")),
)

PRIORITY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("high", ("urgent", "down", "outage", "critical")),
    ("medium", ("please", "help", "problem", "error")),
)


def analyze_ticket(title: str, description: str) -> TicketAnalysis:
    text = f"{title} {description}".lower()
    category = find_first_match(text, CATEGORY_RULES, default="general")
    priority = find_first_match(text, PRIORITY_RULES, default="low")

    return TicketAnalysis(
        category=category,
        priority=priority,
        summary=build_summary(title=title, description=description),
        suggested_reply=build_suggested_reply(category=category, priority=priority),
    )


def find_first_match(
    text: str,
    rules: tuple[tuple[str, tuple[str, ...]], ...],
    default: str,
) -> str:
    for value, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return value
    return default


def build_summary(title: str, description: str) -> str:
    clean_description = " ".join(description.split())
    if len(clean_description) > 140:
        clean_description = f"{clean_description[:137].rstrip()}..."
    return f"{title}: {clean_description}"


def build_suggested_reply(category: str, priority: str) -> str:
    return (
        f"Thanks for contacting support. We classified this as a {priority} "
        f"priority {category} issue and will review it shortly."
    )
