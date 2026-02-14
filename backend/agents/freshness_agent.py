from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from backend.common.models import AgentResult, FreshnessReport
from .base_agent import AgentBase


class FreshnessAgent(AgentBase):
    agent_name = "freshness-agent"

    def execute(self, request: dict) -> AgentResult:
        scope = request.get("scope", "all")
        threshold_days = int(request.get("threshold_days", self.config.stale_threshold_days))
        include_images = bool(request.get("include_images", True))
        docs_root = Path(self.config.knowledge_base_path) / "documents"
        now = datetime.now(timezone.utc)

        current = aging = stale = unknown = 0
        stale_documents: list[dict[str, str]] = []
        stale_images: list[dict[str, str]] = []
        total = 0

        for doc_dir in docs_root.glob("*"):
            if not doc_dir.is_dir():
                continue
            metadata = doc_dir / "metadata.json"
            if not metadata.exists():
                total += 1
                unknown += 1
                continue

            metadata_json = json.loads(metadata.read_text(encoding="utf-8"))
            if scope not in {"all", metadata_json.get("doc_type"), *metadata_json.get("tools", [])}:
                continue

            total += 1
            modified = datetime.fromtimestamp(metadata.stat().st_mtime, tz=timezone.utc)
            age_days = (now - modified).days
            if age_days <= threshold_days:
                current += 1
            elif age_days <= threshold_days * 2:
                aging += 1
            else:
                stale += 1
                stale_documents.append({"doc_id": doc_dir.name, "age_days": str(age_days), "doc_type": metadata_json.get("doc_type", "UNKNOWN")})

            if include_images:
                description_manifest = doc_dir / "descriptions.json"
                if description_manifest.exists():
                    payload = json.loads(description_manifest.read_text(encoding="utf-8"))
                    for image in payload.get("images", []):
                        if image.get("status") == "pending":
                            stale_images.append({"doc_id": doc_dir.name, "image_id": image.get("image_id", ""), "reason": "pending_description"})

        recommendations: list[str] = []
        if stale_documents:
            recommendations.append("Prioritize updates for stale documents listed in report.")
        if stale_images:
            recommendations.append("Complete pending image descriptions to improve multimodal retrieval quality.")
        if not recommendations:
            recommendations.append("No immediate freshness actions required.")

        report = FreshnessReport(
            total_documents=total,
            current=current,
            aging=aging,
            stale=stale,
            unknown=unknown,
            stale_documents=stale_documents,
            stale_images=stale_images,
            recommendations=recommendations,
        )

        confidence = 0.95 if total else 0.6
        return self.quality_check(
            AgentResult(
                success=True,
                confidence=confidence,
                data={"freshness_report": report},
                reasoning="Calculated freshness buckets from local metadata age.",
            )
        )
