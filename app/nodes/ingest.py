"""
Node 1: Email Ingestion

Reads an email JSON file from the inbox and populates the state with raw email data.
"""

import json
from pathlib import Path
from app.state import ClaimState
from app.attachments import extract_attachment_bundle


# Base directories
BASE_DIR = Path(__file__).parent.parent.parent
INBOX_DIR = BASE_DIR / "data" / "inbox"


def _resolve_local_attachment_paths(email_id: str, attachments: list[str]) -> list[str]:
    """Best-effort resolution of local attachment file paths for demo inbox data."""
    paths: list[str] = []
    candidate_roots = [
        INBOX_DIR / "attachments" / email_id,
        INBOX_DIR / "attachments",
        INBOX_DIR,
    ]
    for name in attachments or []:
        for root in candidate_roots:
            candidate = root / name
            if candidate.exists() and candidate.is_file():
                paths.append(str(candidate))
                break
    return paths


def ingest_email(state: ClaimState) -> ClaimState:
    """
    Read email JSON from inbox and populate state.
    
    Args:
        state: Current workflow state with email_id set
        
    Returns:
        Updated state with raw email data
    """
    # If email content is already present (e.g. from a live connector), skip file ingestion.
    if state.get("email_body") and state.get("email_from") and state.get("email_subject"):
        attachments = state.get("email_attachments") or []
        attachment_paths = state.get("email_attachment_paths") or []
        attachment_text = state.get("email_attachment_text") or ""
        attachment_details = state.get("email_attachment_details") or []
        if attachment_paths and not attachment_text:
            attachment_text, attachment_details = extract_attachment_bundle(attachment_paths)
        return {
            **state,
            "email_attachments": attachments,
            "email_attachment_paths": attachment_paths,
            "email_attachment_text": attachment_text,
            "email_attachment_details": attachment_details,
            "workflow_status": "PENDING",
        }

    email_id = state.get("email_id", "")
    
    # Try to find the email file
    email_file = INBOX_DIR / f"{email_id}.json"
    
    if not email_file.exists():
        # Try without .json extension
        for f in INBOX_DIR.glob(f"*{email_id}*"):
            email_file = f
            break
    
    if not email_file.exists():
        return {
            **state,
            "workflow_status": "ERROR",
            "error_message": f"Email file not found: {email_id}"
        }
    
    try:
        with open(email_file, "r", encoding="utf-8") as f:
            email_data = json.load(f)
        
        attachment_paths = _resolve_local_attachment_paths(
            email_data.get("email_id", email_id),
            email_data.get("attachments", []),
        )
        attachment_text, attachment_details = extract_attachment_bundle(attachment_paths)

        return {
            **state,
            "email_id": email_data.get("email_id", email_id),
            "email_from": email_data.get("from", ""),
            "email_to": email_data.get("to", ""),
            "email_subject": email_data.get("subject", ""),
            "email_date": email_data.get("date", ""),
            "email_body": email_data.get("body", ""),
            "email_attachments": email_data.get("attachments", []),
            "email_attachment_paths": attachment_paths,
            "email_attachment_text": attachment_text,
            "email_attachment_details": attachment_details,
            "workflow_status": "PENDING"
        }
        
    except json.JSONDecodeError as e:
        return {
            **state,
            "workflow_status": "ERROR",
            "error_message": f"Invalid JSON in email file: {e}"
        }
    except Exception as e:
        return {
            **state,
            "workflow_status": "ERROR",
            "error_message": f"Error reading email: {e}"
        }
