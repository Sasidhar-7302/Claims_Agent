from email.message import EmailMessage
from pathlib import Path

from app.integrations.imap import ImapConfig, build_imap_email_id, parse_imap_email_id, parse_raw_message


def _config() -> ImapConfig:
    return ImapConfig(
        host="imap.example.com",
        port=993,
        username="agent@example.com",
        password="secret",
        folder="INBOX",
        query="UNSEEN",
        use_ssl=True,
    )


def test_build_and_parse_imap_email_id():
    email_id = build_imap_email_id("12345", "imap.example.com", "agent@example.com", "INBOX")
    assert email_id.startswith("imap_")
    assert parse_imap_email_id(email_id) == "12345"
    assert parse_imap_email_id("bad-format") is None


def test_parse_raw_message_plain_and_attachment():
    msg = EmailMessage()
    msg["From"] = "Customer <customer@example.com>"
    msg["To"] = "Claims <claims@example.com>"
    msg["Subject"] = "Warranty claim"
    msg["Date"] = "Thu, 26 Feb 2026 09:00:00 +0000"
    msg.set_content("Hello team,\nThe device stopped working.")
    msg.add_attachment(
        b"serial,amount\nABC123,299",
        maintype="text",
        subtype="csv",
        filename="receipt.csv",
    )

    parsed = parse_raw_message(msg.as_bytes(), uid="777", config=_config(), download_attachments=False)
    assert parsed.uid == "777"
    assert parsed.subject == "Warranty claim"
    assert "device stopped working" in parsed.body
    assert parsed.attachments == ["receipt.csv"]
    assert parsed.attachment_paths == []


def test_parse_raw_message_downloads_attachments(tmp_path: Path, monkeypatch):
    msg = EmailMessage()
    msg["From"] = "Customer <customer@example.com>"
    msg["To"] = "Claims <claims@example.com>"
    msg["Subject"] = "Claim with docs"
    msg.set_content("Please see attached proof.")
    msg.add_attachment(
        b"proof-data",
        maintype="application",
        subtype="octet-stream",
        filename="proof.bin",
    )

    def fake_save_attachment_bytes(email_id: str, filename: str, data: bytes) -> Path:
        target = tmp_path / filename
        target.write_bytes(data)
        return target

    monkeypatch.setattr("app.attachments.save_attachment_bytes", fake_save_attachment_bytes)

    parsed = parse_raw_message(msg.as_bytes(), uid="901", config=_config(), download_attachments=True)
    assert parsed.attachments == ["proof.bin"]
    assert len(parsed.attachment_paths) == 1
    assert Path(parsed.attachment_paths[0]).exists()


def test_parse_raw_message_html_fallback():
    msg = EmailMessage()
    msg["From"] = "Customer <customer@example.com>"
    msg["To"] = "Claims <claims@example.com>"
    msg["Subject"] = "HTML only"
    msg.set_content("<p>Need warranty help.</p>", subtype="html")

    parsed = parse_raw_message(msg.as_bytes(), uid="456", config=_config(), download_attachments=False)
    assert "Need warranty help." in parsed.body

