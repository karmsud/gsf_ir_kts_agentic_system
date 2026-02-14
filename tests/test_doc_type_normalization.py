"""
Unit tests for canonical DocType normalization.

Verifies that normalize_doc_type() correctly handles:
- Common alias mappings (RELEASE_NOTES -> RELEASE_NOTE)
- Case normalization (lowercase -> UPPERCASE)
- Format normalization (hyphens, spaces -> underscores)
- Unknown types -> UNKNOWN
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.common.doc_types import normalize_doc_type, RELEASE_NOTE, SOP, TROUBLESHOOT, USER_GUIDE, UNKNOWN


def test_release_note_aliases():
    """Test all release note variant mappings"""
    assert normalize_doc_type("release notes") == RELEASE_NOTE
    assert normalize_doc_type("RELEASE_NOTES") == RELEASE_NOTE
    assert normalize_doc_type("Release-Note") == RELEASE_NOTE
    assert normalize_doc_type("Release Note") == RELEASE_NOTE
    assert normalize_doc_type("RELEASE") == RELEASE_NOTE
    assert normalize_doc_type("changelog") == RELEASE_NOTE
    assert normalize_doc_type("CHANGELOGS") == RELEASE_NOTE
    print("✅ Release note aliases: PASS")


def test_sop_aliases():
    """Test SOP variant mappings"""
    assert normalize_doc_type("sop") == SOP
    assert normalize_doc_type("SOP") == SOP
    assert normalize_doc_type("sops") == SOP
    assert normalize_doc_type("SOPS") == SOP
    assert normalize_doc_type("runbook") == SOP
    assert normalize_doc_type("procedure") == SOP
    assert normalize_doc_type("standard operating procedure") == SOP
    print("✅ SOP aliases: PASS")


def test_troubleshoot_aliases():
    """Test troubleshooting variant mappings"""
    assert normalize_doc_type("troubleshoot") == TROUBLESHOOT
    assert normalize_doc_type("TROUBLESHOOT") == TROUBLESHOOT
    assert normalize_doc_type("troubleshooting") == TROUBLESHOOT
    assert normalize_doc_type("TROUBLESHOOTING") == TROUBLESHOOT
    assert normalize_doc_type("troubleshooting guide") == TROUBLESHOOT
    print("✅ Troubleshoot aliases: PASS")


def test_user_guide_aliases():
    """Test user guide variant mappings"""
    assert normalize_doc_type("user guide") == USER_GUIDE
    assert normalize_doc_type("USER_GUIDE") == USER_GUIDE
    assert normalize_doc_type("userguide") == USER_GUIDE
    assert normalize_doc_type("USERGUIDE") == USER_GUIDE
    assert normalize_doc_type("user guides") == USER_GUIDE
    assert normalize_doc_type("guide") == USER_GUIDE
    assert normalize_doc_type("documentation") == USER_GUIDE
    print("✅ User guide aliases: PASS")


def test_case_normalization():
    """Test uppercase normalization"""
    assert normalize_doc_type("sop") == SOP
    assert normalize_doc_type("Sop") == SOP
    assert normalize_doc_type("SOP") == SOP
    assert normalize_doc_type("release note") == RELEASE_NOTE
    assert normalize_doc_type("Release Note") == RELEASE_NOTE
    assert normalize_doc_type("RELEASE_NOTE") == RELEASE_NOTE
    print("✅ Case normalization: PASS")


def test_format_normalization():
    """Test hyphen/space -> underscore normalization"""
    assert normalize_doc_type("release-note") == RELEASE_NOTE
    assert normalize_doc_type("release_note") == RELEASE_NOTE
    assert normalize_doc_type("release note") == RELEASE_NOTE
    assert normalize_doc_type("user-guide") == USER_GUIDE
    assert normalize_doc_type("user_guide") == USER_GUIDE
    assert normalize_doc_type("user guide") == USER_GUIDE
    print("✅ Format normalization: PASS")


def test_unknown_types():
    """Test unrecognized types map to UNKNOWN"""
    assert normalize_doc_type("unknown_type_x") == UNKNOWN
    assert normalize_doc_type("random") == UNKNOWN
    assert normalize_doc_type("foobar") == UNKNOWN
    assert normalize_doc_type("") == UNKNOWN
    assert normalize_doc_type(None) == UNKNOWN
    print("✅ Unknown types: PASS")


def test_identity_mappings():
    """Test canonical types remain unchanged"""
    assert normalize_doc_type("RELEASE_NOTE") == RELEASE_NOTE
    assert normalize_doc_type("SOP") == SOP
    assert normalize_doc_type("TROUBLESHOOT") == TROUBLESHOOT
    assert normalize_doc_type("USER_GUIDE") == USER_GUIDE
    assert normalize_doc_type("UNKNOWN") == UNKNOWN
    print("✅ Identity mappings: PASS")


def test_whitespace_handling():
    """Test whitespace trimming"""
    assert normalize_doc_type("  sop  ") == SOP
    assert normalize_doc_type("\trelease note\n") == RELEASE_NOTE
    assert normalize_doc_type("  user guide  ") == USER_GUIDE
    print("✅ Whitespace handling: PASS")


if __name__ == "__main__":
    print("=" * 60)
    print("DocType Normalization Unit Tests")
    print("=" * 60)
    
    test_release_note_aliases()
    test_sop_aliases()
    test_troubleshoot_aliases()
    test_user_guide_aliases()
    test_case_normalization()
    test_format_normalization()
    test_unknown_types()
    test_identity_mappings()
    test_whitespace_handling()
    
    print("=" * 60)
    print("✅ ALL TESTS PASSED")
    print("=" * 60)
