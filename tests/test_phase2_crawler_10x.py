from __future__ import annotations

from pathlib import Path

import pytest

from backend.agents import CrawlerAgent
from backend.common.manifest import ManifestStore
from config import load_config


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_crawler_10_scenarios(tmp_path: Path):
    cfg = load_config()
    cfg.manifest_path = str(tmp_path / "manifest.json")
    agent = CrawlerAgent(cfg)

    data_dir = tmp_path / "src"
    data_dir.mkdir()

    scenarios = []

    scenarios.append(agent.execute({"paths": [str(data_dir)]}))

    for index in range(3):
        _write(data_dir / f"doc_{index}.md", f"content {index}")
    scenarios.append(agent.execute({"paths": [str(data_dir)]}))

    manifest = ManifestStore(cfg.manifest_path)
    changes = scenarios[-1].data["changes"]
    manifest.upsert_files(changes.new_files + changes.modified_files)

    scenarios.append(agent.execute({"paths": [str(data_dir)]}))

    _write(data_dir / "doc_1.md", "changed")
    scenarios.append(agent.execute({"paths": [str(data_dir)]}))

    scenarios.append(agent.execute({"paths": [str(data_dir)], "force": True}))

    (data_dir / "doc_2.md").unlink()
    scenarios.append(agent.execute({"paths": [str(data_dir)]}))

    scenarios.append(agent.execute({"paths": [str(data_dir)], "dry_run": True}))

    huge_file = data_dir / "huge.md"
    huge_file.write_text("x" * 1024, encoding="utf-8")
    scenarios.append(agent.execute({"paths": [str(data_dir)], "max_file_size_mb": 0}))

    scenarios.append(agent.execute({"paths": [str(tmp_path / 'missing')]}))

    unsupported = data_dir / "skip.bin"
    unsupported.write_bytes(b"abc")
    scenarios.append(agent.execute({"paths": [str(data_dir)]}))

    assert len(scenarios) == 10
    assert scenarios[0].success
    assert len(scenarios[1].data["changes"].new_files) >= 3
    assert scenarios[2].data["changes"].unchanged_files >= 1
    assert len(scenarios[3].data["changes"].modified_files) >= 1
    assert len(scenarios[4].data["changes"].modified_files) >= 1
    assert len(scenarios[5].data["changes"].deleted_files) >= 1
    assert scenarios[6].data["dry_run"] is True
    assert scenarios[7].data["changes"].warnings
    assert scenarios[8].data["changes"].errors
    assert scenarios[9].success
