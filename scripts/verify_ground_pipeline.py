"""One real HTTP/Dify/MATLAB end-to-end run; starts local API if absent."""

import json
import os
import subprocess
import sys
import time
import argparse
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"
parser = argparse.ArgumentParser()
parser.add_argument("--version", default=None)
args = parser.parse_args()
with httpx.Client(timeout=20) as client:
    try:
        available = client.get(BASE + "/health").is_success
    except httpx.HTTPError:
        available = False
    if not available:
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONIOENCODING="utf-8")
        log = (ROOT / "data/server-ground-pipeline.log").open("w", encoding="utf-8")
        subprocess.Popen([sys.executable, "-m", "uvicorn", "multiflight.main:app", "--host", "0.0.0.0", "--port", "8000"],
                         cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        log.close()
        for _ in range(30):
            try:
                if client.get(BASE + "/health").is_success: break
            except httpx.HTTPError: pass
            time.sleep(1)
    scenes = client.get(BASE + "/api/scenarios").json()
    scene = next(s for s in scenes if s["scene_id"] == "ground_direction")
    if scene["status"] != "enabled":
        raise RuntimeError("Existing API is stale; restart scripts/start.ps1 before this verification")
    versions = client.get(BASE + "/api/prompts/ground_direction/versions")
    versions.raise_for_status()
    print("published_prompt=" + versions.json()["published"], flush=True)
    response = client.post(BASE + "/api/runs", json={"scene_id": "ground_direction", "prompt_version": args.version})
    response.raise_for_status(); run_id = response.json()["id"]
    print(run_id, flush=True)
    for _ in range(240):
        response = client.get(BASE + "/api/runs/" + run_id); response.raise_for_status()
        job = response.json()
        if job["status"] in {"succeeded", "completed_with_failures", "failed"}:
            result = job.get("result") or {}
            print(json.dumps({"id": job["id"], "status": job["status"], "error": job.get("error"),
                              "prompt": result.get("prompt"), "evaluation": result.get("evaluation"),
                              "artifacts": result.get("artifacts")}, ensure_ascii=False, indent=2), flush=True)
            sys.exit(0 if job["status"] == "succeeded" else 1)
        time.sleep(2)
    raise TimeoutError("End-to-end job exceeded 480s")
