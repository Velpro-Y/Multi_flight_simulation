"""One-click Dify-driven experiment execution."""

from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from ..db import JobStore
from ..dify_client import DifyClient
from ..evaluation import RunEvaluator
from ..prompts import PromptCompiler, PromptStore
from ..scene_registry import SceneRegistry
from ..settings import RUN_DIR
from ..simulation import SimulationManager


DEFAULT_QUERY = (
    "立即执行一次完整实验。首先调用 reset_simulation，然后严格按照场景提示词，"
    "连续调用 step_simulation，直到工具返回 done=true。不要等待用户确认。"
)


class RunService:
    def __init__(
        self,
        *,
        jobs: JobStore,
        scenes: SceneRegistry,
        prompts: PromptStore,
        compiler: PromptCompiler,
        simulator: SimulationManager,
        dify: DifyClient,
        evaluator: RunEvaluator,
        executor: ThreadPoolExecutor,
        execution_lock: threading.Lock,
    ) -> None:
        self.jobs = jobs
        self.scenes = scenes
        self.prompts = prompts
        self.compiler = compiler
        self.simulator = simulator
        self.dify = dify
        self.evaluator = evaluator
        self.executor = executor
        self.execution_lock = execution_lock

    def start(
        self,
        scene_id: str,
        prompt_version: Optional[str] = None,
        query: Optional[str] = None,
    ) -> dict[str, Any]:
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        payload = {
            "scene_id": scene_id,
            "prompt_version": prompt_version,
            "query": query,
        }
        job = self.jobs.create(run_id, "run", payload, "等待执行")
        self.executor.submit(
            self.execute_blocking,
            run_id,
            scene_id,
            prompt_version,
            query,
        )
        return job

    def execute_blocking(
        self,
        run_id: str,
        scene_id: str,
        prompt_version: Optional[str],
        query: Optional[str],
    ) -> dict[str, Any]:
        try:
            with self.execution_lock:
                return self._execute_locked(run_id, scene_id, prompt_version, query)
        except Exception as exc:
            self.jobs.update(
                run_id,
                status="failed",
                progress=1.0,
                message="实验执行失败",
                error=str(exc),
            )
            raise

    def _execute_locked(
        self,
        run_id: str,
        scene_id: str,
        prompt_version: Optional[str],
        query: Optional[str],
    ) -> dict[str, Any]:
        scene = self.scenes.get(scene_id)
        if scene.status != "enabled":
            raise ValueError(scene.unavailable_reason or f"Scene {scene_id} is unavailable")

        version_record = self.prompts.get(scene_id, prompt_version)
        artifact = self.compiler.compile(
            scene,
            version_record["version"],
            version_record.get("addendum", ""),
        )
        self.jobs.update(
            run_id,
            status="running",
            progress=0.02,
            message=f"已加载提示词 {artifact.version}，等待Dify Agent调用仿真工具",
        )
        self.simulator.begin_run(run_id, scene_id, self._on_progress)

        try:
            dify_result = self.dify.run_agent(
                scene_prompt=artifact.text,
                query=query or DEFAULT_QUERY,
                user=run_id,
            )
            records = self.simulator.snapshot()
            evaluation = self.evaluator.evaluate(
                scene, records, artifact.version, artifact.prompt_hash
            )
            result = {
                "run_id": run_id,
                "scene_id": scene_id,
                "prompt": {
                    "version": artifact.version,
                    "prompt_hash": artifact.prompt_hash,
                    "protected_hash": artifact.protected_hash,
                    "block_hashes": artifact.block_hashes,
                },
                "dify": dify_result,
                "evaluation": evaluation,
                "artifacts": self._write_artifacts(
                    run_id, artifact.text, records, evaluation, dify_result
                ),
            }
            status = "succeeded" if evaluation["passed"] else "completed_with_failures"
            self.jobs.update(
                run_id,
                status=status,
                progress=1.0,
                message="实验完成，已生成自动评估报告",
                result=result,
            )
            return result
        finally:
            self.simulator.finish_run()

    def _on_progress(
        self, run_id: str, step_count: int, result: dict[str, Any]
    ) -> None:
        try:
            scene_id = self.jobs.get(run_id)["payload"]["scene_id"]
            max_steps = self.scenes.get(scene_id).safety.max_steps
            progress = min(0.90, 0.05 + 0.80 * step_count / max_steps)
            phase = result.get("state", {}).get("flight_phase", "UNKNOWN")
            self.jobs.update(
                run_id,
                status="running",
                progress=progress,
                message=f"仿真第{step_count}步，当前阶段：{phase}",
            )
        except Exception:
            # Progress reporting must never interrupt the tool callback.
            return

    @staticmethod
    def _write_artifacts(
        run_id: str,
        prompt_text: str,
        records: list[dict[str, Any]],
        evaluation: dict[str, Any],
        dify_result: dict[str, Any],
    ) -> dict[str, str]:
        run_dir = RUN_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        paths = {
            "prompt": run_dir / "compiled_prompt.md",
            "records": run_dir / "records.json",
            "evaluation": run_dir / "evaluation.json",
            "dify": run_dir / "dify_result.json",
        }
        paths["prompt"].write_text(prompt_text, encoding="utf-8")
        paths["records"].write_text(_json(records), encoding="utf-8")
        paths["evaluation"].write_text(_json(evaluation), encoding="utf-8")
        paths["dify"].write_text(_json(dify_result), encoding="utf-8")
        return {name: str(path) for name, path in paths.items()}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)

