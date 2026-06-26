"""Non-AI / structural edge cases: schema robustness, error handling, boundary
values, large inputs, type errors, determinism, and stability.

LLM is disabled via conftest.py, so these exercise the deterministic engine.
"""
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests._helpers import assert_ok, schema_problems, ENUMS

client = TestClient(app)


def post(body):
    return client.post("/analyze-ticket", json=body)


def txn(tid="TXN-1", ts="2026-04-14T12:00:00Z", typ="transfer", amt=1000,
        cp="+8801711111111", status="completed"):
    return {"transaction_id": tid, "timestamp": ts, "type": typ,
            "amount": amt, "counterparty": cp, "status": status}


# --------------------------------------------------------------------------
# Optional-field handling — all should succeed (200) and stay schema-valid
# --------------------------------------------------------------------------
class TestOptionalFields:
    def test_only_required_fields(self):
        assert_ok(post({"ticket_id": "T1", "complaint": "money missing from account"}), "T1")

    def test_all_optionals_present(self):
        body = {
            "ticket_id": "T2", "complaint": "I sent 1000 to wrong number",
            "language": "en", "channel": "in_app_chat", "user_type": "customer",
            "campaign_context": "boishakh_bonanza_day_1",
            "transaction_history": [txn()], "metadata": {"foo": "bar", "n": 3},
        }
        assert_ok(post(body), "T2")

    @pytest.mark.parametrize("field", ["language", "channel", "user_type",
                                        "campaign_context", "metadata"])
    def test_optional_field_null(self, field):
        body = {"ticket_id": "T3", "complaint": "something wrong", field: None}
        assert_ok(post(body), "T3")

    def test_unknown_extra_fields_ignored(self):
        body = {"ticket_id": "T4", "complaint": "help me",
                "totally_unknown": "x", "nested": {"a": [1, 2, 3]}, "n": 42}
        assert_ok(post(body), "T4")

    def test_empty_transaction_history(self):
        assert_ok(post({"ticket_id": "T5", "complaint": "x happened", "transaction_history": []}), "T5")

    def test_unknown_channel_value_does_not_crash(self):
        # channel is free-form string in our model; an unexpected value must not crash
        body = {"ticket_id": "T6", "complaint": "issue", "channel": "carrier_pigeon"}
        assert_ok(post(body), "T6")


# --------------------------------------------------------------------------
# Boundary / unusual values
# --------------------------------------------------------------------------
class TestBoundaryValues:
    @pytest.mark.parametrize("amount", [0, 1, 999, 1000, 1001, 5000, 50000,
                                         50001, 100000, 999999, 1000000])
    def test_amount_boundaries(self, amount):
        body = {"ticket_id": "TA", "complaint": f"I sent {amount} to wrong number",
                "transaction_history": [txn(amt=amount)]}
        b = assert_ok(post(body), "TA")
        assert b["severity"] in ENUMS["severity"]

    def test_negative_amount(self):
        body = {"ticket_id": "TN", "complaint": "weird negative",
                "transaction_history": [txn(amt=-500)]}
        assert_ok(post(body), "TN")

    def test_float_amount(self):
        body = {"ticket_id": "TF", "complaint": "I paid 1234.56",
                "transaction_history": [txn(typ="payment", amt=1234.56, status="failed")]}
        assert_ok(post(body), "TF")

    def test_integer_amount_coerced(self):
        body = {"ticket_id": "TI", "complaint": "sent 500",
                "transaction_history": [txn(amt=500)]}
        assert_ok(post(body), "TI")

    def test_numeric_string_amount_coerced(self):
        # pydantic coerces "500" -> 500.0
        body = {"ticket_id": "TS", "complaint": "sent 500",
                "transaction_history": [txn(amt="500")]}
        assert_ok(post(body), "TS")

    def test_many_transactions(self):
        hist = [txn(tid=f"TXN-{i}", amt=100 + i) for i in range(50)]
        body = {"ticket_id": "TM", "complaint": "something wrong with one of these",
                "transaction_history": hist}
        assert_ok(post(body), "TM")

    def test_ticket_id_with_special_chars(self):
        tid = "TKT/2026#001-✓"
        assert_ok(post({"ticket_id": tid, "complaint": "issue"}), tid)


# --------------------------------------------------------------------------
# Large / unusual text
# --------------------------------------------------------------------------
class TestUnusualText:
    def test_very_long_complaint(self):
        complaint = "I sent money to the wrong number. " * 500  # ~17k chars
        assert_ok(post({"ticket_id": "TL", "complaint": complaint}), "TL")

    def test_emoji_only_complaint(self):
        assert_ok(post({"ticket_id": "TE", "complaint": "😡😡💸❓"}), "TE")

    def test_gibberish_complaint(self):
        assert_ok(post({"ticket_id": "TG", "complaint": "asdkjh qwe zxcvb plkmn"}), "TG")

    def test_single_char_complaint(self):
        assert_ok(post({"ticket_id": "TC", "complaint": "?"}), "TC")

    def test_newlines_and_tabs(self):
        assert_ok(post({"ticket_id": "TT", "complaint": "line1\n\tline2\r\n  line3"}), "TT")

    def test_html_like_complaint_not_executed(self):
        # ensure no template/HTML injection surprises in output
        b = assert_ok(post({"ticket_id": "TH", "complaint": "<script>alert(1)</script> money gone"}), "TH")
        assert isinstance(b["customer_reply"], str)


# --------------------------------------------------------------------------
# Error handling — controlled responses, never a crash
# --------------------------------------------------------------------------
class TestErrorHandling:
    def test_malformed_json_400(self):
        r = client.post("/analyze-ticket", content=b"{not json",
                        headers={"Content-Type": "application/json"})
        assert r.status_code == 400

    def test_empty_body_400(self):
        r = client.post("/analyze-ticket", content=b"",
                        headers={"Content-Type": "application/json"})
        assert r.status_code == 400

    def test_json_array_instead_of_object_400(self):
        r = client.post("/analyze-ticket", json=[1, 2, 3])
        assert r.status_code == 400

    def test_missing_both_required_400(self):
        assert post({}).status_code == 400

    def test_missing_complaint_400(self):
        assert post({"ticket_id": "T"}).status_code == 400

    def test_missing_ticket_id_400(self):
        assert post({"complaint": "x"}).status_code == 400

    @pytest.mark.parametrize("complaint", ["", "   ", "\n", "\t  \n"])
    def test_empty_or_whitespace_complaint_422(self, complaint):
        assert post({"ticket_id": "T", "complaint": complaint}).status_code == 422

    def test_ticket_id_wrong_type_400(self):
        assert post({"ticket_id": 12345, "complaint": "x"}).status_code == 400

    def test_transaction_history_wrong_type_400(self):
        assert post({"ticket_id": "T", "complaint": "x", "transaction_history": "nope"}).status_code == 400

    def test_transaction_entry_missing_required_subfield_400(self):
        bad = {"transaction_id": "T", "type": "transfer"}  # missing timestamp/amount/...
        assert post({"ticket_id": "T", "complaint": "x", "transaction_history": [bad]}).status_code == 400

    def test_transaction_amount_non_numeric_400(self):
        bad = txn(amt="not-a-number")
        assert post({"ticket_id": "T", "complaint": "x", "transaction_history": [bad]}).status_code == 400

    def test_error_body_leaks_no_internals(self):
        r = post({})
        low = r.text.lower()
        for leak in ("traceback", 'file "', "line ", "pydantic", "site-packages", "valueerror"):
            assert leak not in low, f"error body leaked: {leak}"

    def test_wrong_content_type_does_not_crash(self):
        r = client.post("/analyze-ticket", content=b"ticket_id=T&complaint=x",
                        headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert r.status_code in (400, 415, 422)


# --------------------------------------------------------------------------
# Determinism, idempotency, stability, performance
# --------------------------------------------------------------------------
class TestStability:
    def test_identical_input_is_deterministic(self):
        body = {"ticket_id": "TD", "complaint": "I sent 5000 to a wrong number today",
                "transaction_history": [txn(amt=5000)]}
        first = post(body).json()
        for _ in range(5):
            assert post(body).json() == first

    def test_health_stable_across_many_calls(self):
        for _ in range(25):
            r = client.get("/health")
            assert r.status_code == 200 and r.json() == {"status": "ok"}

    def test_latency_well_under_limit(self):
        body = {"ticket_id": "TP", "complaint": "I paid 850 twice for my bill",
                "transaction_history": [txn(tid="A", typ="payment", amt=850),
                                        txn(tid="B", typ="payment", amt=850)]}
        t0 = time.time()
        assert_ok(post(body), "TP")
        assert time.time() - t0 < 5.0  # rule-based must be fast

    def test_burst_of_varied_requests(self):
        for i in range(30):
            body = {"ticket_id": f"B{i}", "complaint": f"issue number {i} with 100{i} taka",
                    "transaction_history": [txn(tid=f"X{i}", amt=1000 + i)]}
            assert_ok(post(body), f"B{i}")
