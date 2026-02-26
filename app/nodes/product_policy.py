"""
Node 4: Product and Policy Selection

Deterministically maps product names to product IDs and policy files.
"""

import json
from typing import Optional, Tuple
from app.state import ClaimState
from app.vector_store import get_policies_dir, get_policy_index_file
from app.product_catalog import load_products_catalog


def load_products() -> dict:
    """Load the product catalog."""
    try:
        return load_products_catalog()
    except Exception as e:
        print(f"Error loading products: {e}")
        return {"products": []}


def load_policy_index() -> list:
    """Load policy index metadata."""
    policy_index_file = get_policy_index_file()
    if not policy_index_file.exists():
        return []
    try:
        with open(policy_index_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("policies", [])
    except Exception as e:
        print(f"Error loading policy index: {e}")
        return []


def parse_date(date_str: str) -> Optional[str]:
    """Parse a date string in YYYY-MM-DD format."""
    if not date_str:
        return None
    return date_str.strip()


def select_policy_from_index(product_id: str, purchase_date: Optional[str]) -> Optional[dict]:
    """Select the appropriate policy entry based on product and purchase date."""
    policies = [p for p in load_policy_index() if p.get("product_id") == product_id]
    if not policies:
        return None

    # Choose latest policy with effective_date <= purchase_date
    purchase_date = parse_date(purchase_date)
    if purchase_date:
        eligible = [p for p in policies if p.get("effective_date", "") <= purchase_date]
        if eligible:
            return sorted(eligible, key=lambda p: p.get("effective_date", ""))[-1]

    # Fallback to latest by effective_date
    return sorted(policies, key=lambda p: p.get("effective_date", ""))[-1]


def normalize_text(text: str) -> str:
    """Normalize text for matching."""
    if not text:
        return ""
    return text.lower().strip().replace("-", " ").replace("_", " ")


def find_product_match(product_name: str, products: list) -> Tuple[Optional[dict], float]:
    """
    Find the best matching product from catalog.
    
    Args:
        product_name: Product name from claim
        products: Product catalog list
        
    Returns:
        Tuple of (matched product dict, confidence score)
    """
    if not product_name:
        return None, 0.0
    
    normalized_name = normalize_text(product_name)
    
    best_match = None
    best_score = 0.0
    
    for product in products:
        # Check exact name match
        if normalize_text(product["name"]) == normalized_name:
            return product, 1.0
        
        # Check product ID match
        if normalize_text(product["product_id"]) == normalized_name:
            return product, 1.0
        
        # Check aliases
        for alias in product.get("aliases", []):
            if normalize_text(alias) == normalized_name:
                return product, 1.0
            
            # Partial match scoring
            if normalize_text(alias) in normalized_name or normalized_name in normalize_text(alias):
                score = len(normalize_text(alias)) / max(len(normalized_name), 1)
                if score > best_score:
                    best_score = score
                    best_match = product
        
        # Check if product name is contained
        prod_name_norm = normalize_text(product["name"])
        if prod_name_norm in normalized_name or normalized_name in prod_name_norm:
            score = len(prod_name_norm) / max(len(normalized_name), 1)
            if score > best_score:
                best_score = min(score, 0.9)  # Cap at 0.9 for partial matches
                best_match = product
    
    return best_match, best_score


def verify_policy_exists(policy_file: str) -> bool:
    """Check if the policy file exists."""
    policy_path = get_policies_dir() / policy_file
    return policy_path.exists()


def select_product_policy(state: ClaimState) -> ClaimState:
    """
    Select the correct product and warranty policy based on extracted fields.
    
    Uses deterministic matching against product catalog.
    
    Args:
        state: Current workflow state with extracted fields
        
    Returns:
        Updated state with product and policy selection
    """
    if state.get("workflow_status") == "ERROR":
        return state
    
    extracted = state.get("extracted_fields", {})
    product_name = extracted.get("product_name", "")
    product_serial = extracted.get("product_serial", "")
    purchase_date = extracted.get("purchase_date", "")
    
    # Load product catalog
    catalog = load_products()
    products = catalog.get("products", [])
    
    if not products:
        return {
            **state,
            "product_id": None,
            "product_name": product_name,
            "policy_file": None,
            "policy_selection_reason": "Product catalog not available",
            "product_match_confidence": 0.0
        }
    
    # Try to match by serial number prefix if available
    matched_by_serial = None
    if product_serial:
        serial_prefix = product_serial.split("-")[0].upper() if "-" in product_serial else ""
        prefix_map = {
            "PS3K": "HD-PRO-001",
            "PS5K": "HD-PRO-002",
            "TMC": "HD-TRV-001",
            "TMP": "HD-TRV-002",
            "SE7K": "HD-SLN-001",
            "SE9K": "HD-SLN-002",
            "EB": "HD-ECO-001",
            "KG": "HD-KDS-001",
            "IF2K": "HD-ION-001",
            "QDE": "HD-QCK-001"
        }
        if serial_prefix in prefix_map:
            target_id = prefix_map[serial_prefix]
            matched_by_serial = next(
                (p for p in products if p["product_id"] == target_id), 
                None
            )
    
    # Match by product name
    matched_product, match_confidence = find_product_match(product_name, products)
    
    # Use serial match if available and has high confidence
    if matched_by_serial:
        if matched_product and matched_product["product_id"] == matched_by_serial["product_id"]:
            # Both methods agree
            final_match = matched_product
            final_confidence = 1.0
            reason = "Matched by both serial number and product name"
        else:
            # Serial takes precedence
            final_match = matched_by_serial
            final_confidence = 0.95
            reason = "Matched by serial number prefix"
    elif matched_product:
        final_match = matched_product
        final_confidence = match_confidence
        reason = f"Matched by product name (confidence: {match_confidence:.0%})"
    else:
        final_match = None
        final_confidence = 0.0
        reason = "No product match found"
    
    if final_match:
        policy_entry = select_policy_from_index(final_match["product_id"], purchase_date)
        policy_file = None
        policy_id = None
        policy_version = None
        policy_effective_date = None
        policy_requirements = None
        policy_exclusion_keywords = None

        if policy_entry:
            policy_file = policy_entry.get("policy_file")
            policy_id = policy_entry.get("policy_id")
            policy_version = policy_entry.get("version")
            policy_effective_date = policy_entry.get("effective_date")
            policy_requirements = policy_entry.get("requirements", [])
            policy_exclusion_keywords = policy_entry.get("exclusion_keywords", [])
            reason += f" | Policy: {policy_id} ({policy_version})"
        else:
            policy_file = final_match.get("policy_file", "")

        policy_exists = verify_policy_exists(policy_file) if policy_file else False
        if policy_file and not policy_exists:
            reason += f" (Warning: policy file not found: {policy_file})"

        return {
            **state,
            "product_id": final_match["product_id"],
            "product_name": final_match["name"],
            "product_category": final_match.get("category", ""),
            "policy_file": policy_file if policy_exists else None,
            "policy_id": policy_id,
            "policy_version": policy_version,
            "policy_effective_date": policy_effective_date,
            "policy_requirements": policy_requirements,
            "policy_exclusion_keywords": policy_exclusion_keywords,
            "policy_selection_reason": reason,
            "product_match_confidence": final_confidence
        }
    else:
        return {
            **state,
            "product_id": None,
            "product_name": product_name,
            "product_category": None,
            "policy_file": None,
            "policy_selection_reason": reason,
            "product_match_confidence": 0.0
        }
