from app.pii import scrub_text
from app.logging_config import scrub_event


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_cccd_and_payment_card() -> None:
    out = scrub_text("CCCD 079123456789, card 4111 1111 1111 1111")
    assert "079123456789" not in out
    assert "4111 1111 1111 1111" not in out
    assert "REDACTED_CCCD" in out
    assert "REDACTED_CREDIT_CARD" in out


def test_log_processor_scrubs_nested_values_and_metadata() -> None:
    event = {
        "session_id": "student@vinuni.edu.vn",
        "payload": {"contacts": ["0901234567", {"identity": "079123456789"}]},
    }
    scrubbed = scrub_event(None, "info", event)
    assert scrubbed["session_id"] == "[REDACTED_EMAIL]"
    assert scrubbed["payload"]["contacts"] == [
        "[REDACTED_PHONE_VN]",
        {"identity": "[REDACTED_CCCD]"},
    ]
