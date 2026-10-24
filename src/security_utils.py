"""Security and data-protection utilities for CareerAdapt."""
import re
import unicodedata
from typing import Optional

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_REGEX = re.compile(r"(?:\+?84|0)(?:\d[\s.-]?){9,10}\b")

def normalize_nfc(text: Optional[str]) -> str:
    return unicodedata.normalize("NFC", text or "")

def redact_pii(text: Optional[str], known_name: Optional[str] = None) -> str:
    """Redact email/phone and optionally the exact known profile name.

    Does not attempt generic named-entity recognition. Pass a name only when it
    was obtained from the authenticated user's own profile.
    """
    if not text:
        return ""
    clean = normalize_nfc(text)
    if known_name and known_name.strip():
        name = normalize_nfc(known_name).strip()
        clean = re.sub(re.escape(name), "[REDACTED_NAME]", clean, flags=re.IGNORECASE)
    clean = EMAIL_REGEX.sub("[REDACTED_EMAIL]", clean)
    clean = PHONE_REGEX.sub("[REDACTED_PHONE]", clean)
    return clean

def verify_evidence_quote(submission_text: str, evidence_quote: str) -> bool:
    if not submission_text or not evidence_quote:
        return False
    norm_submission = re.sub(r"\s+", " ", normalize_nfc(submission_text)).strip().casefold()
    norm_quote = re.sub(r"\s+", " ", normalize_nfc(evidence_quote)).strip().casefold()
    return norm_quote in norm_submission

def verify_ownership(resource_owner_id: str, authenticated_user_id: str) -> bool:
    if not resource_owner_id or not authenticated_user_id:
        return False
    return str(resource_owner_id).strip().lower() == str(authenticated_user_id).strip().lower()
