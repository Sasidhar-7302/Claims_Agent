"""
Node 6: Claim Analysis

Analyzes claim validity using deterministic checks and LLM reasoning.
"""

import json
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple, List
from app.state import ClaimState, AnalysisResult
from app.llm import get_llm


WARRANTY_PERIOD_MONTHS = 3


ANALYSIS_PROMPT = """You are a warranty claims analyst for HairTech Industries.

Analyze this warranty claim and provide a recommendation.

## Claim Details
- Customer: {customer_name}
- Product: {product_name} ({product_id})
- Purchase Date: {purchase_date}
- Issue: {issue_description}
- Has Proof of Purchase: {has_proof}
- Serial Number: {serial_number}

## Warranty Window Check
{warranty_check}

## Relevant Policy Excerpts

{policy_excerpts}

## Missing Information
{missing_fields}

---

Analyze this claim carefully.
1. Is the purchase within the 3-month warranty window? (See Warranty Window Check)
2. Is the issue a product defect? (Examples: stopped working, no heat, bad switch, won't turn on).
3. Do any exclusions apply? (Damage, misuse, water, commercial use).

IMPORTANT RULES:
- If the warranty is VALID and the issue is a DEFECT, you MUST recommend **APPROVE**.
- Do NOT reject for lack of detail if the customer states the product stopped working.
- Only REJECT if there is a clear policy violation (e.g. warranty expired, water damage, misuse).
- If unsure, use NEED_INFO.

Respond with ONLY a JSON object:
{{
    "recommendation": "APPROVE" or "REJECT" or "NEED_INFO",
    "confidence": 0.0 to 1.0,
    "facts": ["list of verified facts"],
    "assumptions": ["list of assumptions made"],
    "reasoning": "Detailed explanation of the recommendation",
    "policy_references": ["list of policy sections that apply"],
    "exclusions_triggered": ["list of any exclusions that apply, empty if none"]
}}"""

REQUIREMENT_LABELS = {
    "proof_of_purchase": "proof_of_purchase",
    "serial_number": "serial_number",
    "contact_info": "contact_info (email, phone, or address)",
    "photos": "photos of the product issue",
    "business_license": "business license (salon models)",
    "maintenance_description": "maintenance description",
    "adult_supervision": "adult supervision confirmation",
    "recycling_confirmation": "recycling confirmation",
    "us_address": "US return address",
    "us_ca_address": "US or Canada return address"
}


def check_warranty_window(purchase_date_str: Optional[str], claim_date: Optional[str] = None) -> Tuple[bool, str]:
    """
    Check if purchase date is within warranty window.
    
    Args:
        purchase_date_str: Purchase date string (YYYY-MM-DD)
        claim_date: Claim date (optional, defaults to today)
        
    Returns:
        Tuple of (is_valid, explanation)
    """
    if not purchase_date_str:
        return None, "Purchase date not provided - cannot verify warranty window"
    
    try:
        # Parse purchase date
        purchase_date = datetime.strptime(purchase_date_str, "%Y-%m-%d")
        
        # Get claim date
        if claim_date:
            try:
                current_date = datetime.fromisoformat(claim_date.replace("Z", "+00:00")).replace(tzinfo=None)
            except:
                current_date = datetime.now()
        else:
            current_date = datetime.now()
        
        # Calculate warranty expiration
        warranty_expiration = purchase_date + timedelta(days=WARRANTY_PERIOD_MONTHS * 30)
        
        # Check if within warranty
        is_valid = current_date <= warranty_expiration
        
        days_since_purchase = (current_date - purchase_date).days
        days_remaining = (warranty_expiration - current_date).days
        
        if is_valid:
            explanation = (
                f"[OK] Within warranty period. "
                f"Purchased {days_since_purchase} days ago. "
                f"{days_remaining} days remaining in warranty."
            )
        else:
            explanation = (
                f"[EXPIRED] Outside warranty period. "
                f"Purchased {days_since_purchase} days ago. "
                f"Warranty expired {-days_remaining} days ago."
            )
        
        return is_valid, explanation
        
    except ValueError as e:
        return None, f"Could not parse purchase date '{purchase_date_str}': {e}"


def format_policy_excerpts(excerpts: List[dict]) -> str:
    """Format policy excerpts for the prompt."""
    if not excerpts:
        return "No policy excerpts available."
    
    formatted = []
    for excerpt in excerpts:
        source = (
            f"Source: {excerpt.get('policy_id', 'N/A')} | "
            f"File: {excerpt.get('policy_file', 'N/A')} | "
            f"Chunk: {excerpt.get('chunk_index', 'N/A')} | "
            f"Distance: {excerpt.get('distance', 'N/A')}"
        )
        formatted.append(
            f"### {excerpt.get('section_name', 'Unknown')}\n{source}\n{excerpt.get('content', '')}\n"
        )
    
    return "\n".join(formatted)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _keyword_present(text: str, keyword: str) -> bool:
    if not keyword:
        return False
    idx = text.find(keyword)
    if idx == -1:
        return False
    window = text[max(0, idx - 12):idx]
    if re.search(r"\b(no|not|never)\b", window):
        return False
    return True


def _find_exclusion_hits(text: str, keywords: List[str]) -> List[str]:
    hits = []
    for kw in keywords or []:
        kw_norm = _normalize_text(kw)
        if kw_norm and _keyword_present(text, kw_norm):
            hits.append(kw)
    return hits


def _address_in_us(address: str) -> bool:
    if not address:
        return False
    addr = address.upper()
    if "USA" in addr or "UNITED STATES" in addr:
        return True
    us_states = {
        "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA",
        "ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK",
        "OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"
    }
    if re.search(r"\b\d{5}(-\d{4})?\b", addr):
        for state in us_states:
            if re.search(rf"\b{state}\b", addr):
                return True
    return False


def _address_in_us_or_canada(address: str) -> bool:
    if _address_in_us(address):
        return True
    addr = (address or "").upper()
    if "CANADA" in addr:
        return True
    ca_provinces = {"ON","QC","BC","AB","MB","NB","NL","NS","NT","NU","PE","SK","YT"}
    if re.search(r"\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b", addr):
        for prov in ca_provinces:
            if re.search(rf"\b{prov}\b", addr):
                return True
    return False


def _check_requirements_missing(state: ClaimState, extracted: dict) -> List[str]:
    requirements = state.get("policy_requirements") or []
    missing = []
    email_body = state.get("email_body", "")
    attachments = state.get("email_attachments", [])

    def has_photos():
        photo_exts = (".jpg", ".jpeg", ".png", ".heic")
        if any(att.lower().endswith(photo_exts) for att in attachments):
            return True
        return bool(re.search(r"\b(photo|picture|image)\b", email_body.lower()))

    def has_business_license():
        return bool(re.search(r"\b(business license|salon license|license number)\b", email_body.lower()))

    def has_maintenance_desc():
        return bool(re.search(r"\b(clean|filter|maintenance|wipe)\b", email_body.lower()))

    def has_adult_supervision():
        return bool(re.search(r"\b(supervision|supervised|adult present)\b", email_body.lower()))

    def has_recycling_confirmation():
        return bool(re.search(r"\b(recycle|recycling|return for recycling)\b", email_body.lower()))

    for req in requirements:
        label = REQUIREMENT_LABELS.get(req, req)
        if req == "proof_of_purchase" and not extracted.get("has_proof_of_purchase"):
            missing.append(label)
        elif req == "serial_number" and not extracted.get("product_serial"):
            missing.append(label)
        elif req == "contact_info":
            has_contact = any(extracted.get(k) for k in ["customer_email", "customer_phone", "customer_address"])
            if not has_contact:
                missing.append(label)
        elif req == "photos" and not has_photos():
            missing.append(label)
        elif req == "business_license" and not has_business_license():
            missing.append(label)
        elif req == "maintenance_description" and not has_maintenance_desc():
            missing.append(label)
        elif req == "adult_supervision" and not has_adult_supervision():
            missing.append(label)
        elif req == "recycling_confirmation" and not has_recycling_confirmation():
            missing.append(label)
        elif req == "us_address" and not _address_in_us(extracted.get("customer_address", "")):
            missing.append(label)
        elif req == "us_ca_address" and not _address_in_us_or_canada(extracted.get("customer_address", "")):
            missing.append(label)

    return missing


def analyze_claim(state: ClaimState) -> ClaimState:
    """
    Analyze warranty claim using deterministic checks and LLM reasoning.
    
    Args:
        state: Current workflow state with extracted fields and policy
        
    Returns:
        Updated state with analysis result
    """
    if state.get("workflow_status") == "ERROR":
        return state
    
    extracted = state.get("extracted_fields", {})
    policy_excerpts = state.get("policy_excerpts", [])
    
    # Deterministic warranty window check
    purchase_date = extracted.get("purchase_date")
    email_date = state.get("email_date")
    warranty_valid, warranty_details = check_warranty_window(purchase_date, email_date)
    
    # If warranty expired, fast-track rejection FIRST
    if warranty_valid is False:
        return {
            **state,
            "analysis": AnalysisResult(
                recommendation="REJECT",
                confidence=0.95,
                facts=[
                    f"Purchase date: {purchase_date}",
                    warranty_details
                ],
                assumptions=[],
                reasoning="Warranty period has expired. The 3-month warranty window has passed.",
                policy_references=["WARRANTY PERIOD"],
                warranty_window_valid=False,
                warranty_window_details=warranty_details,
                exclusions_triggered=["Warranty period expired"]
            ),
            "workflow_status": "ANALYZED"
        }
    
    # Deterministic exclusions - check BEFORE missing info
    # If customer admits exclusion (e.g., salon use), reject immediately
    text_blob = f"{extracted.get('issue_description', '')} {state.get('email_body', '')}"
    exclusion_hits = _find_exclusion_hits(_normalize_text(text_blob), state.get("policy_exclusion_keywords", []))
    if exclusion_hits:
        return {
            **state,
            "analysis": AnalysisResult(
                recommendation="REJECT",
                confidence=0.9,
                facts=[
                    f"Issue description: {extracted.get('issue_description', 'Not provided')}",
                    f"Exclusions matched: {', '.join(exclusion_hits)}"
                ],
                assumptions=[],
                reasoning=(
                    "The claim mentions excluded conditions per the policy. "
                    "These exclusions invalidate the warranty claim."
                ),
                policy_references=["EXCLUSIONS"],
                warranty_window_valid=warranty_valid,
                warranty_window_details=warranty_details,
                exclusions_triggered=exclusion_hits
            ),
            "workflow_status": "ANALYZED"
        }
    
    # Check for critical missing info (hard requirements)
    missing_fields = extracted.get("missing_fields", [])
    
    # Critical fields that MUST be present for any decision
    critical_missing = [f for f in missing_fields if f in [
        "product_name", 
        "issue_description", 
        "contact_info (email, phone, or address)"
    ]]
    
    # Also check for serial number - required for warranty verification
    serial = extracted.get("product_serial")
    if not serial:
        critical_missing.append("serial_number")
    
    # Check for vague issue descriptions (too short or generic)
    issue_desc = extracted.get("issue_description") or ""
    vague_phrases = ["broken", "not working", "doesn't work", "stopped", "help", "issue", "problem"]
    is_vague = (
        len(issue_desc) < 30 or  # Too short
        (issue_desc.lower().strip().split()[-1] if issue_desc else "") in ["broken", "issue", "problem"] or  # Ends with vague word
        all(word in issue_desc.lower() for word in issue_desc.lower().split() if word in vague_phrases)  # Only vague words
    )
    if is_vague and len(issue_desc) < 50:
        critical_missing.append("detailed_issue_description")
    
    # Check for customer address (required for return shipping)
    address = extracted.get("customer_address")
    if not address:
        critical_missing.append("customer_address")
    
    if critical_missing:
        # Can't analyze without critical info
        return {
            **state,
            "analysis": AnalysisResult(
                recommendation="NEED_INFO",
                confidence=0.9,
                facts=[f"Critical information missing: {', '.join(critical_missing)}"],
                assumptions=[],
                reasoning=f"Cannot process claim without: {', '.join(critical_missing)}. Please request this information from the customer.",
                policy_references=["CLAIM REQUIREMENTS"],
                warranty_window_valid=warranty_valid,
                warranty_window_details=warranty_details,
                exclusions_triggered=[]
            ),
            "workflow_status": "ANALYZED"
        }

    # Deterministic requirements check
    requirements_missing = _check_requirements_missing(state, extracted)
    if requirements_missing:
        merged_missing = sorted(set(missing_fields + requirements_missing))
        updated_extracted = dict(extracted)
        updated_extracted["missing_fields"] = merged_missing
        return {
            **state,
            "extracted_fields": updated_extracted,
            "analysis": AnalysisResult(
                recommendation="NEED_INFO",
                confidence=0.85,
                facts=[
                    f"Missing required evidence: {', '.join(requirements_missing)}"
                ],
                assumptions=[],
                reasoning=(
                    "Required evidence is missing for this product. "
                    "Collect the missing items before making a final decision."
                ),
                policy_references=["CLAIM REQUIREMENTS"],
                warranty_window_valid=warranty_valid,
                warranty_window_details=warranty_details,
                exclusions_triggered=[]
            ),
            "workflow_status": "ANALYZED"
        }

    # Use LLM for detailed analysis
    try:
        llm = get_llm()
        llm_model = getattr(llm, "model_name", "")
        
        warranty_check = warranty_details if warranty_details else "Warranty window check not performed (missing purchase date)"
        
        prompt = ANALYSIS_PROMPT.format(
            customer_name=extracted.get("customer_name", "Unknown"),
            product_name=state.get("product_name", extracted.get("product_name", "Unknown")),
            product_id=state.get("product_id", "Unknown"),
            purchase_date=purchase_date or "Not provided",
            issue_description=extracted.get("issue_description", "Not provided"),
            has_proof=extracted.get("has_proof_of_purchase", False),
            serial_number=extracted.get("product_serial", "Not provided"),
            warranty_check=warranty_check,
            policy_excerpts=format_policy_excerpts(policy_excerpts),
            missing_fields=", ".join(missing_fields) if missing_fields else "None"
        )
        
        response = llm.generate_json(prompt)
        
        # Parse response
        response = response.strip()
        if response.startswith("```"):
            response = re.sub(r"```json?\s*", "", response)
            response = re.sub(r"```\s*$", "", response)
        
        result = json.loads(response)
        
        # Validate recommendation
        recommendation = result.get("recommendation", "NEED_INFO").upper()
        if recommendation not in ["APPROVE", "REJECT", "NEED_INFO"]:
            recommendation = "NEED_INFO"
        
        return {
            **state,
            "analysis": AnalysisResult(
                recommendation=recommendation,
                confidence=float(result.get("confidence", 0.7)),
                facts=result.get("facts", []),
                assumptions=result.get("assumptions", []),
                reasoning=result.get("reasoning", ""),
                policy_references=result.get("policy_references", []),
                warranty_window_valid=warranty_valid,
                warranty_window_details=warranty_details,
                exclusions_triggered=result.get("exclusions_triggered", [])
            ),
            "llm_model": llm_model,
            "workflow_status": "ANALYZED"
        }
        
    except Exception as e:
        # Fallback analysis
        return {
            **state,
            "analysis": AnalysisResult(
                recommendation="NEED_INFO",
                confidence=0.5,
                facts=[f"Analysis error: {e}"],
                assumptions=["Manual review required due to analysis error"],
                reasoning="Automated analysis failed. Please review manually.",
                policy_references=[],
                warranty_window_valid=warranty_valid,
                warranty_window_details=warranty_details,
                exclusions_triggered=[]
            ),
            "workflow_status": "ANALYZED"
        }
