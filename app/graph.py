"""
LangGraph workflow definition for the Warranty Claims Agent.

This module defines the state graph that orchestrates the claim processing
workflow with human-in-the-loop review.
"""

from typing import Literal
from langgraph.graph import StateGraph, END

from app.state import ClaimState
from app.checkpointing import get_checkpointer

# Import all node functions
from app.nodes.ingest import ingest_email
from app.nodes.triage import triage_email
from app.nodes.extract import extract_fields
from app.nodes.product_policy import select_product_policy
from app.nodes.retrieve_policy import retrieve_policy_excerpts
from app.nodes.analyze import analyze_claim
from app.nodes.review_packet import build_review_packet
from app.nodes.human_gate import human_review_gate
from app.nodes.draft_response import draft_customer_response
from app.nodes.return_label import generate_return_label

from app.nodes.outbox import write_to_outbox
from app.nodes.email_gate import email_gate


def should_continue_after_triage(state: ClaimState) -> Literal["extract", "end"]:
    """Route after triage: continue processing claims, end for spam/non-claims."""
    if state.get("triage_result") == "CLAIM":
        return "extract"
    return "end"


def should_continue_after_analysis(state: ClaimState) -> Literal["review_packet", "draft_response"]:
    """Route after analysis: skip review packet if NEED_INFO with high confidence."""
    # Always go through review packet for human oversight
    return "review_packet"


def should_generate_label(state: ClaimState) -> Literal["return_label", "email_gate"]:
    """Route after draft: generate label only for approvals."""
    if state.get("human_decision") == "APPROVE":
        return "return_label"
    return "email_gate"


def create_workflow() -> StateGraph:
    """
    Create the warranty claims processing workflow.
    
    Workflow structure:
    1. ingest -> Read email from file
    2. triage -> Classify as CLAIM/NON_CLAIM/SPAM
    3. extract -> Extract structured fields (if CLAIM)
    4. select_policy -> Match product and load policy
    5. retrieve_excerpts -> Get relevant policy sections
    6. analyze -> Determine recommendation
    7. review_packet -> Generate human review document
    8. [INTERRUPT] human_review -> Wait for human decision
    9. draft_response -> Create customer email
    10. return_label -> Generate return label (if approved)
    10. return_label -> Generate return label (if approved)
    11. email_gate -> [INTERRUPT] Wait for user to send email
    12. outbox -> Write all outputs
    
    Returns:
        Compiled StateGraph with checkpointing enabled
    """
    
    # Create the workflow graph
    workflow = StateGraph(ClaimState)
    
    # Add all nodes
    workflow.add_node("ingest", ingest_email)
    workflow.add_node("triage", triage_email)
    workflow.add_node("extract", extract_fields)
    workflow.add_node("select_policy", select_product_policy)
    workflow.add_node("retrieve_excerpts", retrieve_policy_excerpts)
    workflow.add_node("analyze", analyze_claim)
    workflow.add_node("review_packet", build_review_packet)
    workflow.add_node("human_review", human_review_gate)
    workflow.add_node("draft_response", draft_customer_response)
    workflow.add_node("return_label", generate_return_label)

    workflow.add_node("email_gate", email_gate)
    workflow.add_node("outbox", write_to_outbox)
    
    # Define the flow
    workflow.set_entry_point("ingest")
    
    # Linear flow: ingest -> triage
    workflow.add_edge("ingest", "triage")
    
    # Conditional: triage -> extract (if CLAIM) or END (if SPAM/NON_CLAIM)
    workflow.add_conditional_edges(
        "triage",
        should_continue_after_triage,
        {
            "extract": "extract",
            "end": END
        }
    )
    
    # Linear flow through claim processing
    workflow.add_edge("extract", "select_policy")
    workflow.add_edge("select_policy", "retrieve_excerpts")
    workflow.add_edge("retrieve_excerpts", "analyze")
    workflow.add_edge("analyze", "review_packet")
    workflow.add_edge("review_packet", "human_review")
    
    # After human review, generate response
    workflow.add_edge("human_review", "draft_response")
    
    # Direct flow: draft -> email_gate
    # Label generation is now triggered manually in the UI
    workflow.add_edge("draft_response", "email_gate")
    
    # email_gate -> outbox -> END
    workflow.add_edge("email_gate", "outbox")
    workflow.add_edge("outbox", END)
    
    return workflow


def compile_workflow(checkpointer=None):
    """
    Compile the workflow with optional checkpointing.
    
    Args:
        checkpointer: Optional checkpointer for state persistence.
                      If None, uses in-memory checkpointing.
    
    Returns:
        Compiled workflow ready for execution
    """
    workflow = create_workflow()
    
    if checkpointer is None:
        checkpointer = get_checkpointer()
    
    # Compile with interrupt before human_review for pause/resume
    compiled = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review", "email_gate"]
    )
    
    return compiled


def get_workflow():
    """Get a ready-to-use compiled workflow instance."""
    return compile_workflow()


# For visualization/debugging
def visualize_workflow():
    """Generate a Mermaid diagram of the workflow."""
    workflow = create_workflow()
    try:
        return workflow.get_graph().draw_mermaid()
    except Exception as e:
        return f"Could not generate diagram: {e}"
