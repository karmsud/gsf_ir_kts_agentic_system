from __future__ import annotations

import json
from pathlib import Path

from backend.common.models import AgentResult
from backend.vector import VectorStore
from .base_agent import AgentBase


class VisionAgent(AgentBase):
    agent_name = "vision-agent"

    def __init__(self, config):
        super().__init__(config)
        self.vector_store = VectorStore(config.chroma_persist_dir)

    def _manifest_path(self, doc_id: str) -> Path:
        return Path(self.config.knowledge_base_path) / "documents" / doc_id / "descriptions.json"

    def _load_manifest(self, doc_id: str) -> dict:
        path = self._manifest_path(doc_id)
        if not path.exists():
            return {"doc_id": doc_id, "images": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_manifest(self, payload: dict) -> str:
        path = self._manifest_path(payload["doc_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(path)

    def execute(self, request: dict) -> AgentResult:
        operation = request.get("operation", "upsert")
        doc_id = request["doc_id"]

        if operation in {"upsert", "initialize"}:
            images = request.get("image_paths", [])
            descriptions = request.get("descriptions", {})
            rows = []
            for idx, image_path in enumerate(images, start=1):
                image_id = f"img_{idx:03d}"
                description = descriptions.get(image_id)
                rows.append(
                    {
                        "image_id": image_id,
                        "filename": Path(image_path).name,
                        "path": image_path,
                        "status": "described" if description else "pending",
                        "description": description,
                    }
                )

            manifest_path = self._save_manifest({"doc_id": doc_id, "images": rows})
            pending = sum(1 for row in rows if row["status"] == "pending")
            confidence = 1.0 if pending == 0 else 0.75
            return self.quality_check(
                AgentResult(
                    success=True,
                    confidence=confidence,
                    data={"doc_id": doc_id, "pending": pending, "manifest_path": manifest_path},
                    reasoning="Generated image description manifest for human-in-the-loop workflow.",
                )
            )

        manifest = self._load_manifest(doc_id)
        images = manifest.get("images", [])

        if operation == "list_pending":
            pending = [row for row in images if row.get("status") != "described"]
            return self.quality_check(
                AgentResult(
                    success=True,
                    confidence=0.95,
                    data={"pending_count": len(pending), "pending_images": pending},
                    reasoning="Listed pending image descriptions.",
                )
            )

        if operation == "status":
            pending_count = sum(1 for row in images if row.get("status") != "described")
            described_count = sum(1 for row in images if row.get("status") == "described")
            return self.quality_check(
                AgentResult(
                    success=True,
                    confidence=0.95,
                    data={"pending_count": pending_count, "described_count": described_count, "pending_images": [row for row in images if row.get("status") != "described"]},
                    reasoning="Computed vision workflow status.",
                )
            )

        if operation == "complete":
            descriptions = request.get("descriptions", {})
            newly_indexed: list[str] = []
            for row in images:
                image_id = row.get("image_id")
                if image_id in descriptions:
                    description = (descriptions.get(image_id) or "").strip()
                    if len(description) < 12:
                        return AgentResult(
                            success=False,
                            confidence=0.2,
                            data={"error": f"description_too_short:{image_id}"},
                            reasoning="Image description must be at least 12 characters.",
                        )
                    row["description"] = description
                    row["status"] = "described"
                    self.vector_store.add_image_description(doc_id=doc_id, source_path=row.get("path", ""), image_id=image_id, description=description)
                    newly_indexed.append(image_id)

            manifest_path = self._save_manifest(manifest)
            pending_count = sum(1 for row in images if row.get("status") != "described")
            described_count = sum(1 for row in images if row.get("status") == "described")
            return self.quality_check(
                AgentResult(
                    success=True,
                    confidence=0.95 if pending_count == 0 else 0.8,
                    data={
                        "pending_count": pending_count,
                        "described_count": described_count,
                        "pending_images": [row for row in images if row.get("status") != "described"],
                        "newly_indexed": newly_indexed,
                        "manifest_path": manifest_path,
                    },
                    reasoning="Completed image descriptions and indexed new descriptions.",
                )
            )

        return AgentResult(success=False, confidence=0.1, data={"error": f"unsupported_operation:{operation}"}, reasoning="Unsupported vision operation requested.")
