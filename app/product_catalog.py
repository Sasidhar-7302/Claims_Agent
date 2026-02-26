"""
Product catalog configuration and validation helpers.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List


BASE_DIR = Path(__file__).parent.parent
DEFAULT_PRODUCTS_FILE = BASE_DIR / "data" / "products.json"


def get_products_file() -> Path:
    """Return active products catalog path."""
    value = (os.getenv("PRODUCTS_FILE") or "").strip()
    return Path(value) if value else DEFAULT_PRODUCTS_FILE


def load_products_catalog() -> Dict[str, Any]:
    """Load the current products catalog JSON."""
    path = get_products_file()
    if not path.exists():
        return {"products": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"products": []}


def save_products_catalog(data: Dict[str, Any], path: Path | None = None) -> Path:
    """Save a products catalog to disk and return the output path."""
    out = path or get_products_file()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return out


def validate_products_catalog(data: Dict[str, Any]) -> List[str]:
    """Validate minimum schema requirements for products catalog."""
    errors: List[str] = []
    if not isinstance(data, dict):
        return ["Root JSON must be an object."]

    products = data.get("products")
    if not isinstance(products, list):
        return ["Field `products` must be a list."]

    seen_ids = set()
    for i, product in enumerate(products):
        prefix = f"products[{i}]"
        if not isinstance(product, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        pid = (product.get("product_id") or "").strip()
        name = (product.get("name") or "").strip()
        aliases = product.get("aliases", [])
        policy_file = (product.get("policy_file") or "").strip()
        if not pid:
            errors.append(f"{prefix}.product_id is required.")
        if not name:
            errors.append(f"{prefix}.name is required.")
        if pid and pid in seen_ids:
            errors.append(f"Duplicate product_id: {pid}")
        seen_ids.add(pid)
        if aliases is not None and not isinstance(aliases, list):
            errors.append(f"{prefix}.aliases must be a list.")
        if not policy_file:
            errors.append(f"{prefix}.policy_file is required.")

    return errors

