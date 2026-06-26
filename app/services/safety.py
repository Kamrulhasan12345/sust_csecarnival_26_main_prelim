import re
from typing import Optional

_BANGLA_RE = re.compile(r"[ঀ-৿]")

_EN_TEMPLATES = {
    "wrong_transfer": (
        "We have noted your concern about transaction {txn}. "
        "Our dispute team will review the case and contact you through official support channels. "
        "Please do not share your PIN or OTP with anyone."
    ),
    "duplicate_payment": (
        "We have noted the possible duplicate payment for transaction {txn}. "
        "Our payments team will verify with the biller and any eligible amount will be returned "
        "through official channels. Please do not share your PIN or OTP with anyone."
    ),
    "payment_failed": (
        "We have noted that transaction {txn} may have caused an unexpected balance deduction. "
        "Our payments team will review the case and any eligible amount will be returned "
        "through official channels. Please do not share your PIN or OTP with anyone."
    ),
    "refund_request": (
        "Thank you for reaching out. Refunds for completed payments depend on the merchant's own policy. "
        "We recommend contacting the merchant directly for assistance. "
        "If you need help, please reach out to us through official support channels. "
        "Please do not share your PIN or OTP with anyone."
    ),
    "merchant_settlement_delay": (
        "We have noted your concern about settlement {txn}. "
        "Our merchant operations team will check the batch status and update you on the expected "
        "settlement time through official channels."
    ),
    "agent_cash_in_issue": (
        "We have noted your concern about transaction {txn}. "
        "Our agent operations team will investigate and resolve this through official channels. "
        "Please do not share your PIN or OTP with anyone."
    ),
    "phishing_or_social_engineering": (
        "Thank you for reaching out before sharing any information. "
        "We never ask for your PIN, OTP, or password under any circumstances. "
        "Please do not share these with anyone, even if they claim to be from us. "
        "Our fraud team has been notified of this incident."
    ),
    "other": (
        "Thank you for reaching out. To help you faster, please share the transaction ID, "
        "the amount involved, and a brief description of what went wrong. "
        "Please do not share your PIN or OTP with anyone."
    ),
}

_BN_TEMPLATES = {
    "wrong_transfer": (
        "আপনার লেনদেন {txn} সম্পর্কে আমরা অবগত হয়েছি। "
        "আমাদের ডিসপুট টিম এটি পর্যালোচনা করবে এবং অফিসিয়াল চ্যানেলে আপনাকে জানাবে। "
        "অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"
    ),
    "duplicate_payment": (
        "লেনদেন {txn}-এর সম্ভাব্য ডুপ্লিকেট পেমেন্টের বিষয়ে আমরা অবগত হয়েছি। "
        "আমাদের পেমেন্টস টিম যাচাই করবে এবং যোগ্য পরিমাণ অফিসিয়াল চ্যানেলে ফেরত দেওয়া হবে। "
        "অনুগ্রহ করে আপনার পিন বা ওটিপি কারো সাথে শেয়ার করবেন না।"
    ),
    "payment_failed": (
        "লেনদেন {txn} অপ্রত্যাশিত ব্যালেন্স কাটার কারণ হতে পারে বলে আমরা অবগত হয়েছি। "
        "আমাদের পেমেন্টস টিম যাচাই করবে এবং যোগ্য পরিমাণ অফিসিয়াল চ্যানেলে ফেরত দেওয়া হবে। "
        "অনুগ্রহ করে আপনার পিন বা ওটিপি কারো সাথে শেয়ার করবেন না।"
    ),
    "refund_request": (
        "আপনার যোগাযোগের জন্য ধন্যবাদ। সম্পন্ন পেমেন্টের রিফান্ড মার্চেন্টের নিজস্ব নীতির উপর নির্ভর করে। "
        "সহায়তার জন্য সরাসরি মার্চেন্টের সাথে যোগাযোগ করুন। "
        "অনুগ্রহ করে আপনার পিন বা ওটিপি কারো সাথে শেয়ার করবেন না।"
    ),
    "merchant_settlement_delay": (
        "সেটেলমেন্ট {txn} সম্পর্কে আপনার উদ্বেগ আমরা লক্ষ্য করেছি। "
        "আমাদের মার্চেন্ট অপারেশন্স টিম ব্যাচ স্ট্যাটাস যাচাই করবে এবং অফিসিয়াল চ্যানেলে আপনাকে জানাবে।"
    ),
    "agent_cash_in_issue": (
        "আপনার লেনদেন {txn} এর বিষয়ে আমরা অবগত হয়েছি। "
        "আমাদের এজেন্ট অপারেশন্স দল এটি দ্রুত যাচাই করবে এবং অফিসিয়াল চ্যানেলে আপনাকে জানাবে। "
        "অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"
    ),
    "phishing_or_social_engineering": (
        "কোনো তথ্য শেয়ার করার আগে যোগাযোগ করার জন্য আপনাকে ধন্যবাদ। "
        "আমরা কখনো আপনার পিন, ওটিপি বা পাসওয়ার্ড চাই না। "
        "এগুলো কারো সাথে শেয়ার করবেন না, এমনকি যদি তারা আমাদের পক্ষ থেকে দাবি করে। "
        "আমাদের ফ্রড টিমকে এই ঘটনা সম্পর্কে জানানো হয়েছে।"
    ),
    "other": (
        "আপনার যোগাযোগের জন্য ধন্যবাদ। দ্রুত সহায়তার জন্য লেনদেন আইডি, পরিমাণ এবং কী সমস্যা হয়েছে তা জানান। "
        "অনুগ্রহ করে আপনার পিন বা ওটিপি কারো সাথে শেয়ার করবেন না।"
    ),
}


def build_safe_reply(
    case_type: str,
    txn_id: Optional[str],
    language: Optional[str],
    complaint_text: str,
) -> str:
    use_bangla = language == "bn" or (
        language != "en" and _is_predominantly_bangla(complaint_text)
    )
    templates = _BN_TEMPLATES if use_bangla else _EN_TEMPLATES
    template = templates.get(case_type, templates["other"])
    txn_ref = txn_id if txn_id else "your recent transaction"
    return template.format(txn=txn_ref)


def _is_predominantly_bangla(text: str) -> bool:
    bangla_chars = len(_BANGLA_RE.findall(text))
    return bangla_chars > len(text) * 0.15
