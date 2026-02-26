"""
Attachment handling utilities.

Supports:
- Persisting inbound attachments under outbox/attachments.
- Extracting best-effort text from common file types.
- Optional OCR for images when pytesseract is installed.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Tuple


BASE_DIR = Path(__file__).parent.parent
ATTACHMENTS_DIR = BASE_DIR / "outbox" / "attachments"


@dataclass
class AttachmentTextResult:
    filename: str
    path: str
    text_length: int
    text_excerpt: str
    ocr_used: bool
    error: str


def _sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "attachment.bin"


def _unique_path(target_dir: Path, filename: str) -> Path:
    safe_name = _sanitize_filename(filename)
    path = target_dir / safe_name
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate = target_dir / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def get_attachment_dir(email_id: str) -> Path:
    out = ATTACHMENTS_DIR / (email_id or "unknown_email")
    out.mkdir(parents=True, exist_ok=True)
    return out


def save_attachment_bytes(email_id: str, filename: str, data: bytes) -> Path:
    """Persist a single attachment and return the saved path."""
    target_dir = get_attachment_dir(email_id)
    path = _unique_path(target_dir, filename)
    path.write_bytes(data)
    return path


def _extract_text_from_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts: List[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            parts.append("")
    return "\n".join(parts).strip()


def _extract_text_from_image_with_ocr(path: Path) -> Tuple[str, bool]:
    try:
        import pytesseract
        from PIL import Image
    except Exception:
        return "", False

    try:
        text = pytesseract.image_to_string(Image.open(path))
        return (text or "").strip(), True
    except Exception:
        return "", False


def extract_text_from_attachment(path: Path) -> Tuple[str, bool]:
    """
    Extract text from one attachment.

    Returns (text, ocr_used).
    """
    suffix = path.suffix.lower()

    if suffix in {".txt", ".md", ".json", ".csv", ".log", ".yaml", ".yml"}:
        return path.read_text(encoding="utf-8", errors="replace"), False

    if suffix == ".pdf":
        return _extract_text_from_pdf(path), False

    if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}:
        text, used = _extract_text_from_image_with_ocr(path)
        return text, used

    # Fallback: best-effort text decode for unknown types.
    try:
        return path.read_text(encoding="utf-8", errors="replace"), False
    except Exception:
        return "", False


def extract_attachment_bundle(paths: List[str], max_chars: int = 20000) -> Tuple[str, List[Dict]]:
    """
    Extract text from a list of attachment paths.

    Returns:
    - Combined extracted text (truncated to max_chars).
    - A list of extraction metadata dicts.
    """
    combined_parts: List[str] = []
    details: List[AttachmentTextResult] = []

    for raw in paths or []:
        p = Path(raw)
        if not p.exists() or not p.is_file():
            details.append(
                AttachmentTextResult(
                    filename=p.name or str(raw),
                    path=str(p),
                    text_length=0,
                    text_excerpt="",
                    ocr_used=False,
                    error="file_not_found",
                )
            )
            continue

        try:
            text, ocr_used = extract_text_from_attachment(p)
            text = (text or "").strip()
            if text:
                header = f"[ATTACHMENT: {p.name}]\n{text}"
                combined_parts.append(header)
            details.append(
                AttachmentTextResult(
                    filename=p.name,
                    path=str(p),
                    text_length=len(text),
                    text_excerpt=text[:280],
                    ocr_used=ocr_used,
                    error="",
                )
            )
        except Exception as e:
            details.append(
                AttachmentTextResult(
                    filename=p.name,
                    path=str(p),
                    text_length=0,
                    text_excerpt="",
                    ocr_used=False,
                    error=str(e),
                )
            )

    merged = "\n\n".join([t for t in combined_parts if t]).strip()
    if len(merged) > max_chars:
        merged = merged[:max_chars]
    return merged, [asdict(d) for d in details]

