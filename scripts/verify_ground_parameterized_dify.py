"""Submit one parameterized Dify run, or inspect an existing run without new calls."""

import argparse
import hashlib
import json
import time

import httpx

from multiflight.schemas import GroundDirectionParameters
from multiflight.settings import RUN_DIR


def verify(job):
    folder = RUN_DIR / job["id"]
    parameters = GroundDirectionParameters.model_validate(job["payload"]["parameters"]).model_dump()
    report = job.get("result") or {}
    records = json.loads((folder / "records.json").read_text(encoding="utf-8")) if (folder / "records.json").exists() else []
    decisions = json.loads((folder / "decisions.json").read_text(encoding="utf-8")) if (folder / "decisions.json").exists() else []
    steps = [r for r in records if r["kind"] == "step"]
    dify = report.get("dify", {})
    configurations = [json.loads(p.read_text(encoding="utf-8")) for p in folder.glob("realtime-*/configuration.json")]
    prompt_path = folder / "compiled_prompt.md"
    prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
    final = steps[-1]["result"]["state"] if steps else {}
    checks = {
        "run_succeeded": job["status"] == "succeeded",
        "evaluation_passed": report.get("evaluation", {}).get("passed") is True,
        "parameters_consistent": (parameters == report.get("parameters") == report.get("evaluation", {}).get("parameters")
                                  and configurations == [parameters]),
        "initial_speed_applied": bool(steps) and abs(steps[0]["result"]["simulation"]["initial_speed_kn"]-parameters["initial_speed_kn"]) < .001,
        "one_fresh_call_per_step": bool(steps) and len(steps) == len(decisions) == dify.get("model_calls")
                                   and dify.get("reused_decisions") == 0
                                   and all(d["source"] == "live_dify" for d in decisions),
        "prompt_parameters": all(f"- {key}: {value:g}" in prompt for key, value in parameters.items()) and "{{" not in prompt,
        "prompt_hash_matches": hashlib.sha256(prompt.encode()).hexdigest() == report.get("prompt", {}).get("prompt_hash"),
    }
    result = {"run_id": job["id"], "status": job["status"], "parameters": parameters,
              "checks": checks, "passed": all(checks.values()), "error": job.get("error"),
              "dify": dify, "final_state": final, "evaluation": report.get("evaluation")}
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "parameterized_dify_verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", help="Inspect only; do not submit another experiment")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--prompt-version", choices=["0.2.0", "0.3.0"], default="0.2.0")
    parser.add_argument("--initial-speed-kn", type=float, default=5)
    parser.add_argument("--target-nose-wheel-deg", type=float, default=40)
    parser.add_argument("--target-heading-change-deg", type=float, default=150)
    parser.add_argument("--max-simulation-time-s", type=float, default=20)
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=20, trust_env=False) as client:
        rid = args.run_id
        if not rid:
            parameters = GroundDirectionParameters(initial_speed_kn=args.initial_speed_kn,
                target_nose_wheel_deg=args.target_nose_wheel_deg, target_heading_change_deg=args.target_heading_change_deg,
                max_simulation_time_s=args.max_simulation_time_s)
            response = client.post("/api/runs", json={"scene_id": "ground_direction", "prompt_version": args.prompt_version,
                                                       "parameters": parameters.model_dump()})
            response.raise_for_status()
            rid = response.json()["id"]
        print("RUN_ID=" + rid, flush=True)
        deadline = time.monotonic() + 1800
        last = None
        while time.monotonic() < deadline:
            response = client.get(f"/api/runs/{rid}")
            response.raise_for_status()
            job = response.json()
            if job["message"] != last:
                print(job["status"], job["message"], flush=True)
                last = job["message"]
            if job["status"] in {"succeeded", "completed_with_failures", "failed"}:
                result = verify(job)
                print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
                return 0 if result["passed"] else 1
            time.sleep(5)
    raise TimeoutError(f"Run {rid} is still active; inspect it before submitting any new run")


if __name__ == "__main__":
    raise SystemExit(main())
