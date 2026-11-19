"""Security Guardrails & Anonymization Engine for AI Integration.

Requirements:
1. anonymize_submission(): Strip PII (full name, email, phone number) before sending to LLM.
2. verify_evidence_quote(): Ensure evidence quote is a verbatim substring of raw submission.
3. Prompt injection detection / neutralization.
"""
from __future__ import annotations
import re


def anonymize_submission(text: str) -> str:
    """Anonymize student submission text to protect privacy (GDPR / FERPA).
    
    Strips:
    - Email addresses
    - Phone numbers (VN standard format)
    - Full name indicators (e.g., 'Họ và tên: Nguyễn Văn A', 'Sinh viên: Trần Thị B')
    - Student ID / MSSV patterns
    """
    if not text:
        return ""

    sanitized = text

    # 1. Mask Email Addresses
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    sanitized = re.sub(email_pattern, "[EMAIL_ĐÃ_ẨN_DANH]", sanitized)

    # 2. Mask Phone Numbers (+84... or 09... 08... 03... 07... 05...)
    phone_pattern = r'(\+84|0)(3[2-9]|5[6|8|9]|7[0|6-9]|8[1-9]|9[0-9])[0-9]{7}'
    sanitized = re.sub(phone_pattern, "[SĐT_ĐÃ_ẨN_DANH]", sanitized)

    # 3. Mask Student ID (MSSV: 20120... or SV...)
    mssv_pattern = r'(?i)\b(mssv|mã\s*số\s*sinh\s*viên|mã\s*sv)[:\s]*([0-9]{6,10})\b'
    sanitized = re.sub(mssv_pattern, "[MSSV_ĐÃ_ẨN_DANH]", sanitized)

    # 4. Mask Full Name labels
    name_label_pattern = r'(?i)(họ\s*và\s*tên|họ\s*tên|sinh\s*viên|người\s*làm\s*bài|tác\s*giả)[:\s]*([A-ZÀ-Ỹa-zà-ỹ\s]{3,30})(?=[\r\n,;]|$)'
    sanitized = re.sub(name_label_pattern, r"\1: [HỌ_TÊN_ĐÃ_ẨN_DANH]", sanitized)

    return sanitized


INJECTION_PATTERNS = re.compile(
    r"(?i)(ignore|disregard|forget)\s+(all\s+|any\s+|the\s+)?(previous|prior|above|your)\s+(instructions?|rules?|prompts?)"
    r"|(bỏ\s*qua|phớt\s*lờ|quên)\s+(hết\s+|mọi\s+|tất\s*cả\s+|các\s+)*(hướng\s*dẫn|chỉ\s*dẫn|quy\s*tắc|lệnh)"
    r"|(system|developer)\s+(prompt|message|instructions?)|(tiết\s*lộ|in\s*ra|cho\s*xem).{0,20}(prompt|chỉ\s*dẫn\s*hệ\s*thống)"
    r"|(you\s+are\s+now|từ\s*giờ\s*bạn\s*là|đóng\s*vai\s*(quản\s*trị|admin))"
    r"|(đổi|sửa|nâng|cộng)\s+(điểm|mức)"
)


def detect_injection(text: str) -> bool:
    """A signal for the audit trace only. The real defence is that the model has no power to act."""
    return bool(text and INJECTION_PATTERNS.search(re.sub(r"[​-‏⁠﻿]", "", text)))


def scrub_identity(text: str, *identifiers: str) -> str:
    """Anonymize, then remove the account's own name and email however they were typed."""
    sanitized = anonymize_submission(text)
    for value in identifiers:
        if value and len(value.strip()) >= 3:
            sanitized = re.sub(re.escape(value.strip()), "[ĐÃ_ẨN_DANH]", sanitized, flags=re.IGNORECASE)
    return sanitized


def verify_evidence_quote(evidence_quote: str, raw_submission: str) -> bool:
    """Verify that an evidence quote extracted by AI exists verbatim in raw submission.
    
    Prevents hallucinated evidence quotes from being accepted into student records.
    Whitespace and case differences are normalized for robustness.
    """
    if not evidence_quote or not raw_submission:
        return False

    # Normalize whitespace
    def normalize_ws(s: str) -> str:
        return " ".join(s.strip().split())

    norm_quote = normalize_ws(evidence_quote)
    norm_sub = normalize_ws(raw_submission)

    # Check direct substring
    if norm_quote in norm_sub:
        return True

    # Check case-insensitive substring
    if norm_quote.lower() in norm_sub.lower():
        return True

    return False
