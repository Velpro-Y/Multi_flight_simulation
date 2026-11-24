"""Submit one parameterized Dify run, or inspect an existing run without new calls."""

import argparse
import hashlib
import json
import time

import httpx

from multiflight.schemas import GroundDirectionParameters
from multiflight.settings import RUN_DIR


BRAKE_COVERAGE_QUERY = (
    "本轮验证参数化刹车闭环：在完成目标转向前，若manual_brake_used=false，"
    "依据实时状态选择一次适度的非零右主轮手动刹车，左手动刹车为0，读取实际输出确认；"
    "若auto_brake_used=false，切换自动模式并预位，左右手动指令均为0，"
    "读取auto_brake_active和左右实际0.15确认。两项累计标记均true后释放刹车并恢复手动模式，"
    "继续完成本轮参数指定的右转目标。时机、油门、前轮角和手动刹车大小由你根据每步状态选择，"
    "防止刹停。每轮只返回一个七字段动作JSON。"
)


def brake_coverage(steps):
    events = []
    for index, r in enumerate(steps, 1):
        action = r["raw_action"]
        sim = r["result"].get("simulation", {})
        left, right = sim.get("brake_left", 0), sim.get("brake_right", 0)
        mode = sim.get("brake_system_mode")
        manual = (mode == action.get("brake_system_mode") == 0 and right > 0 and left == 0
                  and abs(right-action.get("brake_right", 0)) < 1e-6)
        auto = (mode == action.get("brake_system_mode") == 1 and sim.get("auto_brake_active")
                and action.get("auto_brake_armed") and action.get("brake_left", 0) == action.get("brake_right", 0) == 0
                and abs(left-.15) < 1e-6 and abs(right-.15) < 1e-6 and sim.get("on_ground"))
        if manual or auto:
            events.append({"step": index, "kind": "manual_right" if manual else "automatic",
                           "start_time_s": sim["start_time_s"], "end_time_s": sim["time_s"],
                           "brake_left": left, "brake_right": right,
                           "speed_before_kn": r["state_before"]["speed_kn"], "speed_after_kn": sim["speed_kn"]})
    return {"manual_right_exercised": any(e["kind"] == "manual_right" for e in events),
            "automatic_exercised": any(e["kind"] == "automatic" for e in events), "events": events}


def verify(job, require_braking=False):
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
    coverage = brake_coverage(steps) if require_braking else None
    if coverage is not None:
        checks["manual_right_brake_exercised"] = coverage["manual_right_exercised"]
        checks["automatic_brake_exercised"] = coverage["automatic_exercised"]
    result = {"run_id": job["id"], "status": job["status"], "parameters": parameters,
              "checks": checks, "passed": all(checks.values()), "error": job.get("error"),
              "dify": dify, "final_state": final, "evaluation": report.get("evaluation")}
    if coverage is not None:
        result["brake_coverage"] = coverage
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
    parser.add_argument("--require-braking", action="store_true", help="Request and verify actual manual/automatic brake coverage (0.3 protocol)")
    args = parser.parse_args()
    if args.require_braking and not args.run_id and args.prompt_version != "0.3.0":
        parser.error("--require-braking requires --prompt-version 0.3.0")
    with httpx.Client(base_url=args.base_url, timeout=20, trust_env=False) as client:
        rid = args.run_id
        if not rid:
            parameters = GroundDirectionParameters(initial_speed_kn=args.initial_speed_kn,
                target_nose_wheel_deg=args.target_nose_wheel_deg, target_heading_change_deg=args.target_heading_change_deg,
                max_simulation_time_s=args.max_simulation_time_s)
            payload = {"scene_id": "ground_direction", "prompt_version": args.prompt_version,
                       "parameters": parameters.model_dump()}
            if args.require_braking:
                payload["query"] = BRAKE_COVERAGE_QUERY
            response = client.post("/api/runs", json=payload)
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
                result = verify(job, require_braking=args.require_braking)
                print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
                return 0 if result["passed"] else 1
            time.sleep(5)
    raise TimeoutError(f"Run {rid} is still active; inspect it before submitting any new run")


if __name__ == "__main__":
    raise SystemExit(main())
