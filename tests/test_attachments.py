from pathlib import Path

from app.attachments import extract_attachment_bundle, extract_text_from_attachment


def test_extract_text_from_txt_attachment(tmp_path: Path):
    p = tmp_path / "receipt.txt"
    p.write_text("Order 12345\nPurchased 2026-01-01", encoding="utf-8")

    text, ocr_used = extract_text_from_attachment(p)
    assert "Order 12345" in text
    assert ocr_used is False


def test_extract_attachment_bundle_missing_file(tmp_path: Path):
    missing = tmp_path / "does_not_exist.txt"
    merged, details = extract_attachment_bundle([str(missing)])
    assert merged == ""
    assert len(details) == 1
    assert details[0]["error"] == "file_not_found"

