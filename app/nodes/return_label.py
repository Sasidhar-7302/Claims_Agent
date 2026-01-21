"""
Node 10: Return Label Generator

Generates a mock return shipping label PDF for approved claims.
"""

import json
from pathlib import Path
from datetime import datetime
from app.state import ClaimState

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


BASE_DIR = Path(__file__).parent.parent.parent
OUTBOX_DIR = BASE_DIR / "outbox" / "labels"
PRODUCTS_FILE = BASE_DIR / "data" / "products.json"


def get_company_address() -> dict:
    """Load company return address from products.json."""
    try:
        with open(PRODUCTS_FILE, "r") as f:
            data = json.load(f)
            return data.get("return_address", {
                "name": "HairTech Industries Returns",
                "street": "1234 Innovation Drive",
                "city": "San Jose",
                "state": "CA",
                "zip": "95134",
                "country": "USA"
            })
    except:
        return {
            "name": "HairTech Industries Returns",
            "street": "1234 Innovation Drive",
            "city": "San Jose",
            "state": "CA",
            "zip": "95134",
            "country": "USA"
        }


def generate_tracking_number() -> str:
    """Generate a mock tracking number."""
    import random
    return f"HTK{datetime.now().strftime('%Y%m%d')}{random.randint(100000, 999999)}"


def generate_pdf_label(claim_id: str, customer_address: str, output_path: Path) -> bool:
    """
    Generate a realistic PDF return shipping label.
    
    Args:
        claim_id: Claim ID for RMA reference
        customer_address: Customer's address
        output_path: Path to save the PDF
        
    Returns:
        True if successful, False otherwise
    """
    if not REPORTLAB_AVAILABLE:
        return False
    
    try:
        from reportlab.graphics.barcode import code128
        from reportlab.lib.colors import HexColor
        
        company = get_company_address()
        tracking = generate_tracking_number()
        rma_number = f"RMA-{claim_id}"
        
        # Create PDF (4x6 label size - standard shipping label)
        label_width = 4 * inch
        label_height = 6 * inch
        c = canvas.Canvas(str(output_path), pagesize=(label_width, label_height))
        
        # Colors
        brand_teal = HexColor("#2C5559")
        brand_orange = HexColor("#F2542D")
        light_gray = HexColor("#F1F5F9")
        
        # === HEADER: Carrier Section ===
        c.setFillColor(brand_teal)
        c.rect(0, label_height - 60, label_width, 60, fill=True, stroke=False)
        
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(10, label_height - 25, "FastShip")
        c.setFont("Helvetica", 8)
        c.drawString(10, label_height - 40, "PRIORITY RETURN SERVICE")
        
        # Tracking number in header
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(label_width - 10, label_height - 25, tracking)
        c.setFont("Helvetica", 7)
        c.drawRightString(label_width - 10, label_height - 38, "PREPAID - DO NOT STAMP")
        
        # === SERVICE BANNER ===
        c.setFillColor(brand_orange)
        c.rect(0, label_height - 80, label_width, 20, fill=True, stroke=False)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(label_width / 2, label_height - 75, "WARRANTY RETURN - PRIORITY MAIL")
        
        # === FROM SECTION ===
        y_pos = label_height - 100
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(10, y_pos, "FROM:")
        c.setFont("Helvetica", 9)
        
        from_lines = customer_address.split("\n") if customer_address else ["Customer Address"]
        y_pos -= 12
        for line in from_lines[:4]:
            c.drawString(15, y_pos, line.strip()[:40])  # Truncate long lines
            y_pos -= 11
        
        # === DIVIDER ===
        y_pos -= 5
        c.setStrokeColor(colors.gray)
        c.setLineWidth(0.5)
        c.line(10, y_pos, label_width - 10, y_pos)
        
        # === TO SECTION (larger, more prominent) ===
        y_pos -= 15
        c.setFont("Helvetica-Bold", 8)
        c.drawString(10, y_pos, "SHIP TO:")
        c.setFont("Helvetica-Bold", 11)
        
        y_pos -= 14
        c.drawString(15, y_pos, company.get("name", "HairTech Industries Returns"))
        c.setFont("Helvetica", 10)
        y_pos -= 12
        c.drawString(15, y_pos, company.get("street", "1234 Innovation Drive"))
        y_pos -= 12
        c.drawString(15, y_pos, f"{company.get('city', 'San Jose')}, {company.get('state', 'CA')} {company.get('zip', '95134')}")
        y_pos -= 12
        c.drawString(15, y_pos, company.get("country", "USA"))
        
        # === RMA BOX ===
        y_pos -= 25
        c.setFillColor(light_gray)
        c.rect(10, y_pos - 25, label_width - 20, 30, fill=True, stroke=True)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(label_width / 2, y_pos - 5, f"RMA: {rma_number}")
        c.setFont("Helvetica", 8)
        c.drawCentredString(label_width / 2, y_pos - 18, "Reference this number in all correspondence")
        
        # === BARCODE SECTION ===
        y_pos -= 45
        try:
            barcode = code128.Code128(tracking, barWidth=0.8, barHeight=35)
            barcode.drawOn(c, (label_width - barcode.width) / 2, y_pos - 40)
            c.setFont("Helvetica", 8)
            c.drawCentredString(label_width / 2, y_pos - 50, tracking)
        except Exception as e:
            # Fallback: draw placeholder bars
            c.setFont("Courier", 6)
            c.drawCentredString(label_width / 2, y_pos - 20, "|||||||||||||||||||||||||||||||||||||||")
            c.drawCentredString(label_width / 2, y_pos - 35, tracking)
        
        # === PACKAGE INFO ===
        y_pos -= 70
        c.setStrokeColor(colors.gray)
        c.rect(10, y_pos - 35, (label_width - 30) / 2, 35, stroke=True)
        c.rect(15 + (label_width - 30) / 2, y_pos - 35, (label_width - 30) / 2, 35, stroke=True)
        
        c.setFont("Helvetica", 7)
        c.drawString(15, y_pos - 10, "WEIGHT")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(15, y_pos - 25, "2.5 LBS")
        
        c.setFont("Helvetica", 7)
        c.drawString(20 + (label_width - 30) / 2, y_pos - 10, "DIMENSIONS")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 + (label_width - 30) / 2, y_pos - 25, "12x8x4 IN")
        
        # === INSTRUCTIONS ===
        y_pos -= 50
        c.setFont("Helvetica-Bold", 7)
        c.drawString(10, y_pos, "RETURN INSTRUCTIONS:")
        c.setFont("Helvetica", 6)
        c.drawString(10, y_pos - 10, "1. Pack product securely in original packaging")
        c.drawString(10, y_pos - 18, "2. Include copy of claim confirmation email")
        c.drawString(10, y_pos - 26, "3. Affix this label to outside of package")
        c.drawString(10, y_pos - 34, "4. Drop off at any carrier location")
        
        # === FOOTER ===
        c.setFont("Helvetica", 5)
        c.drawCentredString(label_width / 2, 20, 
                           f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
                           f"Valid for 30 days | Claim: {claim_id}")
        c.drawCentredString(label_width / 2, 10, 
                           "Questions? warranty@hairtechind.com | 1-800-HAIRTECH")
        
        c.save()
        return True
        
    except Exception as e:
        print(f"Error generating PDF: {e}")
        import traceback
        traceback.print_exc()
        return False


def generate_text_label(claim_id: str, customer_address: str, output_path: Path) -> bool:
    """Generate a text-based label as fallback when reportlab is not available."""
    try:
        company = get_company_address()
        tracking = generate_tracking_number()
        rma_number = f"RMA-{claim_id}"
        
        label_content = f"""
+------------------------------------------------------------------+
|                    PREPAID RETURN LABEL                          |
|                    HairTech Industries                           |
|                    Warranty Return Service                       |
+------------------------------------------------------------------+
|                                                                  |
|  FROM:                                                           |
|  {customer_address or 'Customer Address'}
|                                                                  |
|  TO:                                                             |
|  {company.get('name', 'HairTech Industries Returns')}
|  {company.get('street', '1234 Innovation Drive')}
|  {company.get('city', 'San Jose')}, {company.get('state', 'CA')} {company.get('zip', '95134')}
|  {company.get('country', 'USA')}
|                                                                  |
+------------------------------------------------------------------+
|                                                                  |
|  RMA Number: {rma_number:<30}                            |
|  Tracking:   {tracking:<30}                            |
|                                                                  |
|  |||||||||||||||||||||||||||||||||||||||||||||||||||||||||||     |
|                      {tracking}                                  |
|                                                                  |
|                    PRIORITY MAIL                                 |
|              PREPAID - NO POSTAGE REQUIRED                       |
|                                                                  |
+------------------------------------------------------------------+
|  INSTRUCTIONS:                                                   |
|  1. Pack the product securely in original packaging              |
|  2. Include a copy of your warranty claim email                  |
|  3. Affix this label to the outside of the package               |
|  4. Drop off at any postal service location                      |
+------------------------------------------------------------------+
|  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Claim: {claim_id} | Valid: 30 days   |
|  Questions? warranty@hairtechind.com | 1-800-HAIRTECH           |
+------------------------------------------------------------------+
"""
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(label_content)
        return True
        
    except Exception as e:
        print(f"Error generating text label: {e}")
        return False


def generate_return_label(state: ClaimState) -> ClaimState:
    """
    Generate return shipping label for approved claims.
    
    Args:
        state: Current workflow state with approval decision
        
    Returns:
        Updated state with label path
    """
    decision = state.get("human_decision")
    
    # Only generate label for approvals
    if decision != "APPROVE":
        return {
            **state,
            "return_label_path": None
        }
    
    claim_id = state.get("claim_id", "UNKNOWN")
    extracted = state.get("extracted_fields", {})
    
    # Get customer address
    customer_address = extracted.get("customer_address", "")
    customer_name = extracted.get("customer_name", "")
    if customer_name and customer_address:
        full_address = f"{customer_name}\n{customer_address}"
    elif customer_address:
        full_address = customer_address
    elif customer_name:
        full_address = customer_name
    else:
        full_address = "Customer Address Not Provided"
    
    # Ensure output directory exists
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    
    # Try to generate PDF first, fall back to text
    if REPORTLAB_AVAILABLE:
        label_path = OUTBOX_DIR / f"{claim_id}.pdf"
        success = generate_pdf_label(claim_id, full_address, label_path)
    else:
        label_path = OUTBOX_DIR / f"{claim_id}_label.txt"
        success = generate_text_label(claim_id, full_address, label_path)
    
    if success:
        return {
            **state,
            "return_label_path": str(label_path)
        }
    else:
        return {
            **state,
            "return_label_path": None,
            "error_message": state.get("error_message", "") + " Label generation failed."
        }
