"""Plot a saved per-step Dify closed-loop run, without model/simulation calls."""

import argparse
import csv
import hashlib
import html
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--run-id", default="run-54b2b6bae411")
parser.add_argument("--simple", action="store_true", help="Concise result figure for an all-live run")
args = parser.parse_args()
folder = ROOT / "data/runs" / args.run_id
sources = {}


def read(path):
    sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text(encoding="utf-8"))


decisions = read(folder / "decisions.json")
records = read(folder / "records.json")
evaluation = read(folder / "evaluation.json")
steps = [r for r in records if r["kind"] == "step"]
assert len(steps) == len(decisions)
traces = [read(Path(r["result"]["simulation_file"])) for r in steps]
# Keep each segment separate: no invented interpolation across restore gaps.
decision_t = np.array([d["state"]["time"] for d in decisions])
end_t = np.array([r["result"]["state"]["time"] for r in steps])
final = steps[-1]["result"]["state"]
max_roll = max(s["max_abs_roll_deg"] for s in traces)
min_speed = min(min(s["trajectory"]["speed_kn"]) for s in traces)
ground = all(s["on_ground"] for s in traces)
live = np.array([d["source"] == "live_dify" for d in decisions])
if args.simple:
    assert live.all(), "Simple all-live view requires every decision to be a fresh Dify call"
actions = {k: np.array([d["action"][k] for d in decisions])
           for k in ["nose_wheel_deg", "throttle_left", "throttle_right"]}

plt.rcParams.update({"font.family": "Microsoft YaHei", "font.size": 10,
                     "axes.unicode_minus": False, "axes.spines.top": False,
                     "axes.spines.right": False, "svg.fonttype": "path"})
BLUE, BROWN, GREY = "#355C75", "#915A3C", "#737373"
fig, matrix = plt.subplots(2, 3, figsize=(15, 9))
axes = list(matrix.flat)
fig.subplots_adjust(left=.075, right=.97, top=.83 if args.simple else .80,
                    bottom=.15 if args.simple else .18, wspace=.38, hspace=.58)
fig.suptitle("场景三 · Dify闭环掉头仿真" if args.simple else "场景三 · Dify逐步闭环决策实测", x=.06, y=.965, ha="left", fontsize=22)
subtitle = (f"提示词 v{evaluation['prompt_version']}   ·   {len(steps)}次决策   ·   仿真步长0.5 s" if args.simple else
            f"提示词v{evaluation['prompt_version']}  |  {len(steps)}步决策  |  每步0.5秒仿真时间  |  左右油门与前轮角由Dify决定，无PI代驾")
fig.text(.06, .895, subtitle, fontsize=11, color="#46515A")
if not args.simple:
    fig.text(.06, .85, f"○ 前{sum(~live)}步：状态匹配后复用已有真实Dify决策     ■ 后{sum(live)}步：新请求Dify     仿真等待模型响应，非墙钟硬实时", fontsize=10, color=GREY)

for ax in axes:
    ax.grid(alpha=.14)

for i, s in enumerate(traces):
    tr = s["trajectory"]
    assert all(np.isfinite(tr[k]).all() for k in ("time_s", "x_m", "y_m", "heading_deg", "speed_kn"))
    axes[0].plot(tr["y_m"], tr["x_m"], color=BLUE, lw=2)
    axes[1].plot(tr["time_s"], tr["heading_deg"], color=BLUE, lw=2)
    axes[2].plot(tr["time_s"], tr["speed_kn"], color=BLUE, lw=2)

marker_groups = [(live, "o", "决策时刻")] if args.simple else [(~live, "o", "复用真实决策"), (live, "s", "新请求决策")]
for mask, marker, label in marker_groups:
    states = [d["state"] for d, yes in zip(decisions, mask) if yes]
    times = decision_t[mask]
    axes[0].scatter([s["y_m"] for s in states], [s["x_m"] for s in states],
                    marker=marker, s=27, facecolors="white" if marker == "o" else BLUE,
                    edgecolors=BLUE, label=label, zorder=4)
    for panel, key in [(1, "heading_deg"), (2, "speed_kn")]:
        axes[panel].scatter(times, [s[key] for s in states], marker=marker, s=23,
                            facecolors="white" if marker == "o" else BLUE, edgecolors=BLUE, zorder=4)
axes[0].scatter([final["y_m"]], [final["x_m"]], marker="*", s=95, color=BROWN, label="终点", zorder=5)
axes[0].annotate("起点", (0, 0), xytext=(6, 3), textcoords="offset points")
axes[0].set(title="地面轨迹" if args.simple else "地面轨迹与决策位置 · 等比例", xlabel="横向位置 Ye (m)", ylabel="初始前进方向 Xe (m)")
axes[0].set_aspect("equal", adjustable="box")
axes[0].legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(1.03, 1))
axes[1].axhline(177, color=GREY, ls=":", lw=1)
axes[1].set(title="航向" if args.simple else "航向变化 · 点为决策时刻", ylabel="航向角 (°)")
axes[2].axhline(5, color=BROWN, ls=":", lw=1, label="目标5 kn")
axes[2].set(title="速度" if args.simple else "速度反馈 · 恒速目标未达标", ylabel="速度 (kn)", ylim=(0, max(6, max(s['max_speed_kn'] for s in traces)*1.1)))
axes[2].legend(frameon=False, fontsize=9)

hold_t = np.r_[decision_t, final["time"]]
axes[3].step(hold_t, np.r_[actions["nose_wheel_deg"], actions["nose_wheel_deg"][-1]],
             where="post", color=BROWN, ls="--", label="目标角")
actual_t = np.r_[0, end_t]
actual_wheel = np.r_[0, [r["result"]["state"]["wheel_deg"] for r in steps]]
axes[3].plot(actual_t, actual_wheel, color=BLUE, marker=".", lw=1.7, label="实际角")
axes[3].set(title="前轮转角" if args.simple else "前轮目标与实际响应", ylabel="前轮角 (°)", ylim=(-3, 85))
axes[3].legend(frameon=False, fontsize=9)
for key, label, color, style in [("throttle_left", "左油门", BLUE, "-"), ("throttle_right", "右油门", BROWN, "--")]:
    axes[4].step(hold_t, np.r_[actions[key], actions[key][-1]], where="post", color=color, ls=style, lw=1.8, label=label)
axes[4].set(title="左右油门" if args.simple else "Dify每步下达的左右油门", ylabel="油门指令 (0–1)", ylim=(-.02, .44))
axes[4].legend(frameon=False, fontsize=9)
axes[5].plot(end_t, [r["result"]["state"]["roll_deg"] for r in steps], marker="o", ms=3, color=BLUE, label="步末滚转")
axes[5].plot(end_t, [s["max_abs_roll_deg"] for s in traces], marker="^", ms=4, ls="--", color=BROWN, label="每步最大绝对滚转")
axes[5].set(title="滚转角" if args.simple else "姿态检查 · 全程三轮接地" if ground else "姿态检查 · 存在接地异常", ylabel="滚转角 (°)")
axes[5].legend(frameon=False, fontsize=8)
for i, ax in enumerate(axes):
    if i:
        ax.set_xlabel("仿真时间 (s)")
        ax.set_xlim(0, final["time"]+.1)
        for t in decision_t:
            ax.axvline(t, color=GREY, alpha=.08, lw=.7, zorder=0)

max_wheel = max(s["max_wheel_deg"] for s in traces)
fig.text(.06, .065 if args.simple else .105, f"仿真时长 {final['time']:.2f} s     航向 {final['heading_deg']:.2f}°     最大前轮角 {max_wheel:.0f}°     末速度 {final['speed_kn']:.2f} kn     最大滚转 {max_roll:.2f}°", fontsize=12, color=BLUE)
if not args.simple:
    fig.text(.06, .045, "轨迹为保存样本分段连线，无平滑；油门为零阶保持指令。掉头功能判据通过，不代表恒速、稳定对正或原始试验点全部验收。", fontsize=9, color=GREY)
png, svg = folder/"realtime_visualization.png", folder/"realtime_visualization.svg"
fig.savefig(png, dpi=170, facecolor="white")
fig.savefig(svg, facecolor="white")
plt.close(fig)

# Accessible tabular alternative for all displayed time series.
with (folder/"realtime_trajectory.csv").open("w", newline="", encoding="utf-8-sig") as stream:
    writer = csv.writer(stream); writer.writerow(["step", "time_s", "x_m", "y_m", "heading_deg", "speed_kn"])
    for i, s in enumerate(traces):
        tr = s["trajectory"]
        writer.writerows((i+1, *row) for row in zip(*(tr[k] for k in ["time_s", "x_m", "y_m", "heading_deg", "speed_kn"])))
with Image.open(png) as im:
    metadata = {"pixels": list(im.size), "dpi": im.info.get("dpi"), "mode": im.mode}
(folder/"realtime_visualization_manifest.json").write_text(json.dumps({
    "script": str(Path(__file__).resolve()), "source_sha256": sources,
    "transformations": ["Plot native saved trajectory segments separately without smoothing",
                        "Plot raw LLM actions with zero-order hold; actual wheel angles and rolls are step-end samples",
                        "Mark reused vs freshly requested Dify decisions; preserve original failed attempt elsewhere"],
    "matplotlib": matplotlib.__version__, "image_metadata": metadata,
    "min_saved_speed_kn_including_start": min_speed,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(png)
