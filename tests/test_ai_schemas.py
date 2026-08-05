import pytest
from pydantic import ValidationError

from app.ai.base import TicketAnalysisProvider
from app.ai.deterministic_provider import DeterministicTicketAnalysisProvider
from app.ai.schemas import (
    ProviderAnalysis,
    TicketAnalysisInput,
    TicketAnalysisResult,
    TicketCategory,
    TicketPriority,
    build_provider_ticket_analysis_schema,
)


class FakeLLMProvider:
    name = "llm"
    model = "synthetic-model"
    is_external = True

    async def analyze(self, ticket: TicketAnalysisInput) -> ProviderAnalysis:
        del ticket
        return ProviderAnalysis(
            analysis=TicketAnalysisResult(
                category=TicketCategory.GENERAL,
                priority=TicketPriority.LOW,
                summary="Synthetic summary",
                suggested_reply="Synthetic draft reply.",
                confidence=0.7,
                reasoning_tags=["general_question"],
            ),
            provider_used=self.name,
            model_used=self.model,
        )

    async def close(self) -> None:
        return None


def accepts_provider(provider: TicketAnalysisProvider) -> TicketAnalysisProvider:
    return provider


@pytest.mark.anyio
async def test_deterministic_provider_matches_contract() -> None:
    provider = DeterministicTicketAnalysisProvider()

    result = await accepts_provider(provider).analyze(
        TicketAnalysisInput(
            title="Payment failed",
            description="Please help with the invoice payment.",
        )
    )

    assert result.provider_used == "deterministic"
    assert result.model_used is None
    assert result.analysis.category is TicketCategory.BILLING
    assert result.analysis.priority is TicketPriority.MEDIUM
    assert result.analysis.confidence == 0.85


@pytest.mark.anyio
async def test_fake_llm_provider_matches_contract() -> None:
    provider = FakeLLMProvider()

    result = await accepts_provider(provider).analyze(
        TicketAnalysisInput(title="Question", description="Synthetic question")
    )

    assert result.analysis == TicketAnalysisResult.model_validate(
        result.analysis.model_dump()
    )
    assert result.provider_used == "llm"


@pytest.mark.parametrize(
    "invalid_result",
    [
        {
            "category": "unknown",
            "priority": "low",
            "summary": "Summary",
            "suggested_reply": "Reply",
            "confidence": 0.5,
            "reasoning_tags": [],
        },
        {
            "category": "general",
            "priority": "low",
            "summary": "Summary",
            "confidence": 0.5,
            "reasoning_tags": [],
        },
        {
            "category": "general",
            "priority": "low",
            "summary": "x" * 501,
            "suggested_reply": "Reply",
            "confidence": 0.5,
            "reasoning_tags": [],
        },
        {
            "category": "general",
            "priority": "low",
            "summary": "Summary",
            "suggested_reply": "Reply",
            "confidence": "0.5",
            "reasoning_tags": [],
        },
        {
            "category": "general",
            "priority": "low",
            "summary": "Summary",
            "suggested_reply": "Reply",
            "confidence": 0.5,
        },
    ],
)
def test_structured_result_rejects_invalid_values(
    invalid_result: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        TicketAnalysisResult.model_validate(invalid_result)


def test_provider_schema_uses_only_supported_subset() -> None:
    schema = build_provider_ticket_analysis_schema()
    allowed_keywords = {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "enum",
        "items",
    }
    forbidden_keywords = {
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "maximum",
        "maxItems",
        "$ref",
        "$defs",
    }

    def assert_supported(value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key == "properties":
                    assert isinstance(nested, dict)
                    for property_schema in nested.values():
                        assert_supported(property_schema)
                    continue
                assert key not in forbidden_keywords
                assert key in allowed_keywords
                assert_supported(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_supported(nested)

    assert_supported(schema)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["properties"]["category"]["enum"] == [
        category.value for category in TicketCategory
    ]
    assert schema["properties"]["priority"]["enum"] == [
        priority.value for priority in TicketPriority
    ]


@pytest.mark.parametrize(
    "update",
    [
        {"summary": "x" * 501},
        {"confidence": 1.01},
        {"unexpected": "field"},
    ],
)
def test_provider_valid_shape_still_uses_full_local_validation(
    update: dict[str, object],
) -> None:
    payload: dict[str, object] = {
        "category": "general",
        "priority": "low",
        "summary": "Summary",
        "suggested_reply": "Draft reply",
        "confidence": 0.5,
        "reasoning_tags": ["general_question"],
    }
    payload.update(update)

    with pytest.raises(ValidationError):
        TicketAnalysisResult.model_validate(payload)
