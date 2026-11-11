"""File-backed prompt version registry with atomic publication."""

from __future__ import annotations

import json
import shutil
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..settings import PROMPT_DIR, PROMPT_REGISTRY_FILE


class PromptStore:
    def __init__(
        self,
        registry_file: Path = PROMPT_REGISTRY_FILE,
        seed_file: Path = PROMPT_DIR / "seed_registry.json",
    ) -> None:
        self.registry_file = registry_file
        self.seed_file = seed_file
        self._lock = threading.RLock()
        if not self.registry_file.exists():
            self.registry_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.seed_file, self.registry_file)
        # Add newly supported scenes without replacing existing versions/results.
        with self._lock:
            data = self._load_unlocked()
            seeds = json.loads(self.seed_file.read_text(encoding="utf-8"))
            missing = {key: value for key, value in seeds.items() if key not in data}
            if missing:
                data.update(missing)
            changed = bool(missing)
            for scene_id, seed in seeds.items():
                for version, record in seed["versions"].items():
                    if version not in data[scene_id]["versions"]:
                        data[scene_id]["versions"][version] = record
                        changed = True
            if changed:
                self._save_unlocked(data)

    def list_versions(self, scene_id: str) -> dict[str, Any]:
        data = self._load()
        if scene_id not in data:
            raise KeyError(f"No prompt versions for scene {scene_id}")
        return deepcopy(data[scene_id])

    def get(self, scene_id: str, version: Optional[str] = None) -> dict[str, Any]:
        scene_data = self.list_versions(scene_id)
        selected = version or scene_data["published"]
        try:
            return deepcopy(scene_data["versions"][selected])
        except KeyError as exc:
            raise KeyError(f"Unknown prompt version {scene_id}:{selected}") from exc

    def add_candidate(
        self,
        scene_id: str,
        version: str,
        name: str,
        description: str,
        addendum: str,
        created_from: str,
    ) -> dict[str, Any]:
        with self._lock:
            data = self._load_unlocked()
            scene_data = data[scene_id]
            if version in scene_data["versions"]:
                return deepcopy(scene_data["versions"][version])
            record = {
                "version": version,
                "status": "candidate",
                "name": name,
                "description": description,
                "addendum": addendum,
                "created_from": created_from,
                "created_at": _utc_now(),
                "regression_report": None,
            }
            scene_data["versions"][version] = record
            self._save_unlocked(data)
            return deepcopy(record)

    def attach_regression(
        self, scene_id: str, version: str, report: dict[str, Any]
    ) -> None:
        with self._lock:
            data = self._load_unlocked()
            data[scene_id]["versions"][version]["regression_report"] = report
            self._save_unlocked(data)

    def publish(self, scene_id: str, version: str, reason: str) -> dict[str, Any]:
        with self._lock:
            data = self._load_unlocked()
            scene_data = data[scene_id]
            candidate = scene_data["versions"][version]
            report = candidate.get("regression_report")
            if not report or not report.get("passed"):
                raise ValueError("Prompt version has no passing regression report")
            previous = scene_data["published"]
            scene_data["versions"][previous]["status"] = "superseded"
            candidate["status"] = "published"
            candidate["published_at"] = _utc_now()
            candidate["publish_reason"] = reason
            scene_data["published"] = version
            self._save_unlocked(data)
            return deepcopy(candidate)

    def _load(self) -> dict[str, Any]:
        with self._lock:
            return self._load_unlocked()

    def _load_unlocked(self) -> dict[str, Any]:
        return json.loads(self.registry_file.read_text(encoding="utf-8"))

    def _save_unlocked(self, data: dict[str, Any]) -> None:
        temp = self.registry_file.with_suffix(".tmp")
        temp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temp.replace(self.registry_file)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

