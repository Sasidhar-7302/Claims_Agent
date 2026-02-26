import json
from pathlib import Path

from app.demo_data import generate_demo_emails, remove_generated_demo_emails


def test_generate_demo_emails(tmp_path: Path):
    created = generate_demo_emails(
        inbox_dir=tmp_path,
        claim_count=2,
        non_claim_count=1,
        spam_count=1,
        seed=123,
    )
    assert len(created) == 4
    assert all(p.exists() for p in created)

    sample = json.loads(created[0].read_text(encoding="utf-8"))
    assert sample.get("metadata", {}).get("generated") is True


def test_remove_generated_demo_emails(tmp_path: Path):
    # Create two generated files and one non-generated file.
    (tmp_path / "demo_gen_001.json").write_text("{}", encoding="utf-8")
    (tmp_path / "demo_gen_002.json").write_text("{}", encoding="utf-8")
    (tmp_path / "claim_001.json").write_text("{}", encoding="utf-8")

    removed = remove_generated_demo_emails(tmp_path)
    assert removed == 2
    assert (tmp_path / "claim_001.json").exists()

