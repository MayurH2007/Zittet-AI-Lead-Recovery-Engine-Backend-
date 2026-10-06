"""LLM service / provider tests: mock output validation, malformed, failure, timeout."""

from __future__ import annotations

import json

import pytest

from app.core.exceptions import LLMError, LLMOutputInvalid, LLMTimeoutError
from app.llm.base import LLMContext
from app.llm.mock_provider import MockLLMProvider
from app.llm.prompts import PROMPT_VERSION, build_user_prompt
from app.schemas.analysis import AnalysisResponse
from app.schemas.lead import ConversationMessage, CustomerInfo, LeadMetadata
from app.services.analysis_service import _apply_business_rules, _validate_llm_output


def _ctx(conversation: list[tuple[str, str]] | None = None) -> LLMContext:
    return LLMContext(
        customer=CustomerInfo(name="Arun", phone="+919876543210"),
        lead=LeadMetadata(source="whatsapp", status="contacted"),
        conversation=[
            ConversationMessage(role=r, message=m)
            for r, m in (conversation or [("customer", "50 employees and we need pricing.")])
        ],
    )


def test_mock_provider_returns_valid_json():
    provider = MockLLMProvider()
    raw = provider._generate(_ctx())
    data = json.loads(raw)
    validated = AnalysisResponse.model_validate(data)
    assert 0 <= validated.lead_score <= 100
    assert validated.priority in {"low", "medium", "high"}


def test_prompt_version_is_set():
    assert PROMPT_VERSION == "lead_recovery_v1"


def test_build_user_prompt_includes_conversation():
    prompt = build_user_prompt(
        customer=CustomerInfo(name="Arun", phone="+91"),
        lead=LeadMetadata(source="whatsapp", status="contacted"),
        conversation=[ConversationMessage(role="customer", message="hello world")],
    )
    assert "hello world" in prompt
    assert "customer" in prompt


def test_validate_llm_output_malformed_json():
    with pytest.raises(LLMOutputInvalid):
        _validate_llm_output("not json", tenant_id="t", lead_id="l")


def test_validate_llm_output_schema_invalid():
    with pytest.raises(LLMOutputInvalid):
        _validate_llm_output(
            json.dumps({"lead_score": 999, "priority": "urgent"}),
            tenant_id="t",
            lead_id="l",
        )


def test_validate_llm_output_valid():
    raw = MockLLMProvider()._generate(_ctx())
    resp = _validate_llm_output(raw, tenant_id="t", lead_id="l")
    assert isinstance(resp, AnalysisResponse)


@pytest.mark.asyncio
async def test_mock_provider_malformed_behavior():
    provider = MockLLMProvider(behavior="malformed")
    raw = await provider.analyze_lead(_ctx())
    # The malformed output should NOT validate.
    with pytest.raises(LLMOutputInvalid):
        _validate_llm_output(raw, tenant_id="t", lead_id="l")


@pytest.mark.asyncio
async def test_mock_provider_fail_behavior():
    provider = MockLLMProvider(behavior="fail")
    with pytest.raises(LLMError):
        await provider.analyze_lead(_ctx())


@pytest.mark.asyncio
async def test_mock_provider_timeout_behavior():
    provider = MockLLMProvider(behavior="timeout")
    with pytest.raises(LLMTimeoutError):
        await provider.analyze_lead(_ctx())


def test_business_rules_override_opt_out():
    raw = MockLLMProvider()._generate(_ctx([("customer", "I need pricing")]))
    resp = _validate_llm_output(raw, tenant_id="t", lead_id="l")
    # Now add an opt-out message and apply business rules.
    resp_after = _apply_business_rules(resp, [("customer", "STOP")])
    assert resp_after.do_not_contact is True
    assert resp_after.follow_up_channel == "none"
    assert resp_after.follow_up_message == ""


def test_business_rules_clamp_score():
    # Validation enforces 0-100; business rules clamp as a safety net.
    raw = '{"lead_score": 100, "priority": "high", "intent": "purchase", "stage": "negotiation", "summary": "x", "next_best_action": "y", "follow_up_channel": "whatsapp", "follow_up_message": "hi", "do_not_contact": false}'
    resp = _validate_llm_output(raw, tenant_id="t", lead_id="l")
    resp_after = _apply_business_rules(resp, [])
    assert 0 <= resp_after.lead_score <= 100
