"""
Node 11: Outbox Writer

Writes final artifacts and logs to the outbox.
Also updates customer email with label attachment info for approved claims.
"""

import json
from pathlib import Path
from datetime import datetime
from app.state import ClaimState


BASE_DIR = Path(__file__).parent.parent.parent
OUTBOX_DIR = BASE_DIR / "outbox"
LOGS_DIR = OUTBOX_DIR / "logs"


def write_to_outbox(state: ClaimState) -> ClaimState:
    """
    Write final artifacts and state log to outbox.
    
    Also updates customer email to reference the actual return label file
    for approved claims (since label is generated after email draft).
    
    Args:
        state: Final workflow state
        
    Returns:
        Updated state with completion status
    """
    claim_id = state.get("claim_id", "UNKNOWN")
    decision = state.get("human_decision", "")
    
    # Ensure logs directory exists
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    # For approved claims, update the customer email to include label attachment info
    if decision == "APPROVE" and state.get("return_label_path") and state.get("customer_email_path"):
        email_path = Path(state.get("customer_email_path"))
        label_path = state.get("return_label_path")
        
        if email_path.exists():
            try:
                with open(email_path, "r", encoding="utf-8") as f:
                    email_content = f.read()
                
                # Add attachment section to email
                attachment_section = f"""
---
ATTACHMENT: Return Shipping Label
- File: {Path(label_path).name}
- Location: {label_path}

Please print this label and attach it to your return package.
---
"""
                # Insert attachment info after the email header
                updated_email = email_content + attachment_section
                
                with open(email_path, "w", encoding="utf-8") as f:
                    f.write(updated_email)
                    
                print(f"[DEBUG] Updated email with label attachment: {label_path}")
            except Exception as e:
                print(f"[DEBUG] Error updating email with label: {e}")
    
    # Prepare audit log
    audit_log = {
        "claim_id": claim_id,
        "processing_started": state.get("processing_started"),
        "processing_completed": datetime.now().isoformat(),
        
        # Email metadata
        "email": {
            "id": state.get("email_id"),
            "from": state.get("email_from"),
            "subject": state.get("email_subject"),
            "date": state.get("email_date")
        },
        
        # Processing results
        "triage": {
            "result": state.get("triage_result"),
            "reason": state.get("triage_reason"),
            "confidence": state.get("triage_confidence")
        },
        
        "extraction": {
            "confidence": state.get("extraction_confidence"),
            "product_detected": state.get("extracted_fields", {}).get("product_name"),
            "missing_fields": state.get("extracted_fields", {}).get("missing_fields", [])
        },
        
        "product_match": {
            "product_id": state.get("product_id"),
            "product_name": state.get("product_name"),
            "policy_file": state.get("policy_file"),
            "match_confidence": state.get("product_match_confidence"),
            "selection_reason": state.get("policy_selection_reason")
        },

        "policy": {
            "policy_id": state.get("policy_id"),
            "policy_version": state.get("policy_version"),
            "policy_effective_date": state.get("policy_effective_date"),
            "policy_file": state.get("policy_file"),
            "retrieval": state.get("policy_retrieval", {})
        },

        "analysis": {
            "recommendation": state.get("analysis", {}).get("recommendation"),
            "confidence": state.get("analysis", {}).get("confidence"),
            "warranty_valid": state.get("analysis", {}).get("warranty_window_valid"),
            "exclusions": state.get("analysis", {}).get("exclusions_triggered", [])
        },

        "model": {
            "llm_model": state.get("llm_model")
        },
        
        "human_review": {
            "decision": state.get("human_decision"),
            "reviewer": state.get("human_reviewer"),
            "notes": state.get("human_notes"),
            "timestamp": state.get("human_review_timestamp")
        },
        
        "outputs": {
            "review_packet": state.get("review_packet_path"),
            "customer_email": state.get("customer_email_path"),
            "return_label": state.get("return_label_path"),
            "label_attached_to_email": decision == "APPROVE" and bool(state.get("return_label_path"))
        },
        
        "status": {
            "final_status": "COMPLETED",
            "error": state.get("error_message")
        }
    }
    
    # Write audit log
    log_path = LOGS_DIR / f"{claim_id}.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(audit_log, f, indent=2)
    
    # Create summary file
    summary_lines = [
        f"Claim Processing Summary: {claim_id}",
        f"=" * 50,
        f"",
        f"Status: COMPLETED",
        f"Decision: {state.get('human_decision', 'N/A')}",
        f"",
        f"Generated Files:",
    ]
    
    if state.get("review_packet_path"):
        summary_lines.append(f"  - Review Packet: {state.get('review_packet_path')}")
    if state.get("customer_email_path"):
        summary_lines.append(f"  - Customer Email: {state.get('customer_email_path')}")
    if state.get("return_label_path"):
        summary_lines.append(f"  - Return Label: {state.get('return_label_path')}")
    
    summary_lines.extend([
        f"  - Audit Log: {log_path}",
        f"",
        f"Processed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ])
    
    summary_path = OUTBOX_DIR / f"{claim_id}_summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines))
    
    return {
        **state,
        "workflow_status": "COMPLETED",
        "processing_completed": datetime.now().isoformat()
    }
