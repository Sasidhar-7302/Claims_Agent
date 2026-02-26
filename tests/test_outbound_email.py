from uuid import uuid4

from app.integrations.outbound_email import send_claim_email


def _base_state():
    nonce = uuid4().hex
    return {
        "claim_id": f"CLM-TEST-OUTBOUND-{nonce}",
        "email_id": f"email_test_outbound_{nonce}",
        "email_from": "customer@example.com",
        "customer_email_draft": "Subject: Test Subject\n\nThis is a test body.",
        "extracted_fields": {
            "customer_email": "customer@example.com",
        },
    }


def test_manual_mode_records_skip():
    result = send_claim_email(_base_state(), send_mode="manual")
    assert result.ok is True
    assert result.status == "SKIPPED"
    assert result.provider == "manual"


def test_idempotent_duplicate_for_sent(monkeypatch):
    state = _base_state()

    def fake_send(*args, **kwargs):
        return "gmail_message_123"

    monkeypatch.setattr(
        "app.integrations.outbound_email._send_gmail_api",
        fake_send,
    )

    first = send_claim_email(state, send_mode="gmail_api", gmail_service=object())
    assert first.ok is True
    assert first.status == "SENT"

    second = send_claim_email(state, send_mode="gmail_api", gmail_service=object())
    assert second.ok is True
    assert second.duplicate is True
    assert second.status == "SENT_DUPLICATE_SKIPPED"
