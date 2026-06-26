import re
from app.models.request import TicketRequest

_CASE_RULES = [
    ("phishing_or_social_engineering", [
        r"\botp\b", r"\bpin\b", r"password", r"fake call", r"scam",
        r"they asked", r"someone called", r"suspicious", r"fraud call",
        r"verify.*account", r"account.*block", r"ভুয়া", r"প্রতারণা",
    ]),
    ("wrong_transfer", [
        r"wrong (number|person|recipient|account)", r"sent to wrong",
        r"wrong number", r"ভুল নম্বর", r"ভুল.*পাঠিয়েছি",
        r"wrong transfer", r"mistakenly sent",
        # P2P transfer where the recipient claims non-receipt → dispute path
        r"sent\b.*\b(brother|sister|friend|mother|father|wife|husband|uncle|aunt|cousin|him|her)\b",
        r"sent\b.{0,60}(didn.?t|did not|hasn.?t|has not|never).{0,15}(get|got|receiv)",
    ]),
    ("duplicate_payment", [
        r"charged twice", r"deducted twice", r"double (charged|deducted|payment)",
        r"duplicate", r"paid twice", r"two times.*deducted", r"দুইবার",
    ]),
    ("payment_failed", [
        r"(payment|transaction).*failed", r"failed.*payment",
        r"not (received|reflected|credited)", r"balance.*deducted",
        r"recharge failed", r"app.*showed failed", r"পেমেন্ট.*হয়নি",
        r"ব্যালেন্স.*কাটা",
    ]),
    ("merchant_settlement_delay", [
        r"settlement", r"not.*settled", r"merchant.*payment",
        r"sales.*not.*received", r"settlement.*delay", r"সেটেলমেন্ট",
    ]),
    ("agent_cash_in_issue", [
        r"agent.*cash.?in", r"cash.?in.*agent", r"cash.?in.*not.*reflect",
        r"deposit.*not.*reflect", r"agent.*deposit",
        r"এজেন্ট.*ক্যাশ", r"ক্যাশ ইন.*আসেনি", r"ক্যাশ ইন করেছি",
    ]),
    ("refund_request", [
        r"\brefund\b", r"return my money", r"give.*back.*money",
        r"money back", r"want.*back", r"রিফান্ড", r"ফেরত",
    ]),
]

_DEPARTMENT_MAP = {
    "wrong_transfer": "dispute_resolution",
    "payment_failed": "payments_ops",
    "duplicate_payment": "payments_ops",
    "merchant_settlement_delay": "merchant_operations",
    "agent_cash_in_issue": "agent_operations",
    "phishing_or_social_engineering": "fraud_risk",
    "refund_request": "customer_support",
    "other": "customer_support",
}


def classify_case_type(req: TicketRequest) -> str:
    text = req.complaint.lower()
    for case_type, patterns in _CASE_RULES:
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return case_type
    return "other"


def route_department(case_type: str, req: TicketRequest) -> str:
    if case_type == "refund_request":
        # contested refund (customer insists, amount > 1000) → dispute_resolution
        text = req.complaint.lower()
        amount = _extract_amount(text)
        if amount and amount > 1000 and re.search(r"(wrong|mistake|error|didn.t|not me)", text):
            return "dispute_resolution"
        return "customer_support"
    return _DEPARTMENT_MAP.get(case_type, "customer_support")


def score_severity(
    case_type: str,
    evidence_verdict: str,
    txn_amount: float | None,
    req: TicketRequest,
) -> str:
    if case_type == "phishing_or_social_engineering":
        return "critical"

    amount = txn_amount or _extract_amount(req.complaint.lower()) or 0

    if amount > 50000:
        return "critical"

    if case_type in ("wrong_transfer", "duplicate_payment", "agent_cash_in_issue"):
        if evidence_verdict == "consistent":
            return "high"
        # inconsistent or ambiguous (insufficient_data) still warrants a dispute review
        return "medium"

    if case_type == "payment_failed":
        return "high" if amount > 0 else "medium"

    if case_type == "merchant_settlement_delay":
        # A delayed settlement is funds-in-transit, not lost money → medium
        return "critical" if amount > 50000 else "medium"

    if amount > 5000:
        return "high"
    if amount > 1000:
        return "medium"

    return "low"


def _extract_amount(text: str) -> float | None:
    matches = re.findall(r"(\d[\d,]*)\s*(?:taka|tk|bdt|টাকা)?", text, re.IGNORECASE)
    amounts = []
    for m in matches:
        try:
            amounts.append(float(m.replace(",", "")))
        except ValueError:
            pass
    # Filter out years/phone fragments
    valid = [a for a in amounts if 10 <= a <= 1_000_000]
    return max(valid) if valid else None
