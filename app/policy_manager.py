"""
Policy document ingestion and metadata management.

This module supports:
- Extracting text from uploaded policy documents (txt/md/pdf).
- Writing normalized policy text files to a target directory.
- Maintaining a simple index.json for policy metadata.
"""

from __future__ import annotations

import json
import re
import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class PolicyIndexEntry:
    policy_id: str
    product_id: str
    product_name: str
    policy_file: str
    version: str
    effective_date: str
    exclusion_keywords: List[str]
    requirements: List[str]


def _safe_stem(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip())
    stem = stem.strip("._-")
    return stem or "policy"


def extract_text_from_bytes(filename: str, data: bytes) -> str:
    """
    Extract text from an uploaded document.

    Supported:
    - .txt, .md
    - .pdf (best-effort text extraction; scanned PDFs require OCR)
    """
    suffix = (Path(filename).suffix or "").lower()
    if suffix in (".txt", ".md"):
        return data.decode("utf-8", errors="replace")

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except Exception as e:
            raise RuntimeError(f"pypdf not available for PDF extraction: {e}") from e

        reader = PdfReader(io.BytesIO(data))
        parts: List[str] = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                parts.append("")
        text = "\n".join(parts).strip()
        if not text:
            raise RuntimeError("No extractable text found in PDF (may require OCR).")
        return text

    raise ValueError(f"Unsupported policy file type: {suffix}")


def write_policy_text(policies_dir: Path, original_filename: str, text: str) -> str:
    """
    Write extracted policy text as a .txt file into policies_dir.

    Returns the created filename (basename only).
    """
    policies_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(Path(original_filename).stem)
    out_name = f"{stem}.txt"
    out_path = policies_dir / out_name

    # Avoid overwriting existing files by suffixing.
    if out_path.exists():
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        out_name = f"{stem}_{ts}.txt"
        out_path = policies_dir / out_name

    out_path.write_text(text, encoding="utf-8")
    return out_name


def load_policy_index(index_file: Path) -> Dict[str, Any]:
    if not index_file.exists():
        return {"policies": []}
    try:
        return json.loads(index_file.read_text(encoding="utf-8"))
    except Exception:
        return {"policies": []}


def save_policy_index(index_file: Path, data: Dict[str, Any]) -> None:
    index_file.parent.mkdir(parents=True, exist_ok=True)
    index_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def upsert_policy_entry(index_file: Path, entry: PolicyIndexEntry) -> None:
    data = load_policy_index(index_file)
    policies = list(data.get("policies", []) or [])

    new_item = {
        "policy_id": entry.policy_id,
        "product_id": entry.product_id,
        "product_name": entry.product_name,
        "policy_file": entry.policy_file,
        "version": entry.version,
        "effective_date": entry.effective_date,
        "exclusion_keywords": entry.exclusion_keywords,
        "requirements": entry.requirements,
    }

    replaced = False
    for idx, item in enumerate(policies):
        if item.get("policy_id") == entry.policy_id:
            policies[idx] = new_item
            replaced = True
            break

    if not replaced:
        policies.append(new_item)

    data["policies"] = policies
    save_policy_index(index_file, data)


def normalize_keywords(text: str) -> List[str]:
    items = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        line = line.lstrip("-").strip()
        if line:
            items.append(line)
    return items


def normalize_requirements(reqs: List[str]) -> List[str]:
    out = []
    for r in reqs or []:
        r = (r or "").strip()
        if r:
            out.append(r)
    return out
