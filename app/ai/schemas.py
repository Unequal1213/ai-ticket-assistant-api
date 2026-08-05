from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TicketCategory(StrEnum):
    AUTHENTICATION = "authentication"
    BILLING = "billing"
    TECHNICAL = "technical"
    CUSTOMER_REQUEST = "customer_request"
    DELIVERY = "delivery"
    RETURN = "return"
    ORDER_CHANGE = "order_change"
    GENERAL = "general"


class TicketPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


ReasoningTag = Annotated[
    str,
    Field(min_length=1, max_length=32, pattern=r"^[a-z0-9][a-z0-9_-]*$"),
]

ProviderIdentity = Annotated[
    str,
    Field(min_length=1, max_length=32, pattern=r"^[a-z][a-z0-9_-]*$"),
]
ModelIdentifier = Annotated[
    str,
    Field(
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$",
    ),
]
RequestIdentifier = Annotated[
    str,
    Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9_.:-]+$"),
]
AuditIdentifier = Annotated[
    str,
    Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_-]*$"),
]


class TicketAnalysisResult(BaseModel):
    """Validated, client-safe analysis. It intentionally excludes chain-of-thought."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    category: TicketCategory
    priority: TicketPriority
    summary: str = Field(min_length=1, max_length=500)
    suggested_reply: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_tags: list[ReasoningTag] = Field(max_length=6)

    @field_validator("summary", "suggested_reply")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if any(ord(character) < 32 and character not in "\n\t" for character in value):
            raise ValueError("control characters are not allowed")
        return value


class TicketAnalysisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)


class ProviderUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class ProviderAnalysis(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        revalidate_instances="always",
    )

    analysis: TicketAnalysisResult
    provider_used: ProviderIdentity
    model_used: ModelIdentifier | None = None
    request_id: RequestIdentifier | None = None
    usage: ProviderUsage = Field(default_factory=ProviderUsage)
    provider_attempts: int = Field(default=0, ge=0, le=100)
    repair_attempts: int = Field(default=0, ge=0, le=100)


class ProviderRequestMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    provider_requested: ProviderIdentity
    model_requested: ModelIdentifier | None
    prompt_version: AuditIdentifier


class ProviderFailureMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    error_category: AuditIdentifier
    request_id: RequestIdentifier | None = None


def build_provider_ticket_analysis_schema() -> dict[str, Any]:
    """Build the deliberately small JSON Schema sent to the provider.

    Full length, range, pattern, and extra-field validation remains local in
    ``TicketAnalysisResult``.
    """

    return {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": [category.value for category in TicketCategory],
            },
            "priority": {
                "type": "string",
                "enum": [priority.value for priority in TicketPriority],
            },
            "summary": {"type": "string"},
            "suggested_reply": {"type": "string"},
            "confidence": {"type": "number"},
            "reasoning_tags": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": [
            "category",
            "priority",
            "summary",
            "suggested_reply",
            "confidence",
            "reasoning_tags",
        ],
        "additionalProperties": False,
    }
