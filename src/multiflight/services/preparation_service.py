"""Validate scene parameters and create reusable trim preparations."""

from __future__ import annotations

import threading
import uuid
from typing import Any

from ..db import JobStore
from ..parameter_registry import SCHEMA_VERSION
from ..scene_registry import SceneRegistry
from ..schemas import EngineFailureParameters
from ..trimming import TrimProvider


class PreparationError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "field_errors": [],
            "retryable": self.code in {"TRIM_SERVICE_UNAVAILABLE"},
        }


class PreparationService:
    def __init__(
        self,
        *,
        jobs: JobStore,
        scenes: SceneRegistry,
        trimmer: TrimProvider,
        execution_lock: threading.Lock,
    ) -> None:
        self.jobs = jobs
        self.scenes = scenes
        self.trimmer = trimmer
        self.execution_lock = execution_lock

    def prepare(
        self, scene_id: str, parameters: EngineFailureParameters
    ) -> dict[str, Any]:
        scene = self.scenes.get(scene_id)
        if scene.status != "enabled":
            raise PreparationError(
                "SCENE_UNAVAILABLE",
                scene.unavailable_reason or "场景不可运行",
            )
        if scene_id != "engine_failure":
            raise PreparationError("SCENE_NOT_SUPPORTED", "当前仅支持场景一配平")

        normalized = parameters.model_dump()
        if normalized["wind_speed_ft_s"] != 0.0:
            raise PreparationError(
                "CAPABILITY_NOT_AVAILABLE",
                "当前模型尚未接入风场，wind_speed_ft_s 只能为 0",
            )

        preparation_id = f"prep-{uuid.uuid4().hex[:12]}"
        self.jobs.create(
            preparation_id,
            "preparation",
            {
                "scene_id": scene_id,
                "schema_version": SCHEMA_VERSION,
                "parameters": normalized,
            },
            "等待配平",
        )
        self.jobs.update(
            preparation_id,
            status="running",
            progress=0.1,
            message="正在计算初始状态和阶段配平",
        )
        try:
            with self.execution_lock:
                trim = self.trimmer.prepare_engine_failure(normalized)
        except Exception as exc:
            self.jobs.update(
                preparation_id,
                status="failed",
                progress=1.0,
                message="配平失败",
                error=str(exc),
            )
            code = (
                "TRIM_SERVICE_UNAVAILABLE"
                if "MATLAB" in str(exc) or "matlab" in str(exc)
                else "TRIM_NOT_CONVERGED"
            )
            raise PreparationError(code, str(exc)) from exc

        result = {
            "preparation_id": preparation_id,
            "scene_id": scene_id,
            "status": "ready",
            "schema_version": SCHEMA_VERSION,
            "normalized_parameters": normalized,
            "validation": {"valid": True, "errors": [], "warnings": []},
            "trim": trim,
        }
        self.jobs.update(
            preparation_id,
            status="succeeded",
            progress=1.0,
            message="参数校验与配平完成",
            result=result,
        )
        return result

    def get_ready(self, preparation_id: str, scene_id: str) -> dict[str, Any]:
        try:
            job = self.jobs.get(preparation_id)
        except KeyError as exc:
            raise PreparationError(
                "PREPARATION_NOT_FOUND", f"配平记录不存在：{preparation_id}", 404
            ) from exc
        if job["kind"] != "preparation":
            raise PreparationError(
                "PREPARATION_NOT_FOUND", f"配平记录不存在：{preparation_id}", 404
            )
        if job["status"] != "succeeded" or not job.get("result"):
            raise PreparationError(
                "PREPARATION_NOT_READY", "配平尚未完成或已经失败"
            )
        result = job["result"]
        if result["scene_id"] != scene_id:
            raise PreparationError(
                "PREPARATION_SCENE_MISMATCH", "配平结果与运行场景不一致"
            )
        return result
