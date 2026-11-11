"""Reassess existing traces after a measurement-gate correction, without Dify/MATLAB."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from multiflight.db import JobStore
from multiflight.evaluation import RunEvaluator
from multiflight.scene_registry import SceneRegistry

parser = argparse.ArgumentParser()
parser.add_argument("run_id")
args = parser.parse_args()
folder = ROOT / "data/runs" / args.run_id
jobs = JobStore(); job = jobs.get(args.run_id)
result = job["result"]
assert job["payload"]["scene_id"] == "ground_direction"
records = json.loads((folder / "records.json").read_text(encoding="utf-8"))
original = folder / "evaluation.initial.json"
if not original.exists():
    original.write_text(json.dumps(result["evaluation"], ensure_ascii=False, indent=2), encoding="utf-8")
evaluation = RunEvaluator().evaluate(SceneRegistry().get("ground_direction"), records,
                                    result["prompt"]["version"], result["prompt"]["prompt_hash"])
evaluation["reassessment"] = {
    "reason": "Compare checkpoint to next solver sample using time-gap-dependent motion bounds; maximum gap 1ms",
    "original_evaluation": str(original), "resimulated": False, "agent_called_again": False,
}
result["evaluation"] = evaluation
(folder / "evaluation.json").write_text(json.dumps(evaluation, ensure_ascii=False, indent=2), encoding="utf-8")
jobs.update(args.run_id, status="succeeded" if evaluation["passed"] else "completed_with_failures",
            message="真实Agent完整流程已完成；已按求解器采样间隔重新评估连续性", result=result)
print(json.dumps(evaluation, ensure_ascii=False, indent=2))
