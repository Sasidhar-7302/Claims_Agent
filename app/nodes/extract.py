"""
Node 3: Field Extraction

Extracts structured warranty claim fields from email using LLM.
"""

import json
import re
from typing import List
from datetime import datetime
from app.state import ClaimState, ExtractedFields
from app.llm import get_llm


EXTRACTION_PROMPT = """You are extracting warranty claim information from an email for HairTech Industries.

Extract the following fields from the email.
- Look for the customer name in the email signature (e.g. "Sincerely, [Name]" or "Thanks, [Name]").
- Look for address/phone in the signature block.
- If a field is not clearly stated, set it to null.
- Do NOT infer the purchase date from the email 'Date' header. Only use dates explicitly mentioned in the body as the purchase date.


Email:
From: {email_from}
Subject: {email_subject}
Date: {email_date}

Body:
{email_body}

Attachments mentioned: {attachments}

Extract and respond with ONLY a JSON object in this exact format:
{{
    "customer_name": "Full name (check signature) or null",
    "customer_email": "Email address or null",
    "customer_phone": "Phone number or null",
    "customer_address": "Full address or null",
    "product_name": "Product name/model mentioned or null",
    "product_serial": "Serial number or null",
    "purchase_date": "YYYY-MM-DD format or null",
    "purchase_location": "Where purchased or null",
    "order_number": "Order/confirmation number or null",
    "issue_description": "Description of the problem or null",
    "has_proof_of_purchase": true or false,
    "missing_fields": ["list", "of", "missing", "required", "fields"]
}}

Required fields for a complete claim: customer_name, customer_email or customer_address, product_name, purchase_date, issue_description"""


def normalize_date(date_str: str) -> str:
    """Try to normalize a date string to YYYY-MM-DD format."""
    if not date_str:
        return None
    
    # Common date formats to try
    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
        "%d %b %Y",
        "%Y/%m/%d"
    ]
    
    for fmt in formats:
        try:
            parsed = datetime.strptime(date_str.strip(), fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    
    # Try to extract with regex patterns
    patterns = [
        r"(\d{4})-(\d{1,2})-(\d{1,2})",
        r"(\d{1,2})/(\d{1,2})/(\d{4})",
        r"(\w+)\s+(\d{1,2}),?\s+(\d{4})"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, date_str)
        if match:
            try:
                return normalize_date(match.group(0))
            except:
                continue
    
    return date_str  # Return as-is if normalization fails


def _is_iso_date(date_str: str) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", date_str or ""))


def normalize_phone(phone: str) -> str:
    """Normalize a phone number to ###-###-#### when possible."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"{digits[0:3]}-{digits[3:6]}-{digits[6:]}"
    return phone.strip()


def normalize_serial(serial: str) -> str:
    """Normalize serial numbers to uppercase alphanumerics with hyphens."""
    if not serial:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9-]", "", serial).upper()
    return cleaned or None


def normalize_address(address: str) -> str:
    """Normalize address spacing and line breaks."""
    if not address:
        return None
    parts = [line.strip() for line in address.splitlines() if line.strip()]
    joined = ", ".join(parts)
    joined = re.sub(r"\s{2,}", " ", joined)
    return joined.strip(" ,")


def extract_phone_from_text(text: str) -> str:
    """Extract a phone number from free-form text."""
    if not text:
        return None
    match = re.search(r"(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", text)
    if match:
        return normalize_phone(match.group(0))
    return None


def extract_serial_from_text(text: str) -> str:
    """Extract a serial number from free-form text."""
    if not text:
        return None
    match = re.search(r"(serial|s/n|sn|serial number)\s*[:#]?\s*([A-Za-z0-9-]{4,})", text, re.IGNORECASE)
    if match:
        return normalize_serial(match.group(2))
    return None


def extract_date_from_text(text: str) -> str:
    """Extract a date string from text and normalize it."""
    if not text:
        return None
    patterns = [
        r"\b\d{4}-\d{1,2}-\d{1,2}\b",
        r"\b\d{1,2}/\d{1,2}/\d{4}\b",
        r"\b\d{1,2}-\d{1,2}-\d{4}\b",
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b"
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            normalized = normalize_date(match.group(0))
            return normalized
    return None


def extract_address_from_text(text: str) -> str:
    """Extract a likely address from free-form text."""
    if not text:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    street_keywords = [
        "street", "st", "avenue", "ave", "road", "rd", "blvd", "boulevard",
        "lane", "ln", "drive", "dr", "court", "ct", "way", "circle", "cir", "parkway", "pkwy"
    ]

    def is_street_line(line: str) -> bool:
        lower = line.lower()
        return bool(re.search(r"\d{1,6}\s+\w+", line)) and any(
            re.search(rf"\b{kw}\b", lower) for kw in street_keywords
        )

    def is_city_state_line(line: str) -> bool:
        upper = line.upper()
        if re.search(r"\b[A-Z]{2}\b\s+\d{5}(-\d{4})?\b", upper):
            return True
        if re.search(r"\b\d{5}(-\d{4})?\b", upper) and re.search(r"[A-Z]", upper):
            return True
        return False

    for idx, line in enumerate(lines):
        if is_street_line(line):
            parts = [line]
            if idx + 1 < len(lines) and is_city_state_line(lines[idx + 1]):
                parts.append(lines[idx + 1])
            return normalize_address(", ".join(parts))

    for line in lines:
        if is_city_state_line(line):
            return normalize_address(line)

    return None


def identify_missing_fields(fields: dict) -> List[str]:
    """Identify which required fields are missing."""
    required = ["customer_name", "product_name", "purchase_date", "issue_description"]
    contact_fields = ["customer_email", "customer_address", "customer_phone"]
    
    missing = []
    
    for field in required:
        if not fields.get(field):
            missing.append(field)
    
    # Need at least one contact method
    has_contact = any(fields.get(f) for f in contact_fields)
    if not has_contact:
        missing.append("contact_info (email, phone, or address)")
    
    return missing


def extract_fields(state: ClaimState) -> ClaimState:
    """
    Extract structured fields from warranty claim email.
    
    Args:
        state: Current workflow state with email data
        
    Returns:
        Updated state with extracted fields
    """
    if state.get("workflow_status") == "ERROR":
        return state
    
    email_body = state.get("email_body", "")
    email_from = state.get("email_from", "")
    
    try:
        llm = get_llm()
        llm_model = getattr(llm, "model_name", "")
        
        prompt = EXTRACTION_PROMPT.format(
            email_from=email_from,
            email_subject=state.get("email_subject", ""),
            email_date=state.get("email_date", ""),
            email_body=email_body[:3000],
            attachments=", ".join(state.get("email_attachments", [])) or "None"
        )
        
        response = llm.generate_json(prompt)
        
        # Parse JSON response
        response = response.strip()
        if response.startswith("```"):
            response = re.sub(r"```json?\s*", "", response)
            response = re.sub(r"```\s*$", "", response)
        
        extracted = json.loads(response)
        
        # Post-processing
        # Use email_from if customer_email not found
        if not extracted.get("customer_email") and "@" in email_from:
            extracted["customer_email"] = email_from

        # Normalize known fields
        if extracted.get("customer_phone"):
            extracted["customer_phone"] = normalize_phone(extracted.get("customer_phone"))
        if extracted.get("product_serial"):
            extracted["product_serial"] = normalize_serial(extracted.get("product_serial"))
        if extracted.get("customer_address"):
            extracted["customer_address"] = normalize_address(extracted.get("customer_address"))
        
        # Normalize purchase date
        if extracted.get("purchase_date"):
            extracted["purchase_date"] = normalize_date(extracted["purchase_date"])
            if not _is_iso_date(extracted["purchase_date"]):
                fallback_date = extract_date_from_text(extracted["purchase_date"])
                if fallback_date:
                    extracted["purchase_date"] = fallback_date

        # Fallback extraction from email body if missing
        if not extracted.get("customer_phone"):
            extracted["customer_phone"] = extract_phone_from_text(email_body)
        if not extracted.get("product_serial"):
            extracted["product_serial"] = extract_serial_from_text(email_body)
        if not extracted.get("purchase_date"):
            extracted["purchase_date"] = extract_date_from_text(email_body)
        if not extracted.get("customer_address"):
            extracted["customer_address"] = extract_address_from_text(email_body)
        
        # Check for proof of purchase
        attachments = state.get("email_attachments", [])
        has_proof = extracted.get("has_proof_of_purchase", False)
        if not has_proof:
            proof_keywords = ["receipt", "order", "confirmation", "invoice"]
            has_proof = any(
                any(kw in att.lower() for kw in proof_keywords) 
                for att in attachments
            )
            if not has_proof:
                has_proof = bool(re.search(r"\b(receipt|order|confirmation|invoice|proof of purchase)\b", email_body.lower()))
        extracted["has_proof_of_purchase"] = has_proof
        
        # Normalize derived fields after fallback
        if extracted.get("customer_phone"):
            extracted["customer_phone"] = normalize_phone(extracted.get("customer_phone"))
        if extracted.get("product_serial"):
            extracted["product_serial"] = normalize_serial(extracted.get("product_serial"))
        if extracted.get("customer_address"):
            extracted["customer_address"] = normalize_address(extracted.get("customer_address"))
        if extracted.get("purchase_date"):
            extracted["purchase_date"] = normalize_date(extracted["purchase_date"])
        
        # Identify missing fields
        missing = identify_missing_fields(extracted)
        extracted["missing_fields"] = missing
        extracted["attachments"] = attachments
        
        # Calculate confidence based on completeness
        total_fields = 10
        filled_fields = sum(1 for k, v in extracted.items() 
                          if v and k not in ["missing_fields", "attachments", "has_proof_of_purchase"])
        confidence = filled_fields / total_fields
        
        return {
            **state,
            "extracted_fields": ExtractedFields(**extracted),
            "extraction_confidence": confidence,
            "llm_model": llm_model,
            "workflow_status": "EXTRACTED"
        }
        
    except Exception as e:
        return {
            **state,
            "extracted_fields": ExtractedFields(
                missing_fields=["extraction_failed"],
                has_proof_of_purchase=False,
                attachments=[]
            ),
            "extraction_confidence": 0.0,
            "workflow_status": "EXTRACTED",
            "error_message": f"Extraction error: {e}"
        }
