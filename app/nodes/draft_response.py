"""
Node 9: Draft Customer Response

Generates appropriate customer response email based on decision.
"""

import json
import re
from pathlib import Path
from datetime import datetime
from app.state import ClaimState
from app.llm import get_llm


BASE_DIR = Path(__file__).parent.parent.parent
OUTBOX_DIR = BASE_DIR / "outbox" / "emails"


APPROVAL_TEMPLATE = """Subject: Your Warranty Claim Has Been Approved - {claim_id}

Dear {customer_name},

Thank you for contacting HairTech Industries regarding your warranty claim for the {product_name}.

We are pleased to inform you that your warranty claim has been APPROVED.

CLAIM DETAILS:
- Claim ID: {claim_id}
- Product: {product_name}
- Issue: {issue_summary}

NEXT STEPS:
{label_notice}
2. Please pack your {product_name} securely in its original packaging if available
3. Drop off the package at any authorized shipping location
4. Once we receive your product, we will process your {resolution} within 5-7 business days

IMPORTANT:
- Please include a copy of this email in your package
- Keep your tracking number for reference
- Do not include any accessories unless specifically requested

If you have any questions, please reply to this email or call us at 1-800-HAIRTECH.

Thank you for choosing HairTech Industries!

Best regards,
HairTech Customer Support Team
warranty@hairtechind.com
"""

REJECTION_TEMPLATE = """Subject: Regarding Your Warranty Claim - {claim_id}

Dear {customer_name},

Thank you for contacting HairTech Industries regarding your warranty claim for the {product_name}.

After careful review, we regret to inform you that your warranty claim cannot be approved at this time.

CLAIM DETAILS:
- Claim ID: {claim_id}
- Product: {product_name}
- Issue: {issue_summary}

REASON FOR DECISION:
{rejection_reason}

POLICY REFERENCE:
{policy_reference}

YOUR OPTIONS:
1. Out-of-Warranty Repair: We offer repair services at a reduced cost. Contact us for a quote.
2. Replacement Discount: Use code LOYAL20 for 20% off a new {product_name}.
3. Appeal: If you believe this decision was made in error, you may submit additional documentation.

To appeal this decision, please reply to this email with any additional evidence or clarification within 14 days.

We value your business and hope to serve you again in the future.

Best regards,
HairTech Customer Support Team
warranty@hairtechind.com
"""

NEED_INFO_TEMPLATE = """Subject: Additional Information Needed for Your Warranty Claim - {claim_id}

Dear {customer_name},

Thank you for contacting HairTech Industries regarding your warranty claim.

To process your claim, we need some additional information:

MISSING INFORMATION:
{missing_items}

WHAT YOU'VE PROVIDED:
- Product: {product_name}
- Issue: {issue_summary}

HOW TO RESPOND:
Please reply to this email with the missing information listed above. You can also attach any relevant documents such as:
- Proof of purchase (receipt, order confirmation, credit card statement)
- Photos of the product defect
- Product serial number (usually found on the handle or base)

Once we receive the complete information, we will process your claim within 2-3 business days.

If you have any questions, please don't hesitate to reach out.

Best regards,
HairTech Customer Support Team
warranty@hairtechind.com
"""

NON_CLAIM_TEMPLATE = """Subject: Thank You for Contacting HairTech Industries - {claim_id}

Dear {customer_name},

Thank you for reaching out to HairTech Industries!

We've received your inquiry regarding {subject_summary}. Since this doesn't appear to be a warranty-related request, we'd like to direct you to the appropriate team who can best assist you.

FOR PRODUCT INQUIRIES:
- Visit our product catalog at www.hairtechind.com/products
- Email our sales team at sales@hairtechind.com
- Call 1-800-HAIRTECH (option 2) for product recommendations

FOR GENERAL SUPPORT:
- Check our FAQ at www.hairtechind.com/faq
- Email support@hairtechind.com
- Live chat available at www.hairtechind.com (Mon-Fri, 9am-6pm EST)

FOR WARRANTY CLAIMS:
If you do have a warranty-related issue with a HairTech product, please reply to this email with:
- Your product name and serial number
- Date and place of purchase
- Description of the issue you're experiencing

We're here to help and appreciate your interest in HairTech products!

Best regards,
HairTech Customer Support Team
warranty@hairtechind.com
"""


def generate_llm_response(state: ClaimState, decision: str) -> str:
    """Use LLM to generate a personalized response."""
    try:
        llm = get_llm()
        
        extracted = state.get("extracted_fields", {})
        analysis = state.get("analysis", {})
        
        prompt = f"""Generate a professional customer service email for a warranty claim.

Decision: {decision}
Customer Name: {extracted.get('customer_name', 'Valued Customer')}
Product: {state.get('product_name', 'HairTech Product')}
Issue: {extracted.get('issue_description', 'Product issue')}
Reasoning: {analysis.get('reasoning', '')}
Exclusions: {', '.join(analysis.get('exclusions_triggered', []))}
Missing Info: {', '.join(extracted.get('missing_fields', []))}

Write a professional, empathetic email that:
1. Addresses the customer by name
2. Clearly states the decision
3. Provides clear next steps
4. Maintains a helpful, professional tone

Return ONLY the email body (no JSON), starting with 'Dear'."""

        return llm.generate(prompt, temperature=0.4)
    except Exception:
        return None


def draft_customer_response(state: ClaimState) -> ClaimState:
    """
    Draft the customer response email based on human decision.
    
    Args:
        state: Current workflow state with human decision
        
    Returns:
        Updated state with customer email draft
    """
    decision = state.get("human_decision", "NEED_INFO")
    claim_id = state.get("claim_id", "UNKNOWN")
    extracted = state.get("extracted_fields", {})
    analysis = state.get("analysis", {})
    
    customer_name = extracted.get("customer_name") or "Valued Customer"
    product_name = state.get("product_name") or extracted.get("product_name") or "HairTech Product"
    issue_summary = extracted.get("issue_description", "Product issue")[:100]
    
    if decision == "APPROVE":
        # Dynamic label notice
        label_notice = ""
        if state.get("return_label_path") or True: # Force notice for approve as it will be generated
             label_notice = "1. A prepaid return shipping label is attached to this email"
        else:
             label_notice = "1. Our team will follow up with return shipping instructions"

        email_content = APPROVAL_TEMPLATE.format(
            claim_id=claim_id,
            customer_name=customer_name,
            product_name=product_name,
            issue_summary=issue_summary,
            resolution="replacement",
            label_notice=label_notice
        )
        
    elif decision == "REJECT":
        rejection_reason = analysis.get("reasoning", "Based on our warranty policy review.")
        
        exclusions = analysis.get("exclusions_triggered", [])
        policy_refs = analysis.get("policy_references", [])
        policy_reference = ", ".join(policy_refs) if policy_refs else "Standard warranty terms"
        
        if exclusions:
            rejection_reason = f"{rejection_reason}\n\nExclusions that apply:\n- " + "\n- ".join(exclusions)
        
        email_content = REJECTION_TEMPLATE.format(
            claim_id=claim_id,
            customer_name=customer_name,
            product_name=product_name,
            issue_summary=issue_summary,
            rejection_reason=rejection_reason,
            policy_reference=policy_reference
        )
        
    else:  # NEED_INFO
        missing = extracted.get("missing_fields", [])
        if not missing:
            missing = ["Additional details about the issue", "Proof of purchase"]
        
        missing_items = "\n".join(f"- {item}" for item in missing)
        
        email_content = NEED_INFO_TEMPLATE.format(
            claim_id=claim_id,
            customer_name=customer_name,
            product_name=product_name,
            issue_summary=issue_summary if issue_summary else "Not yet provided",
            missing_items=missing_items
        )
    
    # Ensure output directory exists
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save email draft
    email_path = OUTBOX_DIR / f"{claim_id}.txt"
    with open(email_path, "w", encoding="utf-8") as f:
        f.write(email_content)
    
    return {
        **state,
        "customer_email_draft": email_content,
        "customer_email_path": str(email_path)
    }


def draft_non_claim_response(claim_id: str, customer_name: str, email_subject: str, email_from: str) -> dict:
    """
    Draft a response for non-claim emails (product inquiries, general questions).
    
    Args:
        claim_id: The claim/email ID
        customer_name: Customer name or 'Valued Customer'
        email_subject: Original email subject
        email_from: Customer's email address
        
    Returns:
        Dict with email_content and email_path
    """
    customer_name = customer_name or "Valued Customer"
    subject_summary = email_subject[:50] if email_subject else "your inquiry"
    
    email_content = NON_CLAIM_TEMPLATE.format(
        claim_id=claim_id,
        customer_name=customer_name,
        subject_summary=subject_summary
    )
    
    # Ensure output directory exists
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save email draft
    email_path = OUTBOX_DIR / f"{claim_id}_non_claim.txt"
    with open(email_path, "w", encoding="utf-8") as f:
        f.write(email_content)
    
    return {
        "email_content": email_content,
        "email_path": str(email_path),
        "to": email_from
    }
