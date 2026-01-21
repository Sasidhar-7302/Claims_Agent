"""
Node 8: Human Review Gate

This is where the workflow pauses for human review.
The actual pause is handled by LangGraph's interrupt_before.
This node processes the human decision after resume.
"""

from datetime import datetime
from app.state import ClaimState


def human_review_gate(state: ClaimState) -> ClaimState:
    """
    Process human review decision.
    
    This node is called AFTER the workflow resumes from the human review interrupt.
    The human decision should already be in the state from the resume input.
    
    Args:
        state: Current workflow state with human decision
        
    Returns:
        Updated state with review metadata
    """
    # Check if human decision was provided
    human_decision = state.get("human_decision")
    
    if not human_decision:
        # No decision provided - may need to default or error
        # This could happen if the workflow was resumed incorrectly
        analysis = state.get("analysis", {})
        recommended = analysis.get("recommendation", "NEED_INFO")
        
        return {
            **state,
            "human_decision": recommended,
            "human_notes": "Auto-accepted recommendation (no human input provided)",
            "human_reviewer": "system",
            "human_review_timestamp": datetime.now().isoformat(),
            "workflow_status": "REVIEWED"
        }
    
    # Validate decision
    valid_decisions = ["APPROVE", "REJECT", "NEED_INFO"]
    if human_decision.upper() not in valid_decisions:
        human_decision = "NEED_INFO"
    else:
        human_decision = human_decision.upper()
    
    # Record review timestamp if not already set
    timestamp = state.get("human_review_timestamp")
    if not timestamp:
        timestamp = datetime.now().isoformat()
    
    return {
        **state,
        "human_decision": human_decision,
        "human_review_timestamp": timestamp,
        "workflow_status": "REVIEWED"
    }
