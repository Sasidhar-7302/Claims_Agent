"""
Demo data generation utilities for local/free mode.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

from app.product_catalog import load_products_catalog


BASE_DIR = Path(__file__).parent.parent
DEFAULT_INBOX_DIR = BASE_DIR / "data" / "inbox"


FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Avery", "Riley", "Parker", "Jamie", "Drew",
]
LAST_NAMES = [
    "Johnson", "Smith", "Brown", "Davis", "Miller", "Wilson", "Moore", "Clark", "Hall", "Young",
]
STREETS = ["Oak", "Pine", "Maple", "Cedar", "Elm", "Lake", "Hill", "Sunset", "Ridge", "River"]
CITIES = [
    ("Austin", "TX", "78701"),
    ("Phoenix", "AZ", "85001"),
    ("Denver", "CO", "80202"),
    ("San Diego", "CA", "92101"),
    ("Seattle", "WA", "98101"),
]

ISSUES = [
    "stopped working with no heat and no fan",
    "turns on but shuts off after 30 seconds",
    "power light blinks and the motor never starts",
    "started making a burning smell and then would not turn on",
    "switch is stuck and unit will not start",
]


def _serial_prefix_for_product(product_id: str) -> str:
    mapping = {
        "HD-PRO-001": "PS3K",
        "HD-PRO-002": "PS5K",
        "HD-TRV-001": "TMC",
        "HD-TRV-002": "TMP",
        "HD-SLN-001": "SE7K",
        "HD-SLN-002": "SE9K",
        "HD-ECO-001": "EB",
        "HD-KDS-001": "KG",
        "HD-ION-001": "IF2K",
        "HD-QCK-001": "QDE",
    }
    return mapping.get(product_id, "HDX")


def _next_generated_id(inbox_dir: Path) -> int:
    max_idx = 0
    for path in inbox_dir.glob("demo_gen_*.json"):
        stem = path.stem
        try:
            max_idx = max(max_idx, int(stem.split("_")[-1]))
        except Exception:
            continue
    return max_idx + 1


def _build_claim_email(email_id: str, product: Dict, rng: random.Random) -> Dict:
    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    full_name = f"{first} {last}"
    city, state, zip_code = rng.choice(CITIES)
    street_num = rng.randint(100, 9999)
    street_name = rng.choice(STREETS)
    issue = rng.choice(ISSUES)

    purchase_days_ago = rng.randint(12, 85)
    purchase_date = (datetime.now() - timedelta(days=purchase_days_ago)).strftime("%Y-%m-%d")
    order_num = f"{rng.randint(100,999)}-{rng.randint(1000000,9999999)}-{rng.randint(1000000,9999999)}"
    serial = f"{_serial_prefix_for_product(product.get('product_id', ''))}-{datetime.now().year}-{rng.randint(10000,99999)}"

    body = (
        f"Hello,\n\n"
        f"I bought a {product.get('name')} on {purchase_date} and it has {issue}. "
        f"My order number is {order_num} and serial number is {serial}.\n\n"
        f"Please help me with a warranty claim.\n\n"
        f"Thanks,\n{full_name}\n{street_num} {street_name} Street\n{city}, {state} {zip_code}\n"
        f"Phone: 512-555-{rng.randint(1000,9999)}"
    )

    return {
        "email_id": email_id,
        "from": f"{first.lower()}.{last.lower()}@example.com",
        "to": "warranty@hairtechind.com",
        "subject": f"{product.get('name')} warranty claim",
        "date": datetime.now().isoformat(),
        "body": body,
        "attachments": [f"receipt_{order_num}.pdf"],
        "metadata": {
            "generated": True,
            "type": "claim",
        },
    }


def _build_non_claim_email(email_id: str, product: Dict, rng: random.Random) -> Dict:
    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    return {
        "email_id": email_id,
        "from": f"{first.lower()}.{last.lower()}@example.com",
        "to": "support@hairtechind.com",
        "subject": f"Question about {product.get('name')} features",
        "date": datetime.now().isoformat(),
        "body": (
            f"Hi team,\n\nCan you share whether {product.get('name')} supports dual voltage for travel?\n\n"
            f"Thanks,\n{first}"
        ),
        "attachments": [],
        "metadata": {
            "generated": True,
            "type": "non_claim",
        },
    }


def _build_spam_email(email_id: str, rng: random.Random) -> Dict:
    return {
        "email_id": email_id,
        "from": f"promo{rng.randint(1000,9999)}@bulk-mailer.example",
        "to": "warranty@hairtechind.com",
        "subject": "Act now! Exclusive wholesale deal!",
        "date": datetime.now().isoformat(),
        "body": (
            "Click here now for wholesale pricing!!! Act fast!!! Unsubscribe link included.\n"
            "Verify your credit card immediately for huge rewards."
        ),
        "attachments": [],
        "metadata": {
            "generated": True,
            "type": "spam",
        },
    }


def generate_demo_emails(
    inbox_dir: Path = DEFAULT_INBOX_DIR,
    claim_count: int = 12,
    non_claim_count: int = 4,
    spam_count: int = 4,
    seed: int = 42,
) -> List[Path]:
    """Generate synthetic demo emails and return written file paths."""
    inbox_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed + int(datetime.now().timestamp()) // 60)

    catalog = load_products_catalog()
    products = catalog.get("products", []) or []
    if not products:
        raise RuntimeError("No products available in products catalog.")

    next_idx = _next_generated_id(inbox_dir)
    written: List[Path] = []

    def write_email(payload: Dict) -> None:
        path = inbox_dir / f"{payload['email_id']}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written.append(path)

    for _ in range(claim_count):
        email_id = f"demo_gen_{next_idx:03d}"
        next_idx += 1
        product = rng.choice(products)
        write_email(_build_claim_email(email_id, product, rng))

    for _ in range(non_claim_count):
        email_id = f"demo_gen_{next_idx:03d}"
        next_idx += 1
        product = rng.choice(products)
        write_email(_build_non_claim_email(email_id, product, rng))

    for _ in range(spam_count):
        email_id = f"demo_gen_{next_idx:03d}"
        next_idx += 1
        write_email(_build_spam_email(email_id, rng))

    return written


def remove_generated_demo_emails(inbox_dir: Path = DEFAULT_INBOX_DIR) -> int:
    """Delete generated demo email files and return delete count."""
    deleted = 0
    for path in inbox_dir.glob("demo_gen_*.json"):
        try:
            path.unlink(missing_ok=True)
            deleted += 1
        except Exception:
            continue
    return deleted

