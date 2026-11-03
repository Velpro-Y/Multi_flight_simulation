"""FastAPI entry point for the isolated multi-scene demo."""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .db import JobStore
from .dify_client import DifyClient
from .evaluation import RegressionGate, RunEvaluator
from .prompts import PromptCompiler, PromptStore
from .prompts.candidates import CandidateGenerator
from .parameter_registry import ParameterRegistry
from .scene_registry import SceneRegistry
from .schemas import (
    Action,
    OptimizationRequest,
    PreparationRequest,
    PublishRequest,
    RunRequest,
    SessionRequest,
)
from .services.optimization_service import OptimizationService
from .services.preparation_service import PreparationError, PreparationService
from .services.run_service import RunService
from .settings import LOG_LEVEL
from .simulation import SimulationManager
from .trimming import MatlabTrimProvider


logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(
    title="Multi Flight Simulation Demo",
    version="0.2.0-dev",
    description=(
        "独立的多场景飞行仿真、Dify Agent调用、提示词优化和回归验证服务。"
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

jobs = JobStore()
scenes = SceneRegistry()
prompts = PromptStore()
compiler = PromptCompiler()
simulator = SimulationManager()
dify = DifyClient()
evaluator = RunEvaluator()
regression = RegressionGate()
candidate_generator = CandidateGenerator()
executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="multiflight")
execution_lock = threading.Lock()
parameter_registry = ParameterRegistry()
preparation_service = PreparationService(
    jobs=jobs,
    scenes=scenes,
    trimmer=MatlabTrimProvider(),
    execution_lock=execution_lock,
)

run_service = RunService(
    jobs=jobs,
    scenes=scenes,
    prompts=prompts,
    compiler=compiler,
    simulator=simulator,
    dify=dify,
    evaluator=evaluator,
    executor=executor,
    execution_lock=execution_lock,
)
optimization_service = OptimizationService(
    jobs=jobs,
    scenes=scenes,
    prompts=prompts,
    compiler=compiler,
    candidates=candidate_generator,
    regression=regression,
    runs=run_service,
    executor=executor,
)


@app.get("/health", tags=["system"])
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "dify_configured": dify.configured(),
        "simulation": simulator.status(),
    }


# ---------------------------------------------------------------------------
# Dify custom tool compatibility endpoints
# ---------------------------------------------------------------------------


@app.post("/reset", tags=["dify-tools"])
def reset_simulation() -> dict[str, Any]:
    try:
        return simulator.reset()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/step", tags=["dify-tools"])
def step_simulation(action: Action) -> dict[str, Any]:
    try:
        return simulator.step(action.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/status", tags=["dify-tools"])
def simulation_status() -> dict[str, Any]:
    return simulator.status()


# ---------------------------------------------------------------------------
# Scene and prompt APIs for a future front end
# ---------------------------------------------------------------------------


@app.get("/api/scenarios", tags=["scenes"])
def list_scenarios() -> list[dict[str, Any]]:
    return [scene.model_dump() for scene in scenes.list()]


@app.get("/api/scenarios/{scene_id}", tags=["scenes"])
def get_scene(scene_id: str) -> dict[str, Any]:
    try:
        return scenes.get(scene_id).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/scenarios/{scene_id}/parameters", tags=["scenes"])
def get_scene_parameters(scene_id: str) -> dict[str, Any]:
    try:
        scenes.get(scene_id)
        return parameter_registry.schema(scene_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/simulations/prepare", tags=["simulations"])
def prepare_simulation(request: PreparationRequest) -> dict[str, Any]:
    try:
        return preparation_service.prepare(request.scene_id, request.parameters)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PreparationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc


@app.get(
    "/api/simulations/preparations/{preparation_id}", tags=["simulations"]
)
def get_preparation(preparation_id: str) -> dict[str, Any]:
    return _get_job(preparation_id, expected_kind="preparation")


@app.get("/api/prompts/{scene_id}/versions", tags=["prompts"])
def list_prompt_versions(scene_id: str) -> dict[str, Any]:
    try:
        return prompts.list_versions(scene_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/prompts/{scene_id}/compiled", tags=["prompts"])
def get_compiled_prompt(
    scene_id: str, version: Optional[str] = None
) -> dict[str, Any]:
    try:
        scene = scenes.get(scene_id)
        record = prompts.get(scene_id, version)
        artifact = compiler.compile(
            scene, record["version"], record.get("addendum", "")
        )
        return {
            "scene_id": scene_id,
            "version": artifact.version,
            "prompt_hash": artifact.prompt_hash,
            "protected_hash": artifact.protected_hash,
            "block_hashes": artifact.block_hashes,
            "text": artifact.text,
        }
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(
    "/api/prompts/{scene_id}/versions/{version}/publish", tags=["prompts"]
)
def publish_prompt(
    scene_id: str, version: str, request: PublishRequest
) -> dict[str, Any]:
    try:
        return prompts.publish(scene_id, version, request.reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# One-click experiments and offline prompt optimization
# ---------------------------------------------------------------------------


@app.post("/api/runs", status_code=202, tags=["runs"])
def start_run(request: RunRequest) -> dict[str, Any]:
    try:
        scene = scenes.get(request.scene_id)
        if scene.status != "enabled":
            raise HTTPException(
                status_code=409,
                detail=scene.unavailable_reason or "Scene is unavailable",
            )
        preparation = None
        if request.preparation_id:
            preparation = preparation_service.get_ready(
                request.preparation_id, request.scene_id
            )
        return run_service.start(
            request.scene_id,
            request.prompt_version,
            request.query,
            preparation,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PreparationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc


@app.get("/api/runs", tags=["runs"])
def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    return jobs.latest("run", min(max(limit, 1), 100))


@app.get("/api/runs/{run_id}", tags=["runs"])
def get_run(run_id: str) -> dict[str, Any]:
    return _get_job(run_id, expected_kind="run")


@app.get("/api/runs/{run_id}/report", tags=["runs"])
def get_run_report(run_id: str) -> dict[str, Any]:
    job = _get_job(run_id, expected_kind="run")
    if not job.get("result"):
        raise HTTPException(status_code=409, detail="Run report is not ready")
    return job["result"]


@app.post("/api/optimization/jobs", status_code=202, tags=["optimization"])
def start_optimization(request: OptimizationRequest) -> dict[str, Any]:
    try:
        scene = scenes.get(request.scene_id)
        if scene.status != "enabled":
            raise HTTPException(
                status_code=409,
                detail=scene.unavailable_reason or "Scene is unavailable",
            )
        return optimization_service.start(
            request.scene_id, request.candidate_count, request.auto_publish
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/optimization/jobs", tags=["optimization"])
def list_optimization_jobs(limit: int = 20) -> list[dict[str, Any]]:
    return jobs.latest("optimization", min(max(limit, 1), 100))


@app.get("/api/optimization/jobs/{job_id}", tags=["optimization"])
def get_optimization_job(job_id: str) -> dict[str, Any]:
    return _get_job(job_id, expected_kind="optimization")


# ---------------------------------------------------------------------------
# Manual session endpoints for integration/debugging without a front end.
# ---------------------------------------------------------------------------


@app.post("/api/sessions", status_code=201, tags=["sessions"])
def create_session(request: SessionRequest) -> dict[str, Any]:
    try:
        scene = scenes.get(request.scene_id)
        if scene.status != "enabled":
            raise HTTPException(
                status_code=409,
                detail=scene.unavailable_reason or "Scene is unavailable",
            )
        session_id = f"session-{uuid.uuid4().hex[:12]}"
        return jobs.create(
            session_id,
            "session",
            {"scene_id": request.scene_id},
            "调试会话已创建，尚未重置仿真",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/sessions/{session_id}", tags=["sessions"])
def get_session(session_id: str) -> dict[str, Any]:
    return _get_job(session_id, expected_kind="session")


@app.post("/api/sessions/{session_id}/reset", tags=["sessions"])
def reset_session(session_id: str) -> dict[str, Any]:
    session = _get_job(session_id, expected_kind="session")
    simulator.begin_run(session_id, session["payload"]["scene_id"])
    try:
        result = simulator.reset()
        jobs.update(
            session_id,
            status="running",
            progress=0.0,
            message="调试会话已重置",
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/sessions/{session_id}/step", tags=["sessions"])
def step_session(session_id: str, action: Action) -> dict[str, Any]:
    _get_job(session_id, expected_kind="session")
    if simulator.status().get("active_run_id") != session_id:
        raise HTTPException(status_code=409, detail="Session is not active; reset it first")
    try:
        result = simulator.step(action.model_dump())
        if result.get("done"):
            jobs.update(
                session_id,
                status="succeeded",
                progress=1.0,
                message="调试会话完成",
                result={"final": result, "records": simulator.snapshot()},
            )
            simulator.finish_run()
        return result
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _get_job(job_id: str, expected_kind: str) -> dict[str, Any]:
    try:
        job = jobs.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if job["kind"] != expected_kind:
        raise HTTPException(status_code=404, detail=f"Unknown {expected_kind}: {job_id}")
    return job

