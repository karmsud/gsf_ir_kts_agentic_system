from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "simple"


def main() -> None:
    FIXTURE.mkdir(parents=True, exist_ok=True)
    (FIXTURE / "toolx_user_guide.md").write_text(
        "# ToolX User Guide\n\nHow to reset password in ToolX.\nStep 1: Open Settings.\nStep 2: Security tab.\n",
        encoding="utf-8",
    )
    (FIXTURE / "toolx_release_notes.md").write_text(
        "# ToolX Release Notes\n\nVersion 2.1 includes authentication fixes and onboarding improvements.\n",
        encoding="utf-8",
    )
    print("Demo fixtures seeded.")


if __name__ == "__main__":
    main()
