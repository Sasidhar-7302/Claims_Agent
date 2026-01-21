
import pytest
from app.nodes.extract import (
    normalize_date, 
    normalize_phone, 
    normalize_serial, 
    extract_date_from_text,
    identify_missing_fields
)
from app.nodes.analyze import (
    check_warranty_window,
    _address_in_us,
    _keyword_present
)
from datetime import datetime, timedelta

# --- Normalization Tests ---

def test_normalize_date():
    assert normalize_date("2024-01-01") == "2024-01-01"
    assert normalize_date("01/01/2024") == "2024-01-01"
    assert normalize_date("Jan 1, 2024") == "2024-01-01"
    assert normalize_date("invalid") == "invalid" # Should return as-is or None depending on impl, currently impl returns as-is
    assert normalize_date(None) is None

def test_normalize_phone():
    assert normalize_phone("123-456-7890") == "123-456-7890"
    assert normalize_phone("(123) 456-7890") == "123-456-7890"
    assert normalize_phone("1234567890") == "123-456-7890"
    assert normalize_phone("1-123-456-7890") == "123-456-7890"
    assert normalize_phone(None) is None

def test_normalize_serial():
    assert normalize_serial("sn: 123-abc") == "SN123-ABC" # Regex keeps alphanumeric
    assert normalize_serial("123abc") == "123ABC"
    assert normalize_serial("  123  ") == "123"

# --- Extraction Logic Tests ---

def test_extract_date_fallback():
    text = "I bought this on Jan 15, 2023 at a store."
    assert extract_date_from_text(text) == "2023-01-15"
    
    text2 = "Purchase date: 2023-12-25"
    assert extract_date_from_text(text2) == "2023-12-25"

def test_identify_missing_fields():
    fields = {
        "customer_name": "John Doe",
        "product_name": "ProDry",
        "purchase_date": "2023-01-01",
        "issue_description": None # Missing
    }
    missing = identify_missing_fields(fields)
    assert "issue_description" in missing
    assert "customer_name" not in missing

# --- Analysis Logic Tests ---

def test_warranty_window_valid():
    today = datetime.now()
    two_months_ago = (today - timedelta(days=60)).strftime("%Y-%m-%d")
    
    is_valid, reason = check_warranty_window(two_months_ago)
    assert is_valid is True
    assert "within" in reason.lower()

def test_warranty_window_expired():
    today = datetime.now()
    four_months_ago = (today - timedelta(days=120)).strftime("%Y-%m-%d")
    
    is_valid, reason = check_warranty_window(four_months_ago)
    assert is_valid is False
    assert "expired" in reason.lower()

def test_address_in_us():
    assert _address_in_us("123 Main St, New York, NY 10001") is True
    assert _address_in_us("500 Boylston St, Boston, MA 02116") is True # Added ZIP
    assert _address_in_us("London, UK") is False
    assert _address_in_us(None) is False

def test_keyword_present():
    assert _keyword_present("the device stopped working", "stopped") is True
    assert _keyword_present("the device did not stop working", "stop") is False 
    assert _keyword_present("no damage visible", "damage") is False # Lowercase input
