from app.models.request import TicketRequest
from app.models.response import TicketResponse
from app.services.classifier import (
    classify_case_type,
    route_department,
    score_severity,
    _extract_amount,
)
from app.services.transaction_matcher import match_transaction
from app.services.safety import build_safe_reply
from app.services.llm_client import get_llm_client, enhance_text_fields


def investigate(req: TicketRequest) -> TicketResponse:
    txn_id, evidence_verdict = match_transaction(req)

    case_type = classify_case_type(req)

    # Phishing always overrides — never let complaint text override safety routing
    complaint_lower = req.complaint.lower()
    if _has_phishing_signal(complaint_lower):
        case_type = "phishing_or_social_engineering"
        evidence_verdict = "insufficient_data"
        txn_id = None

    department = route_department(case_type, req)

    txn_amount = None
    if txn_id:
        for t in (req.transaction_history or []):
            if t.transaction_id == txn_id:
                txn_amount = t.amount
                break

    severity = score_severity(case_type, evidence_verdict, txn_amount, req)

    human_review = _needs_human_review(case_type, evidence_verdict, severity)

    confidence = _compute_confidence(case_type, evidence_verdict, txn_id, req)

    # Rule-based text (always produced — used as fallback)
    agent_summary = _build_agent_summary(case_type, txn_id, txn_amount, evidence_verdict, req)
    next_action = _build_next_action(case_type, txn_id, department, evidence_verdict)

    # Optional LLM enhancement for agent_summary and recommended_next_action
    llm = get_llm_client()
    enhanced = enhance_text_fields(
        llm, case_type, txn_id, txn_amount, evidence_verdict,
        department, severity, req.user_type, req.complaint,
    )
    if enhanced:
        agent_summary = enhanced.get("agent_summary", agent_summary)
        next_action = enhanced.get("next_action", next_action)

    # customer_reply is ALWAYS from safety templates — never from the LLM
    customer_reply = build_safe_reply(case_type, txn_id, req.language, req.complaint)

    reason_codes = _build_reason_codes(case_type, evidence_verdict, txn_id)

    return TicketResponse(
        ticket_id=req.ticket_id,
        relevant_transaction_id=txn_id,
        evidence_verdict=evidence_verdict,
        case_type=case_type,
        severity=severity,
        department=department,
        agent_summary=agent_summary,
        recommended_next_action=next_action,
        customer_reply=customer_reply,
        human_review_required=human_review,
        confidence=round(confidence, 2),
        reason_codes=reason_codes,
    )


def _has_phishing_signal(text: str) -> bool:
    import re
    return bool(re.search(
        r"\botp\b|\bpin\b|password|fake call|scam|someone called|suspicious.*call|"
        r"asked.*otp|asked.*pin|asked.*password|verify.*account.*block|ভুয়া|প্রতারণা",
        text, re.IGNORECASE
    ))


def _needs_human_review(case_type: str, verdict: str, severity: str) -> bool:
    if severity in ("high", "critical"):
        return True
    if verdict == "inconsistent":
        return True
    if case_type in (
        "wrong_transfer",
        "phishing_or_social_engineering",
        "duplicate_payment",
        "agent_cash_in_issue",
    ):
        return True
    return False


def _compute_confidence(
    case_type: str,
    verdict: str,
    txn_id,
    req: TicketRequest,
) -> float:
    base = 0.5
    if txn_id:
        base += 0.25
    if verdict == "consistent":
        base += 0.15
    elif verdict == "inconsistent":
        base += 0.05
    if case_type == "phishing_or_social_engineering":
        base = max(base, 0.9)
    if case_type == "other":
        base = min(base, 0.6)
    # Vague complaint
    complaint_words = len(req.complaint.split())
    if complaint_words < 5:
        base = min(base, 0.55)
    return min(base, 0.99)


def _build_agent_summary(
    case_type: str,
    txn_id,
    txn_amount,
    verdict: str,
    req: TicketRequest,
) -> str:
    amount_str = f"{txn_amount:.0f} BDT" if txn_amount else "an unspecified amount"
    txn_ref = f"via {txn_id}" if txn_id else ""

    summaries = {
        "wrong_transfer": (
            f"Customer reports sending {amount_str} {txn_ref} to an unintended recipient. "
            f"Evidence is {verdict}."
        ),
        "payment_failed": (
            f"Customer reports a failed payment of {amount_str} {txn_ref} "
            f"with possible balance deduction."
        ),
        "refund_request": (
            f"Customer requests refund of {amount_str} {txn_ref}. Not a service failure."
        ),
        "duplicate_payment": (
            f"Customer reports possible duplicate payment of {amount_str} {txn_ref}. "
            f"Evidence is {verdict}."
        ),
        "merchant_settlement_delay": (
            f"Merchant reports {amount_str} settlement {txn_ref} delayed beyond expected window."
        ),
        "agent_cash_in_issue": (
            f"Customer reports {amount_str} cash-in {txn_ref} not reflected in balance. "
            f"Evidence is {verdict}."
        ),
        "phishing_or_social_engineering": (
            "Customer reports an unsolicited call/message requesting credentials. "
            "Likely social engineering attempt. Customer has been advised not to share credentials."
        ),
        "other": (
            f"Customer reports a vague concern about their account. "
            f"Insufficient detail to identify relevant transaction."
        ),
    }
    return summaries.get(case_type, summaries["other"])


def _build_next_action(
    case_type: str,
    txn_id,
    department: str,
    verdict: str,
) -> str:
    txn_ref = f"transaction {txn_id}" if txn_id else "the reported transaction"
    actions = {
        "wrong_transfer": (
            f"Verify {txn_ref} details with the customer and initiate the wrong-transfer "
            "dispute workflow per policy."
        ),
        "payment_failed": (
            f"Investigate {txn_ref} ledger status. If balance was deducted on a failed payment, "
            "initiate the automatic reversal flow within standard SLA."
        ),
        "refund_request": (
            "Inform the customer that refund eligibility depends on the merchant's own policy. "
            "Provide guidance on contacting the merchant directly."
        ),
        "duplicate_payment": (
            f"Verify the duplicate with {department}. If the biller confirms only one payment "
            f"was received, initiate reversal of {txn_ref}."
        ),
        "merchant_settlement_delay": (
            f"Route to {department} to verify settlement batch status. "
            "If delayed, communicate revised ETA to the merchant."
        ),
        "agent_cash_in_issue": (
            f"Investigate {txn_ref} pending status with {department}. "
            "Confirm settlement state and resolve within the standard cash-in SLA."
        ),
        "phishing_or_social_engineering": (
            "Escalate to fraud_risk team immediately. Confirm to customer that the company "
            "never asks for OTP. Log the reported number for fraud pattern analysis."
        ),
        "other": (
            "Reply to customer asking for specific details: which transaction, what amount, "
            "what went wrong, and approximate time."
        ),
    }
    return actions.get(case_type, actions["other"])


def _build_reason_codes(case_type: str, verdict: str, txn_id) -> list[str]:
    codes = [case_type]
    if txn_id:
        codes.append("transaction_match")
    if verdict == "consistent":
        codes.append("evidence_consistent")
    elif verdict == "inconsistent":
        codes.append("evidence_inconsistent")
    else:
        codes.append("needs_clarification")
    return codes
