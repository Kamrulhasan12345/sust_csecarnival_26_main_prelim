"""Unit tests for the LLM output safety filter and JSON parsing.

These cover the guarantee that LLM-generated agent_summary / recommended_next_action
can never introduce a safety violation: any unsafe generated text is rejected so the
caller falls back to the safe rule-based templates. No network calls.
"""
from app.services.llm_client import _llm_output_is_safe, _parse_json_object


class TestLLMSafetyFilter:
    SAFE = [
        ("Customer reports a wrong transfer of 5000 BDT via TXN-9101.",
         "Verify transaction details and initiate the dispute workflow per policy."),
        ("Failed payment with balance deducted.",
         "Investigate the ledger. If deducted on a failed payment, initiate the automatic reversal flow within SLA."),
        ("Phishing report.",
         "Advise the customer to never share their PIN or OTP with anyone and escalate to fraud_risk."),
        ("Duplicate payment suspected.",
         "Verify with the biller; any eligible amount will be returned through official channels."),
    ]

    UNSAFE = [
        ("x", "We will refund you the full amount today."),
        ("x", "You will be refunded within 24 hours."),
        ("x", "Your account will be unblocked after we recover the funds."),
        ("x", "We will reverse the transaction immediately."),
        ("x", "The refund has been approved and will reflect shortly."),
        ("x", "Ask the customer to share their OTP to verify identity."),
        ("Please provide your PIN and password to proceed.", "x"),
    ]

    def test_safe_outputs_pass(self):
        for summary, action in self.SAFE:
            assert _llm_output_is_safe(summary, action) is True, \
                f"safe text wrongly rejected: {action!r}"

    def test_unsafe_outputs_blocked(self):
        for summary, action in self.UNSAFE:
            assert _llm_output_is_safe(summary, action) is False, \
                f"unsafe text wrongly allowed: {summary!r} / {action!r}"


class TestLLMParsing:
    def test_plain_json(self):
        out = _parse_json_object('{"agent_summary": "s", "next_action": "a"}')
        assert out == {"agent_summary": "s", "next_action": "a"}

    def test_markdown_fenced_json(self):
        raw = '```json\n{"agent_summary": "s", "next_action": "a"}\n```'
        assert _parse_json_object(raw) == {"agent_summary": "s", "next_action": "a"}

    def test_json_embedded_in_prose(self):
        raw = 'Here is the result:\n{"agent_summary": "s", "next_action": "a"}\nDone.'
        assert _parse_json_object(raw) == {"agent_summary": "s", "next_action": "a"}

    def test_truncated_json_returns_none(self):
        # e.g. a model that hit max_tokens mid-object
        raw = '{"agent_summary": "Customer reports a wrong transfer and next_action": "Init'
        assert _parse_json_object(raw) is None

    def test_reasoning_prose_returns_none(self):
        raw = "1. Analyze the request. 2. Draft the summary. The case involves..."
        assert _parse_json_object(raw) is None

    def test_unsafe_json_rejected_at_parse(self):
        raw = '{"agent_summary": "ok", "next_action": "We will refund you immediately."}'
        assert _parse_json_object(raw) is None

    def test_missing_keys_returns_none(self):
        assert _parse_json_object('{"summary": "x"}') is None

    def test_empty_returns_none(self):
        assert _parse_json_object("") is None
        assert _parse_json_object(None) is None
