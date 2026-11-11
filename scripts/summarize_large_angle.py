"""Combine matched-policy pairs, retaining steering-rate and angle caveats."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data/runs"
first = ROOT / "ground-large-angle-20261110"
repeat = ROOT / "ground-angle75-rate30-20261110"
stage = json.loads((first / "summary.json").read_text(encoding="utf-8"))["cases"]
extra = json.loads((repeat / "summary.json").read_text(encoding="utf-8"))["cases"]
pairs = []
for angle in (20, 40, 60, 75):
    source = extra if angle == 75 else stage
    rows = [r for r in source if r["requested_max_angle_deg"] == angle]
    base = next(r for r in rows if not r["inner_idle"])
    diff = next(r for r in rows if r["inner_idle"])
    pairs.append({"angle_deg": angle, "rate_deg_s": base["steering_rate_limit_deg_s"],
                  "symmetric": base, "inner_zero_throttle": diff,
                  "total_time_reduction_pct": 100*(base["duration_s"]-diff["duration_s"])/base["duration_s"],
                  "lateral_extent_reduction_pct": 100*(base["lateral_extent_m"]-diff["lateral_extent_m"])/base["lateral_extent_m"]})
report = {"pairs": pairs, "initial_75_degree_cases": [r for r in stage if r["requested_max_angle_deg"] == 75],
          "notes": ["75deg uses a separate matched pair at 30deg/s; other pairs use 15deg/s. Cross-angle results therefore do not isolate angle alone.",
                    "Widths are CG-trajectory coordinate ranges, not aircraft swept width or calibrated turn radii.",
                    "Controller targets 5kn but speeds differ and drop below target; this is not a matched-speed pure yaw-moment comparison.",
                    "No Agent calls; inner_idle is zero modeled thrust, not calibrated real-engine idle."]}
path = first / "comparison.json"
path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
for pair in pairs:
    a, b = pair["symmetric"], pair["inner_zero_throttle"]
    print(f"{pair['angle_deg']}deg rate={pair['rate_deg_s']}: time {a['duration_s']:.2f}/{b['duration_s']:.2f}s; "
          f"width {a['lateral_extent_m']:.3f}/{b['lateral_extent_m']:.3f}m; "
          f"width reduction={pair['lateral_extent_reduction_pct']:.2f}%")
