"""
Node: Email Gate

This node acts as an interrupt point before the final completion of the workflow.
It allows the user to review the drafted email (and attached label) and manually
trigger the "Send" action.
"""

from typing import Dict, Any
from app.state import ClaimState


def email_gate(state: ClaimState) -> Dict[str, Any]:
    """
    Pass-through node that serves as an interrupt point.
    
    This node doesn't modify state but allows LangGraph to pause
    so the user can review and edit the email before sending.
    """
    print(f"--- EMAIL GATE: Ready to send for claim {state.get('claim_id')} ---")
    
    # We don't change any state here, just return what we have.
    # The actual "sending" logic happens in the UI layer or a subsequent node
    # if we were to implement real SMTP sending.
    
    return {
        "workflow_status": "AWAITING_EMAIL"
    }
