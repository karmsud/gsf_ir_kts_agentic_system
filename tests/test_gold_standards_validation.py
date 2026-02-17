from pathlib import Path

from scripts.validate_gold_standards import validate_manifest


def test_gold_standards_manifest_validation_passes():
    manifest_path = Path("data/gold_standards_manifest.json")
    report = validate_manifest(manifest_path)
    assert report["passed"] is True
    assert report["failures"] == 0
    assert report["total"] >= 4
