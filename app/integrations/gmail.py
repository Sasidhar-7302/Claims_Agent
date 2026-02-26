"""
Gmail integration (OAuth + message fetch).

This module is intentionally minimal and focused on:
- Authenticating via OAuth (installed app flow).
- Listing messages by query.
- Fetching a message and extracting a best-effort plain text body.

Tokens are stored locally in an untracked path (recommended: under outbox/).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]


@dataclass(frozen=True)
class GmailMessage:
    message_id: str
    thread_id: str
    email_from: str
    email_to: str
    subject: str
    date: str
    body: str
    attachments: List[str]


def _decode_b64url(data: str) -> str:
    if not data:
        return ""
    raw = base64.urlsafe_b64decode(data.encode("utf-8"))
    return raw.decode("utf-8", errors="replace")


def _header_map(headers: List[Dict[str, str]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for h in headers or []:
        name = (h.get("name") or "").strip().lower()
        value = (h.get("value") or "").strip()
        if name and value:
            out[name] = value
    return out


def _walk_parts(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    parts = []
    stack = [payload] if payload else []
    while stack:
        node = stack.pop()
        parts.append(node)
        for child in node.get("parts") or []:
            stack.append(child)
    return parts


def _extract_body_and_attachments(payload: Dict[str, Any]) -> Tuple[str, List[str]]:
    body = ""
    attachments: List[str] = []
    parts = _walk_parts(payload)

    # Prefer text/plain, fall back to text/html.
    plain_candidates = []
    html_candidates = []

    for part in parts:
        filename = (part.get("filename") or "").strip()
        mime = (part.get("mimeType") or "").strip().lower()
        part_body = (part.get("body") or {})
        data = part_body.get("data")
        attachment_id = part_body.get("attachmentId")

        if filename and (attachment_id or (data and mime not in ("text/plain", "text/html"))):
            attachments.append(filename)

        if data and mime == "text/plain":
            plain_candidates.append(_decode_b64url(data))
        elif data and mime == "text/html":
            html_candidates.append(_decode_b64url(data))

    if plain_candidates:
        body = "\n\n".join([c.strip() for c in plain_candidates if c.strip()]).strip()
    elif html_candidates:
        # Best-effort: strip tags without external deps.
        html = "\n\n".join([c.strip() for c in html_candidates if c.strip()])
        body = _strip_html(html).strip()

    # Some messages store body directly on payload.body.data.
    if not body:
        direct = (payload.get("body") or {}).get("data")
        if direct:
            body = _decode_b64url(direct).strip()

    return body, attachments


def _strip_html(html: str) -> str:
    import re

    # Remove script/style and tags.
    html = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", html or "")
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;", " ", html, flags=re.IGNORECASE)
    html = re.sub(r"&amp;", "&", html, flags=re.IGNORECASE)
    html = re.sub(r"&lt;", "<", html, flags=re.IGNORECASE)
    html = re.sub(r"&gt;", ">", html, flags=re.IGNORECASE)
    html = re.sub(r"\\s+", " ", html)
    return html.strip()


def get_gmail_service(client_secrets_file: Path, token_file: Path, scopes: Optional[List[str]] = None) -> Any:
    """
    Authenticate and return a Gmail API service client.

    client_secrets_file: OAuth client secrets JSON (installed app).
    token_file: token JSON storage path (will be created/updated).
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    scopes = scopes or DEFAULT_SCOPES
    token_file.parent.mkdir(parents=True, exist_ok=True)

    creds: Optional[Credentials] = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes=scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_file), scopes=scopes)
            creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def list_message_ids(service: Any, query: str, max_results: int = 20, user_id: str = "me") -> List[str]:
    out: List[str] = []
    page_token = None
    while len(out) < max_results:
        req = service.users().messages().list(
            userId=user_id,
            q=query,
            maxResults=min(100, max_results - len(out)),
            pageToken=page_token,
        )
        resp = req.execute()
        out.extend([m.get("id") for m in (resp.get("messages") or []) if m.get("id")])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


def fetch_message(service: Any, message_id: str, user_id: str = "me") -> GmailMessage:
    msg = service.users().messages().get(userId=user_id, id=message_id, format="full").execute()
    payload = msg.get("payload") or {}
    headers = _header_map(payload.get("headers") or [])

    body, attachments = _extract_body_and_attachments(payload)
    if not body:
        body = (msg.get("snippet") or "").strip()

    return GmailMessage(
        message_id=msg.get("id") or message_id,
        thread_id=msg.get("threadId") or "",
        email_from=headers.get("from", ""),
        email_to=headers.get("to", ""),
        subject=headers.get("subject", ""),
        date=headers.get("date", ""),
        body=body,
        attachments=attachments,
    )

