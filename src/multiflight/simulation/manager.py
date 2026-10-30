"""Single-worker simulation manager used by Dify tool callbacks."""

from __future__ import annotations

import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .flight_env import FlightEnv


ProgressCallback = Callable[[str, int, dict[str, Any]], None]


class SimulationManager:
    """Own the active FlightEnv and capture auditable decision records.

    The migrated MATLAB engine is a singleton, so the demo intentionally allows
    one active simulation at a time. The outer job service provides the global
    execution lock; this class serializes individual tool callbacks.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._env: Optional[FlightEnv] = None
        self._active_run_id: Optional[str] = None
        self._scene_id: Optional[str] = None
        self._records: list[dict[str, Any]] = []
        self._progress_callback: Optional[ProgressCallback] = None

    def begin_run(
        self,
        run_id: str,
        scene_id: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        with self._lock:
            self._active_run_id = run_id
            self._scene_id = scene_id
            self._env = None
            self._records = []
            self._progress_callback = progress_callback

    def ensure_manual_run(self) -> None:
        if self._active_run_id is None:
            self.begin_run(f"manual-{uuid.uuid4().hex[:8]}", "engine_failure")

    def reset(self) -> dict[str, Any]:
        with self._lock:
            self.ensure_manual_run()
            self._env = FlightEnv(run_id=self._active_run_id or "manual")
            result = self._env.reset()
            self._records.append(
                {
                    "sequence": 0,
                    "timestamp": _utc_now(),
                    "kind": "reset",
                    "result": deepcopy(result),
                }
            )
            self._notify(result)
            return result

    def step(self, action: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._env is None:
                raise RuntimeError("Simulation is not reset. Call /reset first.")
            state_before = deepcopy(self._env.get_state())
            result = self._env.step(action)
            record = {
                "sequence": len(self._records),
                "timestamp": _utc_now(),
                "kind": "step",
                "state_before": state_before,
                "raw_action": deepcopy(action),
                "applied_action": deepcopy(result.get("applied_action", {})),
                "result": deepcopy(result),
            }
            self._records.append(record)
            self._notify(result)
            return result

    def status(self) -> dict[str, Any]:
        with self._lock:
            state = self._env.get_state() if self._env is not None else None
            return {
                "active_run_id": self._active_run_id,
                "scene_id": self._scene_id,
                "ready": self._env is not None,
                "steps": sum(1 for item in self._records if item["kind"] == "step"),
                "state": state,
            }

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return deepcopy(self._records)

    def finish_run(self) -> None:
        with self._lock:
            self._progress_callback = None
            self._active_run_id = None
            self._scene_id = None
            self._env = None

    def _notify(self, result: dict[str, Any]) -> None:
        if self._progress_callback and self._active_run_id:
            step_count = sum(1 for item in self._records if item["kind"] == "step")
            self._progress_callback(self._active_run_id, step_count, result)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
