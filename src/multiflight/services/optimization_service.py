"""Offline prompt candidate evaluation and regression workflow."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..db import JobStore
from ..evaluation import RegressionGate
from ..prompts import PromptCompiler, PromptStore
from ..prompts.candidates import CandidateGenerator
from ..scene_registry import SceneRegistry
from .run_service import RunService


class OptimizationService:
    def __init__(
        self,
        *,
        jobs: JobStore,
        scenes: SceneRegistry,
        prompts: PromptStore,
        compiler: PromptCompiler,
        candidates: CandidateGenerator,
        regression: RegressionGate,
        runs: RunService,
        executor: ThreadPoolExecutor,
    ) -> None:
        self.jobs = jobs
        self.scenes = scenes
        self.prompts = prompts
        self.compiler = compiler
        self.candidates = candidates
        self.regression = regression
        self.runs = runs
        self.executor = executor

    def start(
        self, scene_id: str, candidate_count: int, auto_publish: bool
    ) -> dict[str, Any]:
        job_id = f"opt-{uuid.uuid4().hex[:12]}"
        payload = {
            "scene_id": scene_id,
            "candidate_count": candidate_count,
            "auto_publish": auto_publish,
        }
        job = self.jobs.create(job_id, "optimization", payload, "等待提示词优化")
        self.executor.submit(
            self._execute, job_id, scene_id, candidate_count, auto_publish
        )
        return job

    def _execute(
        self, job_id: str, scene_id: str, candidate_count: int, auto_publish: bool
    ) -> None:
        try:
            scene = self.scenes.get(scene_id)
            if scene.status != "enabled":
                raise ValueError(scene.unavailable_reason or "Scene is unavailable")

            champion = self.prompts.get(scene_id)
            baseline_run_id = f"{job_id}-baseline"
            self.jobs.create(
                baseline_run_id,
                "run",
                {"scene_id": scene_id, "prompt_version": champion["version"]},
                "优化任务基线实验",
            )
            self.jobs.update(
                job_id,
                status="running",
                progress=0.05,
                message=f"运行基线提示词 {champion['version']}",
            )
            baseline_result = self.runs.execute_blocking(
                baseline_run_id, scene_id, champion["version"], None
            )
            baseline_eval = baseline_result["evaluation"]
            baseline_protected_hash = baseline_result["prompt"]["protected_hash"]

            reports: list[dict[str, Any]] = []
            definitions = self.candidates.generate(
                candidate_count, baseline_eval.get("failure_labels", []), scene_id=scene_id
            )
            for index, definition in enumerate(definitions, start=1):
                version = _candidate_version(champion["version"], index, job_id)
                self.prompts.add_candidate(
                    scene_id,
                    version,
                    definition.name,
                    definition.description,
                    definition.addendum,
                    champion["version"],
                )
                candidate_run_id = f"{job_id}-candidate-{index}"
                self.jobs.create(
                    candidate_run_id,
                    "run",
                    {"scene_id": scene_id, "prompt_version": version},
                    f"优化候选实验 {index}",
                )
                self.jobs.update(
                    job_id,
                    status="running",
                    progress=0.10 + 0.75 * index / max(1, len(definitions)),
                    message=f"运行候选提示词 {version}",
                )
                candidate_result = self.runs.execute_blocking(
                    candidate_run_id, scene_id, version, None
                )
                candidate_eval = candidate_result["evaluation"]
                regression_report = self.regression.compare(
                    baseline_eval,
                    candidate_eval,
                    candidate_result["prompt"]["protected_hash"]
                    == baseline_protected_hash,
                )
                self.prompts.attach_regression(scene_id, version, regression_report)
                reports.append(
                    {
                        "version": version,
                        "run_id": candidate_run_id,
                        "regression": regression_report,
                    }
                )

            recommended = next(
                (item for item in reports if item["regression"]["improved"]), None
            )
            published = None
            if auto_publish and recommended:
                published = self.prompts.publish(
                    scene_id,
                    recommended["version"],
                    f"automatic publication from {job_id}",
                )
            result = {
                "scene_id": scene_id,
                "baseline_run_id": baseline_run_id,
                "baseline_version": champion["version"],
                "candidates": reports,
                "recommended_version": recommended["version"] if recommended else None,
                "published_version": published["version"] if published else None,
            }
            self.jobs.update(
                job_id,
                status="succeeded",
                progress=1.0,
                message="提示词候选与回归验证完成",
                result=result,
            )
        except Exception as exc:
            self.jobs.update(
                job_id,
                status="failed",
                progress=1.0,
                message="提示词优化失败",
                error=str(exc),
            )


def _candidate_version(base_version: str, index: int, job_id: str) -> str:
    numeric = base_version.split("-", 1)[0].split(".")
    while len(numeric) < 3:
        numeric.append("0")
    numeric[2] = str(int(numeric[2]) + 1)
    return f"{'.'.join(numeric)}-c{index}.{job_id[-6:]}"
