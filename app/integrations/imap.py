"""
Generic IMAP integration for enterprise mailbox onboarding.

Supports:
- Connecting to any IMAP-compatible provider (Outlook, Zoho, custom hosts, etc.).
- Listing message UIDs by IMAP search query.
- Fetching message headers/body and optional attachments.
- Marking messages as read after successful processing.
"""

from __future__ import annotations

import hashlib
import imaplib
import re
import shlex
from contextlib import contextmanager
from dataclasses import dataclass, field
from email import message_from_bytes
from email.header import decode_header
from email.message import Message
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple


@dataclass(frozen=True)
class ImapConfig:
    host: str
    port: int = 993
    username: str = ""
    password: str = ""
    folder: str = "INBOX"
    query: str = "UNSEEN"
    use_ssl: bool = True


@dataclass(frozen=True)
class ImapMessage:
    email_id: str
    uid: str
    message_id_header: str
    email_from: str
    email_to: str
    subject: str
    date: str
    body: str
    attachments: List[str]
    attachment_paths: List[str] = field(default_factory=list)


def _decode_header_value(value: str) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out: List[str] = []
    for chunk, encoding in parts:
        if isinstance(chunk, bytes):
            enc = encoding or "utf-8"
            try:
                out.append(chunk.decode(enc, errors="replace"))
            except Exception:
                out.append(chunk.decode("utf-8", errors="replace"))
        else:
            out.append(str(chunk))
    return "".join(out).strip()


def _strip_html(html: str) -> str:
    import re

    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html or "")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"&amp;", "&", text, flags=re.IGNORECASE)
    text = re.sub(r"&lt;", "<", text, flags=re.IGNORECASE)
    text = re.sub(r"&gt;", ">", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _message_text_part(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        raw = part.get_payload()
        if isinstance(raw, str):
            return raw.strip()
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace").strip()
    except Exception:
        return payload.decode("utf-8", errors="replace").strip()


def _extract_body_and_attachment_parts(msg: Message) -> Tuple[str, List[Message]]:
    body_plain: List[str] = []
    body_html: List[str] = []
    attachments: List[Message] = []

    if msg.is_multipart():
        parts = list(msg.walk())
    else:
        parts = [msg]

    for part in parts:
        content_type = (part.get_content_type() or "").lower()
        disposition = (part.get("Content-Disposition") or "").lower()
        filename = part.get_filename()

        if filename:
            attachments.append(part)
            continue
        if "attachment" in disposition:
            attachments.append(part)
            continue
        if content_type == "text/plain":
            text = _message_text_part(part)
            if text:
                body_plain.append(text)
        elif content_type == "text/html":
            html = _message_text_part(part)
            if html:
                body_html.append(html)

    if body_plain:
        return "\n\n".join([b for b in body_plain if b]).strip(), attachments
    if body_html:
        joined = "\n\n".join([h for h in body_html if h]).strip()
        return _strip_html(joined), attachments

    # Fallback for non-multipart plain emails.
    if not msg.is_multipart():
        raw = _message_text_part(msg)
        if raw:
            return raw, attachments

    return "", attachments


def _fingerprint(host: str, username: str, folder: str) -> str:
    payload = f"{(host or '').strip().lower()}|{(username or '').strip().lower()}|{(folder or '').strip().upper()}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]


def build_imap_email_id(uid: str, host: str, username: str, folder: str) -> str:
    safe_uid = re.sub(r"[^0-9A-Za-z]+", "", (uid or "").strip()) or "0"
    return f"imap_{_fingerprint(host, username, folder)}_{safe_uid}"


def parse_imap_email_id(email_id: str) -> Optional[str]:
    if not email_id:
        return None
    match = re.match(r"^imap_[0-9a-f]{8}_([0-9A-Za-z]+)$", email_id.strip())
    if not match:
        return None
    return match.group(1)


def _extract_raw_fetch_bytes(fetch_resp: List[Any]) -> bytes:
    for item in fetch_resp or []:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
            return bytes(item[1])
    return b""


def parse_raw_message(
    raw_bytes: bytes,
    uid: str,
    config: ImapConfig,
    download_attachments: bool = False,
    attachment_dir: Optional[Path] = None,
) -> ImapMessage:
    msg = message_from_bytes(raw_bytes)
    body, attachment_parts = _extract_body_and_attachment_parts(msg)

    from app.attachments import save_attachment_bytes

    attachment_names: List[str] = []
    attachment_paths: List[str] = []

    for part in attachment_parts:
        filename_raw = part.get_filename() or "attachment.bin"
        filename = _decode_header_value(filename_raw) or "attachment.bin"
        attachment_names.append(filename)

        if download_attachments:
            try:
                payload = part.get_payload(decode=True)
                if payload:
                    # save_attachment_bytes handles path sanitization and dedupe.
                    path = save_attachment_bytes(
                        build_imap_email_id(uid, config.host, config.username, config.folder),
                        filename,
                        payload,
                    )
                    attachment_paths.append(str(path))
            except Exception:
                continue

    email_id = build_imap_email_id(uid, config.host, config.username, config.folder)
    message_id_header = _decode_header_value(msg.get("Message-ID", ""))

    return ImapMessage(
        email_id=email_id,
        uid=uid,
        message_id_header=message_id_header,
        email_from=_decode_header_value(msg.get("From", "")),
        email_to=_decode_header_value(msg.get("To", "")),
        subject=_decode_header_value(msg.get("Subject", "")),
        date=_decode_header_value(msg.get("Date", "")),
        body=body or "",
        attachments=attachment_names,
        attachment_paths=attachment_paths,
    )


def _normalize_query(query: str) -> str:
    q = (query or "").strip()
    return q or "UNSEEN"


def _query_tokens(query: str) -> List[str]:
    normalized = _normalize_query(query)
    try:
        tokens = shlex.split(normalized)
    except Exception:
        tokens = [normalized]
    return tokens or ["UNSEEN"]


@contextmanager
def _imap_session(config: ImapConfig) -> Generator[imaplib.IMAP4, None, None]:
    if not config.host.strip():
        raise RuntimeError("IMAP host is required.")
    if not config.username.strip():
        raise RuntimeError("IMAP username is required.")
    if not config.password:
        raise RuntimeError("IMAP password is required.")

    if config.use_ssl:
        client: imaplib.IMAP4 = imaplib.IMAP4_SSL(config.host, config.port)
    else:
        client = imaplib.IMAP4(config.host, config.port)

    try:
        login_type, login_data = client.login(config.username, config.password)
        if login_type != "OK":
            raise RuntimeError(f"IMAP login failed: {login_data}")
        select_type, select_data = client.select(config.folder or "INBOX")
        if select_type != "OK":
            raise RuntimeError(f"Could not open mailbox folder '{config.folder}': {select_data}")
        yield client
    finally:
        try:
            client.close()
        except Exception:
            pass
        try:
            client.logout()
        except Exception:
            pass


def test_connection(config: ImapConfig) -> Tuple[bool, str]:
    try:
        with _imap_session(config) as client:
            status, data = client.noop()
            if status != "OK":
                return False, f"IMAP NOOP failed: {data}"
        return True, "Connected successfully."
    except Exception as e:
        return False, str(e)


def list_message_uids(config: ImapConfig, max_results: int = 25) -> List[str]:
    tokens = _query_tokens(config.query)
    with _imap_session(config) as client:
        status, data = client.uid("search", None, *tokens)
        if status != "OK":
            raise RuntimeError(f"IMAP search failed: {data}")
        raw = data[0] if data else b""
        if isinstance(raw, bytes):
            uids = raw.decode("utf-8", errors="replace").split()
        else:
            uids = str(raw or "").split()
        uids = [u.strip() for u in uids if u and u.strip()]
        # Most recent messages are usually at the end of the UID list.
        uids.reverse()
        return uids[:max(max_results, 0)]


def _fetch_message_with_client(
    client: imaplib.IMAP4,
    config: ImapConfig,
    uid: str,
    download_attachments: bool = False,
    attachment_dir: Optional[Path] = None,
) -> ImapMessage:
    status, data = client.uid("fetch", uid, "(RFC822)")
    if status != "OK":
        raise RuntimeError(f"IMAP fetch failed for UID {uid}: {data}")
    raw = _extract_raw_fetch_bytes(data or [])
    if not raw:
        raise RuntimeError(f"No message payload found for UID {uid}.")
    return parse_raw_message(
        raw,
        uid=uid,
        config=config,
        download_attachments=download_attachments,
        attachment_dir=attachment_dir,
    )


def fetch_message(
    config: ImapConfig,
    uid: str,
    download_attachments: bool = False,
    attachment_dir: Optional[Path] = None,
) -> ImapMessage:
    with _imap_session(config) as client:
        return _fetch_message_with_client(
            client,
            config,
            uid=uid,
            download_attachments=download_attachments,
            attachment_dir=attachment_dir,
        )


def list_messages(config: ImapConfig, max_results: int = 25) -> List[ImapMessage]:
    tokens = _query_tokens(config.query)
    with _imap_session(config) as client:
        status, data = client.uid("search", None, *tokens)
        if status != "OK":
            raise RuntimeError(f"IMAP search failed: {data}")
        raw = data[0] if data else b""
        if isinstance(raw, bytes):
            uids = raw.decode("utf-8", errors="replace").split()
        else:
            uids = str(raw or "").split()
        uids = [u.strip() for u in uids if u and u.strip()]
        uids.reverse()
        selected = uids[:max(max_results, 0)]

        out: List[ImapMessage] = []
        for uid in selected:
            try:
                out.append(_fetch_message_with_client(client, config, uid))
            except Exception:
                continue
        return out


def mark_message_read(config: ImapConfig, uid: str) -> None:
    with _imap_session(config) as client:
        status, data = client.uid("store", uid, "+FLAGS", r"(\Seen)")
        if status != "OK":
            raise RuntimeError(f"IMAP mark-read failed for UID {uid}: {data}")
