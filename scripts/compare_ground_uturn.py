"""Compare two saved U-turn runs using the same sampled-trajectory metrics."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--baseline", default="ground-6a4fc8b7fe7f")
parser.add_argument("--candidate", required=True)
args = parser.parse_args()


def metrics(run_id):
    record = json.loads((ROOT / "data/runs" / run_id / "result.json").read_text(encoding="utf-8"))
    sim = record["simulation"]
    tr, controls = sim["trajectory"], sim["control"]
    active = [i for i, phase in enumerate(controls["phase"]) if phase == 1]
    diffs = [controls["throttle_left"][i]-controls["throttle_right"][i] for i in active]
    return {"run_id": run_id, "decision_source": record["decision_source"],
            "passed": sim["passed"], "duration_s": sim["duration_s"],
            "heading_change_deg": sim["heading_change_deg"],
            "sampled_forward_extent_m": max(tr["x_m"])-min(tr["x_m"]),
            "sampled_lateral_extent_m": max(tr["y_m"])-min(tr["y_m"]),
            "max_speed_kn": sim["max_speed_kn"], "final_speed_kn": sim["final_speed_kn"],
            "max_abs_roll_deg": sim["max_abs_roll_deg"],
            "all_wheels_contact": sim["all_wheels_contact"],
            "mean_turn_thrust_left_N": sim.get("mean_turn_thrust1_N"),
            "mean_turn_thrust_right_N": sim.get("mean_turn_thrust2_N"),
            "mean_turn_engine_yaw_moment_Nm": sim.get("mean_turn_engine_yaw_moment_Nm"),
            "mean_turn_left_minus_right_throttle": sum(diffs)/len(diffs)}


base, candidate = metrics(args.baseline), metrics(args.candidate)
comparison = {"baseline": base, "candidate": candidate,
              "note": "Extents use each saved sampled trajectory, not maximum-capability turn radius. Candidate reuses the baseline's +10 degree steering decision with explicit angle input."}
for key in ("duration_s", "sampled_forward_extent_m", "sampled_lateral_extent_m"):
    comparison[key + "_reduction_pct"] = 100*(base[key]-candidate[key])/base[key]
path = ROOT / "data/runs" / args.candidate / "comparison.json"
path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(comparison, ensure_ascii=False, indent=2))
