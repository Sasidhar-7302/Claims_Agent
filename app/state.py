"""
State definition for the Warranty Claims Agent workflow.

This module defines the ClaimState TypedDict that is passed between nodes
in the LangGraph workflow.
"""

from typing import TypedDict, Optional, List, Literal
from datetime import datetime


class ExtractedFields(TypedDict, total=False):
    """Structured fields extracted from warranty claim email."""
    customer_name: Optional[str]
    customer_email: Optional[str]
    customer_phone: Optional[str]
    customer_address: Optional[str]
    product_name: Optional[str]
    product_serial: Optional[str]
    purchase_date: Optional[str]
    purchase_location: Optional[str]
    order_number: Optional[str]
    issue_description: Optional[str]
    has_proof_of_purchase: bool
    attachments: List[str]
    missing_fields: List[str]


class PolicyExcerpt(TypedDict, total=False):
    """A section from a warranty policy document."""
    section_name: str
    content: str
    relevance: str
    policy_id: Optional[str]
    policy_file: Optional[str]
    chunk_index: Optional[int]
    distance: Optional[float]
    query: Optional[str]


class AnalysisResult(TypedDict, total=False):
    """Result of the warranty claim analysis."""
    recommendation: Literal["APPROVE", "REJECT", "NEED_INFO"]
    confidence: float  # 0.0 to 1.0
    facts: List[str]
    assumptions: List[str]
    reasoning: str
    policy_references: List[str]
    warranty_window_valid: Optional[bool]
    warranty_window_details: Optional[str]
    exclusions_triggered: List[str]


class ClaimState(TypedDict, total=False):
    """
    Complete state for a warranty claim as it moves through the workflow.
    
    This state is passed between all nodes in the LangGraph workflow and
    accumulates data as the claim is processed.
    """
    
    # Identification
    claim_id: str
    
    # Raw email data (from ingest node)
    email_id: str
    email_from: str
    email_to: str
    email_subject: str
    email_date: str
    email_body: str
    email_attachments: List[str]
    
    # Triage result (from triage node)
    triage_result: Literal["CLAIM", "NON_CLAIM", "SPAM"]
    triage_reason: str
    triage_confidence: float
    
    # Extracted fields (from extract node)
    extracted_fields: ExtractedFields
    extraction_confidence: float
    
    # Product and policy selection (from product_policy node)
    product_id: Optional[str]
    product_name: Optional[str]
    product_category: Optional[str]
    policy_file: Optional[str]
    policy_id: Optional[str]
    policy_version: Optional[str]
    policy_effective_date: Optional[str]
    policy_requirements: Optional[List[str]]
    policy_exclusion_keywords: Optional[List[str]]
    policy_selection_reason: str
    product_match_confidence: float
    
    # Policy excerpts (from retrieve_policy node)
    policy_excerpts: List[PolicyExcerpt]
    full_policy_text: Optional[str]
    policy_retrieval: Optional[dict]
    
    # Analysis result (from analyze node)
    analysis: AnalysisResult
    
    # Review packet path (from review_packet node)
    review_packet_path: Optional[str]
    review_packet_content: Optional[str]
    
    # Human decision (from human_gate node)
    human_decision: Optional[Literal["APPROVE", "REJECT", "NEED_INFO"]]
    human_notes: Optional[str]
    human_reviewer: Optional[str]
    human_review_timestamp: Optional[str]
    
    # Final outputs (from draft_response and return_label nodes)
    customer_email_draft: Optional[str]
    customer_email_path: Optional[str]
    return_label_path: Optional[str]
    email_sent: Optional[bool]
    final_email_body: Optional[str]
    
    # Workflow metadata
    workflow_status: Literal["PENDING", "TRIAGED", "EXTRACTED", "ANALYZED", 
                             "AWAITING_REVIEW", "REVIEWED", "COMPLETED", "ERROR"]
    error_message: Optional[str]
    processing_started: Optional[str]
    processing_completed: Optional[str]

    # LLM metadata
    llm_model: Optional[str]
    
    # For continuing workflow after human review
    messages: List[dict]  # LangGraph message history


def create_initial_state(email_id: str) -> ClaimState:
    """Create an initial empty state for a new claim."""
    return ClaimState(
        claim_id=f"CLM-{datetime.now().strftime('%Y%m%d%H%M%S')}-{email_id}",
        email_id=email_id,
        workflow_status="PENDING",
        processing_started=datetime.now().isoformat(),
        email_attachments=[],
        messages=[],
    )
