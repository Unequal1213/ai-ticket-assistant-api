from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

MAX_TICKET_DESCRIPTION_CHARS = 20_000


class TicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=MAX_TICKET_DESCRIPTION_CHARS)


class TicketUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_TICKET_DESCRIPTION_CHARS,
    )
    status: str | None = Field(default=None, min_length=1, max_length=50)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    priority: str | None = Field(default=None, min_length=1, max_length=50)
    summary: str | None = Field(default=None, min_length=1)
    suggested_reply: str | None = Field(default=None, min_length=1)


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    status: str
    category: str | None = None
    priority: str | None = None
    summary: str | None = None
    suggested_reply: str | None = None
    confidence: float | None = None
    reasoning_tags: list[str] | None = None
    analysis_status: str | None = None
    provider_requested: str | None = None
    provider_used: str | None = None
    model_requested: str | None = None
    model_used: str | None = None
    prompt_version: str | None = None
    fallback_used: bool | None = None
    input_char_count: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_attempts: int | None = None
    repair_attempts: int | None = None
    latency_ms: int | None = None
    error_category: str | None = None
    provider_request_id: str | None = None
    analyzed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AnalysisErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class AnalysisErrorResponse(BaseModel):
    error: AnalysisErrorDetail
