"""Live LLM backend tests — exercise the REAL backend(s) configured in .env.

These are skipped unless you opt in:

    RUN_LLM_TESTS=1 uv run pytest -m llm -v

They confirm the configured backend(s) are reachable and that whatever they
return is still schema-valid and safe (or cleanly falls back). They make real
network calls, so they are slow and excluded from normal runs.
"""
import os
from pathlib import Path

import pytest

from tests._helpers import (
    assert_ok, refund_promise, credential_request, third_party_referral,
)

pytestmark = pytest.mark.llm

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


@pytest.fixture
def live_env():
    """Restore real keys from .env over conftest's blanking, force the LLM
    singleton to rebuild, and re-disable everything on teardown."""
    from dotenv import load_dotenv
    import app.services.llm_client as L

    if not ENV_PATH.exists():
        pytest.skip(".env not found — add one (see .env.example) to run live LLM tests")

    load_dotenv(dotenv_path=str(ENV_PATH), override=True)
    if not (os.getenv("CUSTOM_API_URL", "").strip() or os.getenv("GROQ_API_KEY", "").strip()):
        pytest.skip("no LLM backend configured in .env (CUSTOM_API_URL or GROQ_API_KEY)")

    L._client = None  # rebuild get_llm_client() with the real backends
    try:
        yield L
    finally:
        for _var in ("CUSTOM_API_URL", "CUSTOM_API_KEY", "GROQ_API_KEY"):
            os.environ[_var] = ""
        L._client = None


def test_backend_configured(live_env):
    llm = live_env.LLMClient()
    assert llm.has_backend, "expected at least one configured LLM backend"
    print(f"\nConfigured backends: {[(m, c.base_url.host) for c, m in llm._backends]}")


def test_live_enhancement_is_safe(live_env):
    """The real backend either returns safe parsed text or None (fallback).
    It must never return unsafe content past the filter."""
    llm = live_env.LLMClient()
    result = live_env.enhance_text_fields(
        llm, "wrong_transfer", "TXN-9101", 5000.0, "consistent",
        "dispute_resolution", "high", "customer",
        "I sent 5000 taka to a wrong number around 2pm today.",
    )
    if result is None:
        pytest.skip("backend reachable but produced no usable/safe JSON this run")
    print(f"\nagent_summary: {result['agent_summary']}\nnext_action  : {result['next_action']}")
    assert set(result.keys()) == {"agent_summary", "next_action"}
    for field in result.values():
        assert field.strip()
        assert refund_promise(field) is None, f"unsafe refund/reversal promise: {field!r}"
        assert credential_request(field) is None, f"credential request: {field!r}"
        assert third_party_referral(field) is None, f"third-party referral: {field!r}"


def test_live_http_endpoint_with_real_llm(live_env):
    """Full request through the app with the real LLM active. Rule-engine fields
    must stay correct and the response must stay schema-valid and safe."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    body = {
        "ticket_id": "LIVE-1",
        "complaint": "I sent 5000 taka to a wrong number around 2pm today. Please help.",
        "language": "en",
        "transaction_history": [{
            "transaction_id": "TXN-9101", "timestamp": "2026-04-14T14:08:22Z",
            "type": "transfer", "amount": 5000,
            "counterparty": "+8801719876543", "status": "completed",
        }],
    }
    b = assert_ok(client.post("/analyze-ticket", json=body), "LIVE-1")
    # The deterministic engine must produce correct evidence regardless of the LLM.
    assert b["case_type"] == "wrong_transfer"
    assert b["relevant_transaction_id"] == "TXN-9101"
    assert b["department"] == "dispute_resolution"
    print(f"\nagent_summary: {b['agent_summary']}\ncustomer_reply: {b['customer_reply']}")
