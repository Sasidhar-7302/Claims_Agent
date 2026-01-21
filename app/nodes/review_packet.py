"""
Node 7: Review Packet Builder

Generates a human-readable review packet for the claim.
"""

from pathlib import Path
from datetime import datetime
from app.state import ClaimState


BASE_DIR = Path(__file__).parent.parent.parent
OUTBOX_DIR = BASE_DIR / "outbox" / "review_packets"


def build_review_packet(state: ClaimState) -> ClaimState:
    """
    Build a human review packet document.
    
    Creates a Markdown document with all claim details for human review.
    
    Args:
        state: Current workflow state with analysis
        
    Returns:
        Updated state with review packet path
    """
    if state.get("workflow_status") == "ERROR":
        return state
    
    claim_id = state.get("claim_id", "unknown")
    extracted = state.get("extracted_fields", {})
    analysis = state.get("analysis", {})
    
    # Build the review packet content
    lines = [
        f"# Warranty Claim Review Packet",
        f"",
        f"**Claim ID:** {claim_id}",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        "---",
        "",
        "## Recommendation Summary",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| **Recommendation** | **{analysis.get('recommendation', 'N/A')}** |",
        f"| **Confidence** | {analysis.get('confidence', 0):.0%} |",
        f"| **Warranty Valid** | {analysis.get('warranty_window_valid', 'Unknown')} |",
        "",
        "---",
        "",
        "## Customer Information",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Name | {extracted.get('customer_name', 'Not provided')} |",
        f"| Email | {extracted.get('customer_email', 'Not provided')} |",
        f"| Phone | {extracted.get('customer_phone', 'Not provided')} |",
        f"| Address | {extracted.get('customer_address', 'Not provided')} |",
        "",
        "---",
        "",
        "## Product & Purchase",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Product | {state.get('product_name', 'Unknown')} |",
        f"| Product ID | {state.get('product_id', 'Not matched')} |",
        f"| Category | {state.get('product_category', 'N/A')} |",
        f"| Serial | {extracted.get('product_serial', 'Not provided')} |",
        f"| Purchase Date | {extracted.get('purchase_date', 'Not provided')} |",
        f"| Purchase Location | {extracted.get('purchase_location', 'Not provided')} |",
        f"| Order Number | {extracted.get('order_number', 'Not provided')} |",
        f"| Proof of Purchase | {'Yes' if extracted.get('has_proof_of_purchase') else 'No'} |",
        "",
        "---",
        "",
        "## Issue Description",
        "",
        f"```",
        f"{extracted.get('issue_description', 'No description provided')}",
        f"```",
        "",
        "---",
        "",
        "## Warranty Window Analysis",
        "",
        f"{analysis.get('warranty_window_details', 'Warranty window not checked')}",
        "",
        "---",
        "",
        "## Evidence Checklist",
        "",
    ]
    
    # Add evidence checklist
    checklist = [
        ("Proof of Purchase", extracted.get('has_proof_of_purchase', False)),
        ("Serial Number", bool(extracted.get('product_serial'))),
        ("Purchase Date", bool(extracted.get('purchase_date'))),
        ("Issue Description", bool(extracted.get('issue_description'))),
        ("Contact Information", bool(extracted.get('customer_email') or extracted.get('customer_address'))),
    ]
    
    for item, present in checklist:
        checkbox = "[x]" if present else "[ ]"
        lines.append(f"- {checkbox} {item}")
    
    lines.extend([
        "",
        "---",
        "",
        "## Analysis Details",
        "",
        "### Facts (Verified)",
        "",
    ])
    
    for fact in analysis.get('facts', []):
        lines.append(f"- {fact}")
    
    if not analysis.get('facts'):
        lines.append("- No facts extracted")
    
    lines.extend([
        "",
        "### Assumptions (Not Verified)",
        "",
    ])
    
    for assumption in analysis.get('assumptions', []):
        lines.append(f"- [!] {assumption}")
    
    if not analysis.get('assumptions'):
        lines.append("- No assumptions made")
    
    lines.extend([
        "",
        "### Reasoning",
        "",
        f"{analysis.get('reasoning', 'No reasoning provided')}",
        "",
        "### Policy References",
        "",
    ])
    
    for ref in analysis.get('policy_references', []):
        lines.append(f"- {ref}")
    
    if not analysis.get('policy_references'):
        lines.append("- No policy sections referenced")
    
    # Exclusions triggered
    exclusions = analysis.get('exclusions_triggered', [])
    if exclusions:
        lines.extend([
            "",
            "### [WARNING] Exclusions Triggered",
            "",
        ])
        for exc in exclusions:
            lines.append(f"- **{exc}**")
    
    lines.extend([
        "",
        "---",
        "",
        "## Policy Selected",
        "",
        f"**Policy ID:** {state.get('policy_id', 'None')}",
        f"**Version:** {state.get('policy_version', 'N/A')}",
        f"**Effective Date:** {state.get('policy_effective_date', 'N/A')}",
        f"**File:** {state.get('policy_file', 'None')}",
        f"",
        f"**Reason:** {state.get('policy_selection_reason', 'N/A')}",
        "",
    ])
    
    # Add policy excerpts
    excerpts = state.get('policy_excerpts', [])
    if excerpts:
        lines.extend([
            "### Relevant Policy Excerpts",
            "",
        ])
        for excerpt in excerpts:
            policy_id = excerpt.get("policy_id", "N/A")
            policy_file = excerpt.get("policy_file", "N/A")
            chunk_index = excerpt.get("chunk_index", "N/A")
            distance = excerpt.get("distance", "N/A")
            query = excerpt.get("query", "N/A")
            lines.extend([
                f"#### {excerpt.get('section_name', 'Unknown Section')}",
                "",
                f"Source: {policy_id} | File: {policy_file} | Chunk: {chunk_index} | Distance: {distance} | Query: {query}",
                "",
                f"```",
                f"{excerpt.get('content', '')[:500]}",
                f"```",
                "",
            ])
    
    lines.extend([
        "---",
        "",
        "## Original Email",
        "",
        f"**From:** {state.get('email_from', 'Unknown')}",
        f"**Subject:** {state.get('email_subject', 'No subject')}",
        f"**Date:** {state.get('email_date', 'Unknown')}",
        "",
        "```",
        state.get('email_body', 'No body')[:2000],
        "```",
        "",
        "---",
        "",
        "## Human Review Required",
        "",
        "Please review this claim and select an action:",
        "",
        "- [ ] **APPROVE** - Issue replacement/repair/refund",
        "- [ ] **REJECT** - Deny claim with explanation",
        "- [ ] **NEED_INFO** - Request additional information",
        "",
    ])
    
    # Missing fields if any
    missing = extracted.get('missing_fields', [])
    if missing:
        lines.extend([
            "### Missing Information",
            "",
        ])
        for field in missing:
            lines.append(f"- {field}")
    
    # Combine all lines
    content = "\n".join(lines)
    
    # Ensure output directory exists
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    
    # Write the packet
    packet_path = OUTBOX_DIR / f"{claim_id}.md"
    with open(packet_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    return {
        **state,
        "review_packet_path": str(packet_path),
        "review_packet_content": content,
        "workflow_status": "AWAITING_REVIEW"
    }
