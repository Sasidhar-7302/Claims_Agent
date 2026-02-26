"""
Node 1: Email Ingestion

Reads an email JSON file from the inbox and populates the state with raw email data.
"""

import json
from pathlib import Path
from app.state import ClaimState


# Base directories
BASE_DIR = Path(__file__).parent.parent.parent
INBOX_DIR = BASE_DIR / "data" / "inbox"


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
        return {
            **state,
            "email_attachments": attachments,
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
        
        return {
            **state,
            "email_id": email_data.get("email_id", email_id),
            "email_from": email_data.get("from", ""),
            "email_to": email_data.get("to", ""),
            "email_subject": email_data.get("subject", ""),
            "email_date": email_data.get("date", ""),
            "email_body": email_data.get("body", ""),
            "email_attachments": email_data.get("attachments", []),
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
