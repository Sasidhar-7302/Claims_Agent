"""
Node 2: Email Triage

Classifies emails as CLAIM, NON_CLAIM, or SPAM using LLM.
"""

import json
import re
from app.state import ClaimState
from app.llm import get_llm


TRIAGE_PROMPT = """You are a warranty claims email classifier for HairTech Industries, a hair dryer manufacturer.

Analyze the following email and classify it into one of these categories:
1. CLAIM - A warranty claim or request for warranty service for a product defect
2. NON_CLAIM - A legitimate email but not a warranty claim (product inquiry, general question, feedback)
3. SPAM - Promotional, phishing, or irrelevant email

Email details:
From: {email_from}
Subject: {email_subject}
Date: {email_date}

Body:
{email_body}

Attachments: {attachments}

Respond with ONLY a JSON object in this exact format:
{{
    "classification": "CLAIM" or "NON_CLAIM" or "SPAM",
    "confidence": 0.0 to 1.0,
    "reason": "Brief explanation of classification"
}}"""


def triage_email(state: ClaimState) -> ClaimState:
    """
    Classify email as CLAIM, NON_CLAIM, or SPAM.
    
    Uses LLM for classification with cheap rule-based pre-filters.
    
    Args:
        state: Current workflow state with email data
        
    Returns:
        Updated state with triage result
    """
    # Check for error state
    if state.get("workflow_status") == "ERROR":
        return state
    
    email_body = state.get("email_body", "")
    email_subject = state.get("email_subject", "")
    email_from = state.get("email_from", "")
    
    # Quick rule-based spam detection
    spam_indicators = [
        "unsubscribe" in email_body.lower(),
        "click here" in email_body.lower() and "http" in email_body.lower(),
        "act now" in email_body.lower() or "act fast" in email_body.lower(),
        "wholesale" in email_body.lower() and "price" in email_body.lower(),
        "credit card" in email_body.lower() and "verify" in email_body.lower(),
        ".scam" in email_from.lower() or "fake" in email_from.lower(),
        email_body.count("!") > 10,  # Excessive exclamation marks
    ]
    
    if sum(spam_indicators) >= 2:
        return {
            **state,
            "triage_result": "SPAM",
            "triage_reason": "Multiple spam indicators detected",
            "triage_confidence": 0.95,
            "workflow_status": "TRIAGED"
        }
    
    # Use LLM for classification
    try:
        llm = get_llm()
        llm_model = getattr(llm, "model_name", "")
        
        prompt = TRIAGE_PROMPT.format(
            email_from=email_from,
            email_subject=email_subject,
            email_date=state.get("email_date", ""),
            email_body=email_body[:2000],  # Limit length
            attachments=", ".join(state.get("email_attachments", [])) or "None"
        )
        
        response = llm.generate_json(prompt)
        
        # Parse JSON response
        # Clean up response if needed
        response = response.strip()
        if response.startswith("```"):
            response = re.sub(r"```json?\s*", "", response)
            response = re.sub(r"```\s*$", "", response)
        
        result = json.loads(response)
        
        classification = result.get("classification", "CLAIM").upper()
        if classification not in ["CLAIM", "NON_CLAIM", "SPAM"]:
            classification = "CLAIM"  # Default to processing
        
        return {
            **state,
            "triage_result": classification,
            "triage_reason": result.get("reason", "LLM classification"),
            "triage_confidence": float(result.get("confidence", 0.8)),
            "llm_model": llm_model,
            "workflow_status": "TRIAGED"
        }
        
    except Exception as e:
        # On LLM error, default to processing as claim (conservative)
        return {
            **state,
            "triage_result": "CLAIM",
            "triage_reason": f"LLM error, defaulting to CLAIM: {e}",
            "triage_confidence": 0.5,
            "workflow_status": "TRIAGED"
        }
