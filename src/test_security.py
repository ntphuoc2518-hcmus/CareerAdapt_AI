from security_utils import normalize_nfc, redact_pii, verify_evidence_quote, verify_ownership

def run_tests():
    raw = "Học viên Nguyen Van A, email: test_student@gmail.com, sdt: 0912345678 đã nộp bài."
    redacted = redact_pii(raw, known_name="Nguyen Van A")
    assert "[REDACTED_EMAIL]" in redacted and "[REDACTED_PHONE]" in redacted
    assert "[REDACTED_NAME]" in redacted
    assert "test_student@gmail.com" not in redacted and "0912345678" not in redacted
    assert "Nguyen Van A" not in redacted
    assert redact_pii("Nguyễn Văn A làm bài", known_name="Nguyễn Văn A") == "[REDACTED_NAME] làm bài"
    assert redact_pii("Không có PII", known_name="") == "Không có PII"
    assert verify_evidence_quote("Doanh thu giảm 14.29% tháng 2", "giảm 14.29%")
    assert not verify_evidence_quote("Doanh thu giảm 14.29% tháng 2", "giảm 20%")
    a, b = "00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"
    assert verify_ownership(a, a) and not verify_ownership(a, b)
    print("ALL SECURITY UTILITY TESTS PASSED")

if __name__ == "__main__": run_tests()
