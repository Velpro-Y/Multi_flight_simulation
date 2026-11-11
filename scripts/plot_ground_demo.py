"""Plot saved scene-three trajectories without rerunning the simulation."""

import csv
import argparse
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--run-id", default="ground-f745f2fbe046")
args = parser.parse_args()
FOLDER = ROOT / "data" / "runs" / args.run_id
record = json.loads((FOLDER / "result.json").read_text(encoding="utf-8"))
simulation = record["simulation"]
data = simulation["trajectory"]
t, x, y, heading = [data[k] for k in ("time_s", "x_m", "y_m", "heading_deg")]
assert len(t) == len(x) == len(y) == len(heading)
assert all(math.isfinite(v) for series in (t, x, y, heading) for v in series)

plt.rcParams.update({"font.family": "Microsoft YaHei", "font.size": 11,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.unicode_minus": False, "svg.fonttype": "path"})
color = "#355C75"
uturn = "control" in simulation
fig, axes = plt.subplots(1, 3 if uturn else 2, figsize=(14 if uturn else 11, 6.5))
trajectory, angle = axes[:2]
fig.subplots_adjust(left=0.09, right=0.96, top=0.77, bottom=0.23, wspace=0.4)
fig.suptitle("场景三 · Agent 掉头仿真实测" if uturn else "场景三 · Agent 左转仿真实测",
             fontsize=20, x=0.08, ha="left", y=0.95)
subtitle = (f"静止起步 → 达到5 kn后转向 → 航向反转  |  Agent指令 +10°  |  实际时长 {t[-1]:.2f} s"
            if uturn else "初始速度 5 kn  |  Agent 指令 −10°  |  仿真时长 8 s  |  关车、释放驻车")
fig.text(0.08, 0.865, subtitle, color="#46515A")

trajectory.plot(y, x, color=color, lw=2.5)
trajectory.scatter([y[0]], [x[0]], marker="o", s=45, color=color, zorder=3)
trajectory.scatter([y[-1]], [x[-1]], marker="s", s=45, color=color, zorder=3)
trajectory.annotate("起点", (y[0], x[0]), xytext=(8, 5), textcoords="offset points")
trajectory.annotate("终点", (y[-1], x[-1]), xytext=(8, -12), textcoords="offset points")
for idx in (len(t)//3, 2*len(t)//3):
    theta = math.radians(heading[idx])
    trajectory.arrow(y[idx], x[idx], 1.2*math.sin(theta), 1.2*math.cos(theta),
                     width=0.035, head_width=0.32, color=color, length_includes_head=True)
trajectory.set(xlabel="横向位置 Ye (m)，负值为左侧", ylabel="初始前进方向 Xe (m)",
               title="地面轨迹（坐标等比例）")
trajectory.set_aspect("equal", adjustable="box")
trajectory.set_xlim(min(y)-1.5, max(y)+2)
trajectory.set_ylim(min(x)-1, max(x)+2)
trajectory.grid(alpha=0.15)

angle.plot(t, heading, color=color, lw=2.5)
angle.scatter([t[-1]], [heading[-1]], color=color, marker="s", s=40, zorder=3)
angle.annotate(f"{heading[-1]:.2f}°", (t[-1], heading[-1]),
               xytext=(-7, 14), textcoords="offset points", ha="right", color=color)
angle.set(xlabel="仿真时间 (s)", ylabel="航向角 (°)，负值为左转",
          title="航向随时间变化", xlim=(0, t[-1]*1.04),
          ylim=(min(heading)-7, max(heading)+7))
angle.grid(alpha=0.15)
if uturn:
    speed_axis = axes[2]
    speed_axis.plot(t, data["speed_kn"], color=color, lw=2.5)
    speed_axis.axhline(5, color="#777777", ls="--", lw=1, label="目标5 kn")
    speed_axis.set(xlabel="仿真时间 (s)", ylabel="速度 (kn)", title="加速与速度保持",
                   xlim=(0, t[-1]*1.04), ylim=(0, 7))
    speed_axis.grid(alpha=0.15)
    speed_axis.legend(frameon=False)
fig.text(0.08, 0.12,
         f"航向变化 {simulation['heading_change_deg']:.2f}°     横向位移 {simulation['final_y_m']:.2f} m"
         f"     最大滚转 {simulation['max_abs_roll_deg']:.2f}°     三轮保持接地", fontsize=12, color=color)
caption = ("真实Agent单次决策，底层控制双发对称推力；177°为Demo结束阈值。未验证75°最大转角及差动推力。"
           if uturn else "保存轨迹的101个采样点直接连线，无平滑处理；箭头表示机体航向。尚未完成180°掉头。")
fig.text(0.08, 0.06, caption,
         fontsize=9, color="#555555")
fig.savefig(FOLDER / "visualization.png", dpi=180, facecolor="white")
fig.savefig(FOLDER / "visualization.svg", facecolor="white")
with (FOLDER / "trajectory.csv").open("w", newline="", encoding="utf-8-sig") as stream:
    writer = csv.writer(stream)
    writer.writerow(["time_s", "x_m", "y_m", "heading_deg"])
    writer.writerows(zip(t, x, y, heading))
(FOLDER / "visualization_manifest.json").write_text(json.dumps({
    "source": str(FOLDER / "result.json"), "script": str(Path(__file__).resolve()),
    "transformations": ["Plot Ye horizontally and Xe vertically with equal spatial scale",
                        "Connect saved samples without smoothing; arrows use saved heading"],
    "samples": len(t), "matplotlib": matplotlib.__version__,
    "png_pixels": list(fig.canvas.get_width_height()), "dpi": 180,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(FOLDER / "visualization.png")
