"""
Outbound email delivery helpers.

Supports:
- Gmail API send.
- SMTP send.
- Idempotent dispatch tracking in SQLite.
"""

from __future__ import annotations

import base64
import hashlib
import mimetypes
import os
import smtplib
from dataclasses import dataclass
from email import encoders
from email.message import EmailMessage
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid, parseaddr
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.database import get_dispatch_by_key, record_email_dispatch


@dataclass
class DispatchResult:
    ok: bool
    status: str
    provider: str
    dispatch_key: str
    recipient: str
    subject: str
    message_id: str
    error: str
    duplicate: bool


def _load_email_draft(state: Dict[str, Any]) -> str:
    draft = (state.get("customer_email_draft") or "").strip()
    if draft:
        return draft
    path = state.get("customer_email_path")
    if path and Path(path).exists():
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    return ""


def _parse_subject_and_body(text: str, fallback_subject: str) -> Tuple[str, str]:
    lines = (text or "").splitlines()
    subject = fallback_subject
    body_start = 0

    for idx, line in enumerate(lines):
        if line.lower().startswith("subject:"):
            subject = line.split(":", 1)[1].strip() or fallback_subject
            body_start = idx + 1
            break

    body = "\n".join(lines[body_start:]).strip()
    if not body:
        body = text.strip()
    return subject, body


def _recipient_from_state(state: Dict[str, Any]) -> str:
    extracted = state.get("extracted_fields", {}) or {}
    email = (extracted.get("customer_email") or "").strip()
    if email:
        return parseaddr(email)[1] or email

    email_from = (state.get("email_from") or "").strip()
    parsed = parseaddr(email_from)[1]
    return parsed or email_from


def _collect_attachments(state: Dict[str, Any]) -> List[Path]:
    out: List[Path] = []
    label = state.get("return_label_path")
    if label:
        p = Path(label)
        if p.exists():
            out.append(p)
    return out


def _payload_hash(recipient: str, subject: str, body: str, attachments: List[Path]) -> str:
    hasher = hashlib.sha256()
    hasher.update((recipient or "").encode("utf-8"))
    hasher.update((subject or "").encode("utf-8"))
    hasher.update((body or "").encode("utf-8"))
    for a in attachments:
        hasher.update(a.name.encode("utf-8"))
        try:
            hasher.update(str(a.stat().st_size).encode("utf-8"))
        except Exception:
            hasher.update(b"0")
    return hasher.hexdigest()


def _send_gmail_api(
    service: Any,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    attachments: List[Path],
) -> str:
    msg = MIMEMultipart()
    msg["To"] = recipient
    msg["From"] = sender
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-Id"] = make_msgid()
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for path in attachments:
        ctype, _ = mimetypes.guess_type(str(path))
        maintype, subtype = ("application", "octet-stream")
        if ctype:
            maintype, subtype = ctype.split("/", 1)
        part = MIMEBase(maintype, subtype)
        part.set_payload(path.read_bytes())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{path.name}"')
        msg.attach(part)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    resp = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return resp.get("id", "")


def _send_smtp(
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    attachments: List[Path],
) -> str:
    host = (os.getenv("SMTP_HOST") or "").strip()
    port = int((os.getenv("SMTP_PORT") or "587").strip())
    username = (os.getenv("SMTP_USERNAME") or "").strip()
    password = (os.getenv("SMTP_PASSWORD") or "").strip()
    use_tls = (os.getenv("SMTP_USE_TLS") or "true").strip().lower() == "true"

    if not host:
        raise RuntimeError("SMTP_HOST is required for SMTP sending.")

    msg = EmailMessage()
    msg["To"] = recipient
    msg["From"] = sender
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-Id"] = make_msgid()
    msg.set_content(body)

    for path in attachments:
        ctype, _ = mimetypes.guess_type(str(path))
        if ctype:
            maintype, subtype = ctype.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"
        msg.add_attachment(
            path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=path.name,
        )

    if port == 465 and use_tls:
        with smtplib.SMTP_SSL(host, port, timeout=30) as server:
            if username:
                server.login(username, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            if use_tls:
                server.starttls()
                server.ehlo()
            if username:
                server.login(username, password)
            server.send_message(msg)

    return msg.get("Message-Id", "").strip("<>")


def send_claim_email(
    state: Dict[str, Any],
    send_mode: str,
    gmail_service: Any = None,
) -> DispatchResult:
    """
    Send a claim response email with idempotency protection.

    send_mode:
    - gmail_api
    - smtp
    - manual (no send)
    """
    mode = (send_mode or "manual").strip().lower()
    claim_id = (state.get("claim_id") or "UNKNOWN").strip()
    email_id = (state.get("email_id") or "").strip()
    fallback_subject = f"Warranty Claim Update - {claim_id}"

    draft = _load_email_draft(state)
    subject, body = _parse_subject_and_body(draft, fallback_subject)
    recipient = _recipient_from_state(state)
    sender = (os.getenv("EMAIL_FROM") or os.getenv("SMTP_FROM") or "warranty@hairtechind.com").strip()
    attachments = _collect_attachments(state)

    payload_hash = _payload_hash(recipient, subject, body, attachments)
    dispatch_key = f"{claim_id}:{payload_hash}"

    existing = get_dispatch_by_key(dispatch_key)
    if existing and existing.get("status") == "SENT":
        return DispatchResult(
            ok=True,
            status="SENT_DUPLICATE_SKIPPED",
            provider=existing.get("provider") or mode,
            dispatch_key=dispatch_key,
            recipient=recipient,
            subject=subject,
            message_id=existing.get("message_id") or "",
            error="",
            duplicate=True,
        )

    if not recipient:
        err = "No recipient email found in claim state."
        record_email_dispatch(
            dispatch_key=dispatch_key,
            email_id=email_id,
            claim_id=claim_id,
            provider=mode,
            recipient=recipient,
            subject=subject,
            payload_hash=payload_hash,
            status="FAILED",
            error=err,
            metadata={"mode": mode},
        )
        return DispatchResult(
            ok=False,
            status="FAILED",
            provider=mode,
            dispatch_key=dispatch_key,
            recipient=recipient,
            subject=subject,
            message_id="",
            error=err,
            duplicate=False,
        )

    if mode in ("manual", "demo", ""):
        record_email_dispatch(
            dispatch_key=dispatch_key,
            email_id=email_id,
            claim_id=claim_id,
            provider="manual",
            recipient=recipient,
            subject=subject,
            payload_hash=payload_hash,
            status="SKIPPED",
            metadata={"reason": "manual_mode"},
        )
        return DispatchResult(
            ok=True,
            status="SKIPPED",
            provider="manual",
            dispatch_key=dispatch_key,
            recipient=recipient,
            subject=subject,
            message_id="",
            error="",
            duplicate=False,
        )

    try:
        if mode == "gmail_api":
            if gmail_service is None:
                raise RuntimeError("Gmail service is not connected.")
            message_id = _send_gmail_api(
                gmail_service,
                sender=sender,
                recipient=recipient,
                subject=subject,
                body=body,
                attachments=attachments,
            )
            provider = "gmail_api"
        elif mode == "smtp":
            message_id = _send_smtp(
                sender=sender,
                recipient=recipient,
                subject=subject,
                body=body,
                attachments=attachments,
            )
            provider = "smtp"
        else:
            raise RuntimeError(f"Unsupported send mode: {mode}")

        record_email_dispatch(
            dispatch_key=dispatch_key,
            email_id=email_id,
            claim_id=claim_id,
            provider=provider,
            recipient=recipient,
            subject=subject,
            payload_hash=payload_hash,
            status="SENT",
            message_id=message_id,
            metadata={
                "attachments": [p.name for p in attachments],
                "mode": mode,
            },
        )

        return DispatchResult(
            ok=True,
            status="SENT",
            provider=provider,
            dispatch_key=dispatch_key,
            recipient=recipient,
            subject=subject,
            message_id=message_id,
            error="",
            duplicate=False,
        )

    except Exception as e:
        err = str(e)
        record_email_dispatch(
            dispatch_key=dispatch_key,
            email_id=email_id,
            claim_id=claim_id,
            provider=mode,
            recipient=recipient,
            subject=subject,
            payload_hash=payload_hash,
            status="FAILED",
            error=err,
            metadata={"mode": mode},
        )
        return DispatchResult(
            ok=False,
            status="FAILED",
            provider=mode,
            dispatch_key=dispatch_key,
            recipient=recipient,
            subject=subject,
            message_id="",
            error=err,
            duplicate=False,
        )

