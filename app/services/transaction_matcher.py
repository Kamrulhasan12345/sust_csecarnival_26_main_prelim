import re
from datetime import datetime, timezone
from typing import Optional, Tuple

from app.models.request import TicketRequest, TransactionEntry


def match_transaction(req: TicketRequest) -> Tuple[Optional[str], str]:
    """Return (relevant_transaction_id, evidence_verdict)."""
    history = req.transaction_history or []
    if not history:
        return None, "insufficient_data"

    complaint = req.complaint.lower()
    complaint_amount = _extract_amount(complaint)
    complaint_type_hint = _extract_type_hint(complaint)
    is_yesterday = bool(re.search(r"\byesterday\b", complaint))
    is_today = bool(re.search(r"\btoday\b|আজ", complaint))

    scored: list[Tuple[int, TransactionEntry]] = []
    for txn in history:
        score = 0
        # Amount match
        if complaint_amount and abs(txn.amount - complaint_amount) < 0.01:
            score += 3
        # Type hint match
        if complaint_type_hint and txn.type == complaint_type_hint:
            score += 2
        # Status match (failed/pending are noteworthy)
        if txn.status in ("failed", "pending"):
            score += 1
        # Time match
        try:
            txn_dt = datetime.fromisoformat(txn.timestamp.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            delta_days = (now - txn_dt).days
            if is_today and delta_days == 0:
                score += 2
            elif is_yesterday and delta_days == 1:
                score += 2
            elif delta_days <= 1:
                score += 1
        except Exception:
            pass
        scored.append((score, txn))

    if not scored:
        return None, "insufficient_data"

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_txn = scored[0]

    # Duplicate detection takes precedence over the generic ambiguity check:
    # if the complaint alleges a duplicate and two near-identical transactions
    # exist, the LATER one is the suspected duplicate (evidence is consistent).
    if re.search(r"twice|duplicate|double|two times|2 times|দুইবার", complaint):
        groups: dict = {}
        for _, t in scored:
            key = (t.amount, t.type, t.counterparty, t.status)
            groups.setdefault(key, []).append(t)
        for txns in groups.values():
            if len(txns) >= 2:
                latest = max(txns, key=lambda t: t.timestamp)
                return latest.transaction_id, "consistent"

    # Multiple plausible transactions → ambiguous (can't pick one safely)
    plausible = [s for s in scored if s[0] >= 5]
    if len(plausible) > 1:
        return None, "insufficient_data"

    # Multiple transactions with same best score and weak signal → ambiguous
    top_ties = [s for s in scored if s[0] == best_score]
    if len(top_ties) > 1 and best_score < 3:
        return None, "insufficient_data"

    if best_score < 2:
        return None, "insufficient_data"

    # Determine verdict
    verdict = _determine_verdict(req, best_txn, scored)
    return best_txn.transaction_id, verdict


def _determine_verdict(
    req: TicketRequest,
    best_txn: TransactionEntry,
    scored: list,
) -> str:
    complaint = req.complaint.lower()
    case_hint = _extract_case_hint(complaint)

    # Duplicate payment: two very close identical transactions
    if case_hint == "duplicate":
        identical = [
            s for _, s in scored
            if s.amount == best_txn.amount
            and s.type == best_txn.type
            and s.status == best_txn.status
            and s.counterparty == best_txn.counterparty
            and s.transaction_id != best_txn.transaction_id
        ]
        if identical:
            return "consistent"

    # Wrong transfer: repeated transfers to same recipient → inconsistent
    if case_hint == "wrong_transfer":
        same_recipient = [
            s for _, s in scored
            if s.counterparty == best_txn.counterparty
            and s.transaction_id != best_txn.transaction_id
            and s.type == "transfer"
        ]
        if len(same_recipient) >= 2:
            return "inconsistent"
        return "consistent"

    # Payment failed: status confirms
    if best_txn.status == "failed" and re.search(r"fail|didn.t work|not work", complaint):
        return "consistent"

    # Agent cash-in pending
    if best_txn.type == "cash_in" and best_txn.status == "pending":
        return "consistent"

    # Settlement pending
    if best_txn.type == "settlement" and best_txn.status == "pending":
        return "consistent"

    # Generic: if transaction found, assume consistent unless we detect contradiction
    return "consistent"


def _extract_amount(text: str) -> Optional[float]:
    matches = re.findall(r"(\d[\d,]*)\s*(?:taka|tk|bdt|টাকা)?", text, re.IGNORECASE)
    for m in matches:
        try:
            val = float(m.replace(",", ""))
            if 10 <= val <= 1_000_000:
                return val
        except ValueError:
            pass
    return None


def _extract_type_hint(text: str) -> Optional[str]:
    if re.search(r"\b(transfer|sent|send)\b", text):
        return "transfer"
    if re.search(r"\b(payment|paid|pay|recharge|bill)\b", text):
        return "payment"
    if re.search(r"\bcash.?in\b|deposit", text):
        return "cash_in"
    if re.search(r"\bcash.?out\b|withdraw", text):
        return "cash_out"
    if re.search(r"\bsettlement\b", text):
        return "settlement"
    if re.search(r"\brefund\b", text):
        return "refund"
    return None


def _extract_case_hint(text: str) -> Optional[str]:
    if re.search(r"wrong (number|person|recipient)", text):
        return "wrong_transfer"
    if re.search(r"twice|duplicate|double", text):
        return "duplicate"
    return None
