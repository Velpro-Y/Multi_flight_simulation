"""Run the same scene-three API job locally, without starting a web server."""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from multiflight.main import ground_demo_service, jobs, executor
from multiflight.services.ground_demo import GroundDemoRequest

parser = argparse.ArgumentParser()
parser.add_argument("--angle", type=float, default=None, help="Explicit angle bypasses Dify")
parser.add_argument("--direction", choices=["left", "right", "straight"], default="right")
parser.add_argument("--maneuver", choices=["turn", "uturn"], default="turn")
parser.add_argument("--differential-throttle", type=float, default=0)
parser.add_argument("--thrust-policy", choices=["offset", "inner_idle"], default="offset")
args = parser.parse_args()
job = ground_demo_service.start(GroundDemoRequest(
    direction=args.direction, nose_wheel_deg=args.angle, maneuver=args.maneuver,
    differential_throttle=args.differential_throttle, thrust_policy=args.thrust_policy))
print(job["id"], flush=True)
try:
    for _ in range(180):
        job = jobs.get(job["id"])
        if job["status"] in {"succeeded", "completed_with_failures", "failed"}:
            result = job.get("result")
            if result:
                result["simulation"].pop("trajectory", None)
                result["simulation"].pop("control", None)
            print(json.dumps(job, ensure_ascii=False, indent=2), flush=True)
            sys.exit(0 if job["status"] == "succeeded" else 1)
        time.sleep(2)
    raise TimeoutError("Job did not finish within 360 seconds")
finally:
    executor.shutdown(wait=True)
