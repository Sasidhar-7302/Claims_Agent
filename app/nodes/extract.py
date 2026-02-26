"""
Node 3: Field Extraction

Extracts structured warranty claim fields from email using LLM.
"""

import json
import os
import re
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from app.state import ClaimState, ExtractedFields
from app.llm import get_llm
from app.product_catalog import load_products_catalog


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

def _load_products() -> List[Dict[str, Any]]:
    try:
        data = load_products_catalog()
        return data.get("products", []) or []
    except Exception:
        return []


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _find_product_in_text(text: str) -> Optional[str]:
    """Best-effort product detection using the local product catalog."""
    haystack = _norm(text)
    if not haystack:
        return None

    best: Tuple[Optional[str], int] = (None, 0)
    for product in _load_products():
        names = [product.get("name", "")] + list(product.get("aliases", []) or [])
        for name in names:
            needle = _norm(name)
            if not needle:
                continue
            if needle in haystack:
                if len(needle) > best[1]:
                    best = (product.get("name") or name, len(needle))

    return best[0]


def _extract_customer_name_from_signature(body: str) -> Optional[str]:
    if not body:
        return None
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    if not lines:
        return None

    markers = ("thanks", "thank you", "sincerely", "regards", "best", "cheers")
    for idx, line in enumerate(lines):
        low = line.lower().strip(" :,")
        if any(low.startswith(m) or low == m for m in markers):
            if idx + 1 < len(lines):
                candidate = lines[idx + 1].strip(" ,")
                if 1 <= len(candidate) <= 60 and "@" not in candidate and not re.search(r"\d", candidate):
                    return candidate
    # Fallback: last line if it looks like a name.
    tail = lines[-1].strip(" ,")
    if 1 <= len(tail) <= 60 and "@" not in tail and not re.search(r"\d", tail):
        return tail
    return None


def _extract_order_number_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    # Common order/confirmation formats (Amazon-like, numeric, etc.)
    match = re.search(r"\b(order number|order|confirmation)\s*[:#]?\s*([A-Za-z0-9-]{6,})\b", text, re.IGNORECASE)
    if match:
        return match.group(2).strip()
    match2 = re.search(r"\b\d{3}-\d{7}-\d{7}\b", text)
    if match2:
        return match2.group(0)
    return None


def _deterministic_extract(state: ClaimState) -> Dict[str, Any]:
    """Deterministic extraction for demo mode and as a fallback when LLMs fail."""
    email_body = state.get("email_body", "") or ""
    attachment_text = state.get("email_attachment_text", "") or ""
    email_from = state.get("email_from", "") or ""
    attachments = state.get("email_attachments", []) or []
    source_text = f"{email_body}\n\n{attachment_text}".strip()

    extracted: Dict[str, Any] = {
        "customer_name": _extract_customer_name_from_signature(email_body),
        "customer_email": None,
        "customer_phone": extract_phone_from_text(source_text),
        "customer_address": extract_address_from_text(source_text),
        "product_name": _find_product_in_text(source_text),
        "product_serial": extract_serial_from_text(source_text),
        "purchase_date": extract_date_from_text(source_text),
        "purchase_location": None,
        "order_number": _extract_order_number_from_text(source_text),
        "issue_description": None,
        "has_proof_of_purchase": False,
        "missing_fields": [],
    }

    # Email address fallback
    if "@" in email_from:
        extracted["customer_email"] = email_from.strip()
    else:
        match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", source_text)
        if match:
            extracted["customer_email"] = match.group(0)

    # Issue description heuristic
    issue = None
    for line in (l.strip() for l in email_body.splitlines()):
        if not line:
            continue
        low = line.lower()
        if any(k in low for k in ["stopped working", "not working", "won't", "doesn't", "no heat", "no power", "broken", "defect"]):
            issue = line
            break
    extracted["issue_description"] = issue or (email_body.strip()[:400] if email_body.strip() else None)

    # Normalize known fields
    if extracted.get("customer_phone"):
        extracted["customer_phone"] = normalize_phone(extracted.get("customer_phone"))
    if extracted.get("product_serial"):
        extracted["product_serial"] = normalize_serial(extracted.get("product_serial"))
    if extracted.get("customer_address"):
        extracted["customer_address"] = normalize_address(extracted.get("customer_address"))
    if extracted.get("purchase_date"):
        extracted["purchase_date"] = normalize_date(extracted.get("purchase_date"))

    # Proof of purchase
    proof_keywords = ["receipt", "order", "confirmation", "invoice"]
    has_proof = any(any(kw in (att or "").lower() for kw in proof_keywords) for att in attachments)
    if not has_proof:
        body_plus_attachment = f"{email_body}\n{attachment_text}".lower()
        has_proof = bool(re.search(r"\b(receipt|order|confirmation|invoice|proof of purchase)\b", body_plus_attachment))
    extracted["has_proof_of_purchase"] = has_proof

    # Missing fields and attachments
    extracted["missing_fields"] = identify_missing_fields(extracted)
    extracted["attachments"] = attachments

    return extracted


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
    attachment_text = state.get("email_attachment_text", "")
    combined_body = (f"{email_body}\n\nAttachment text:\n{attachment_text}").strip()
    email_from = state.get("email_from", "")
    demo_mode = os.getenv("DEMO_MODE", "false").strip().lower() == "true"

    if demo_mode:
        extracted = _deterministic_extract(state)
        # Calculate confidence based on completeness
        total_fields = 10
        filled_fields = sum(
            1
            for k, v in extracted.items()
            if v and k not in ["missing_fields", "attachments", "has_proof_of_purchase"]
        )
        confidence = filled_fields / total_fields
        return {
            **state,
            "extracted_fields": ExtractedFields(**extracted),
            "extraction_confidence": confidence,
            "llm_model": "demo",
            "workflow_status": "EXTRACTED",
        }
    
    try:
        llm = get_llm()
        llm_model = getattr(llm, "model_name", "")
        
        prompt = EXTRACTION_PROMPT.format(
            email_from=email_from,
            email_subject=state.get("email_subject", ""),
            email_date=state.get("email_date", ""),
            email_body=combined_body[:4500],
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
            extracted["customer_phone"] = extract_phone_from_text(combined_body)
        if not extracted.get("product_serial"):
            extracted["product_serial"] = extract_serial_from_text(combined_body)
        if not extracted.get("purchase_date"):
            extracted["purchase_date"] = extract_date_from_text(combined_body)
        if not extracted.get("customer_address"):
            extracted["customer_address"] = extract_address_from_text(combined_body)
        
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
                has_proof = bool(re.search(r"\b(receipt|order|confirmation|invoice|proof of purchase)\b", combined_body.lower()))
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
        # Fallback to deterministic extraction instead of hard failing.
        extracted = _deterministic_extract(state)
        total_fields = 10
        filled_fields = sum(
            1
            for k, v in extracted.items()
            if v and k not in ["missing_fields", "attachments", "has_proof_of_purchase"]
        )
        confidence = filled_fields / total_fields
        return {
            **state,
            "extracted_fields": ExtractedFields(**extracted),
            "extraction_confidence": confidence,
            "llm_model": "fallback-deterministic",
            "workflow_status": "EXTRACTED",
            "error_message": f"Extraction error (used deterministic fallback): {e}",
        }
