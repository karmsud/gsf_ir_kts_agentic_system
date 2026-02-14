from __future__ import annotations

import re
from difflib import unified_diff

from backend.common.models import AgentResult
from .base_agent import AgentBase


class VersionAgent(AgentBase):
    agent_name = "version-agent"

    @staticmethod
    def _extract_sections(text: str) -> dict[str, str]:
        sections: dict[str, str] = {}
        current = "_root"
        buffer: list[str] = []
        for line in text.splitlines():
            if line.strip().startswith("#"):
                sections[current] = "\n".join(buffer).strip()
                current = line.strip().lstrip("#").strip() or "untitled"
                buffer = []
            else:
                buffer.append(line)
        sections[current] = "\n".join(buffer).strip()
        return {k: v for k, v in sections.items() if k}

    @staticmethod
    def _extract_image_refs(text: str) -> set[str]:
        return set(re.findall(r"!\[[^\]]*\]\(([^\)]+)\)", text))

    def execute(self, request: dict) -> AgentResult:
        old_text = request.get("old_text", "")
        new_text = request.get("new_text", "")
        old_version = int(request.get("old_version", 0))

        diff_lines = list(
            unified_diff(
                old_text.splitlines(),
                new_text.splitlines(),
                fromfile="old",
                tofile="new",
                lineterm="",
            )
        )

        old_sections = self._extract_sections(old_text)
        new_sections = self._extract_sections(new_text)
        old_keys = set(old_sections.keys())
        new_keys = set(new_sections.keys())

        added_sections = sorted(new_keys - old_keys)
        removed_sections = sorted(old_keys - new_keys)
        modified_sections = sorted([key for key in (old_keys & new_keys) if old_sections[key] != new_sections[key]])

        old_images = self._extract_image_refs(old_text)
        new_images = self._extract_image_refs(new_text)
        added_images = sorted(new_images - old_images)
        removed_images = sorted(old_images - new_images)

        changed_chunks = list(range(len(added_sections) + len(modified_sections)))
        summary = (
            f"Added sections: {len(added_sections)}, removed sections: {len(removed_sections)}, "
            f"modified sections: {len(modified_sections)}, added images: {len(added_images)}, removed images: {len(removed_images)}"
        )

        changed = old_text != new_text

        return self.quality_check(
            AgentResult(
                success=True,
                confidence=0.95,
                data={
                    "doc_id": request.get("doc_id"),
                    "old_version": old_version,
                    "new_version": old_version + 1,
                    "diff": "\n".join(diff_lines),
                    "changed": changed,
                    "added_sections": added_sections,
                    "removed_sections": removed_sections,
                    "modified_sections": modified_sections,
                    "added_images": added_images,
                    "removed_images": removed_images,
                    "changed_chunks": changed_chunks,
                    "summary": summary,
                },
                reasoning="Computed section-level and image-level version diff.",
            )
        )
