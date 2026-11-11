"""Render every saved scene-three experiment; no simulation or Agent calls."""

import csv
import hashlib
import html
import json
import zipfile
from pathlib import Path
from PIL import Image

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "data/runs"
OUT = RUNS / "scene3_visual_summary"
OUT.mkdir(exist_ok=True)
plt.rcParams.update({"font.family": "Microsoft YaHei", "font.size": 10,
                     "axes.unicode_minus": False, "axes.spines.top": False,
                     "axes.spines.right": False, "svg.fonttype": "path"})
BLUE, BROWN, GREY = "#355C75", "#915A3C", "#707070"
COLORS, STYLES = [BLUE, GREY, BROWN], ["-", "--", "-."]
sources, registry, figures = {}, [], []


def read(path):
    path = Path(path)
    sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text(encoding="utf-8"))


def get_run(run_id, label):
    path = RUNS / run_id / "result.json"
    record = read(path)
    sim = record["simulation"]
    register(run_id, label, sim, path)
    return sim


def register(case_id, label, sim, path, status=None):
    tr = sim.get("trajectory", {})
    widths = tr.get("y_m", [])
    registry.append({"case_id": case_id, "label": label,
                     "status": status or ("功能判据通过" if sim.get("passed") else "未通过"),
                     "duration_s": sim.get("duration_s"),
                     "heading_change_deg": sim.get("heading_change_deg"),
                     "lateral_extent_m": sim.get("lateral_extent_m", max(widths)-min(widths) if widths else None),
                     "max_roll_deg": sim.get("max_abs_roll_deg"),
                     "max_wheel_deg": sim.get("max_actual_front_wheel_angle_deg", sim.get("max_command_angle_deg")),
                     "on_ground": sim.get("all_wheels_contact"),
                     "source": str(path.relative_to(ROOT))})
    if tr:
        keys = [k for k, v in tr.items() if isinstance(v, list)]
        assert len({len(tr[k]) for k in keys}) == 1
        assert all(np.isfinite(tr[k]).all() for k in keys)
        with (OUT / (case_id.replace("/", "_") + "_trajectory.csv")).open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream); writer.writerow(keys)
            writer.writerows(zip(*(tr[k] for k in keys)))
    control = sim.get("control")
    if control:
        keys = [k for k, v in control.items() if isinstance(v, list)]
        if keys:
            with (OUT / (case_id.replace("/", "_") + "_control.csv")).open("w", newline="", encoding="utf-8-sig") as stream:
                writer = csv.writer(stream); writer.writerow(keys)
                writer.writerows(zip(*(control[k] for k in keys)))


def canvas(title, note, rows=1, cols=2, size=(12, 6)):
    fig, axes = plt.subplots(rows, cols, figsize=size, squeeze=False)
    fig.subplots_adjust(left=0.08, right=0.97, bottom=0.15, top=0.83, wspace=0.34, hspace=0.52)
    fig.suptitle(title, x=0.06, y=0.965, ha="left", fontsize=19)
    fig.text(0.06, 0.895, note, color="#46515A", fontsize=10)
    for ax in axes.flat:
        ax.grid(alpha=0.14)
    return fig, list(axes.flat)


def finish(fig, name, caption):
    fig.text(0.06, 0.035, caption, fontsize=9, color="#555555")
    fig.savefig(OUT / f"{name}.png", dpi=160, facecolor="white")
    fig.savefig(OUT / f"{name}.svg", facecolor="white")
    figures.append({"name": name, "title": fig._suptitle.get_text(), "caption": caption})
    plt.close(fig)


def trajectory(ax, sims, labels, colors=None, styles=None):
    colors, styles = colors or COLORS, styles or STYLES
    for i, (sim, label) in enumerate(zip(sims, labels)):
        tr = sim["trajectory"]
        ax.plot(tr["y_m"], tr["x_m"], color=colors[i], ls=styles[i], lw=1.9, label=label)
        ax.scatter(tr["y_m"][-1], tr["x_m"][-1], s=22, marker=["s", "^", "D"][i], color=colors[i], zorder=3)
    ax.set(xlabel="横向 Ye (m)", ylabel="初始前进方向 Xe (m)")
    ax.set_aspect("equal", adjustable="box")
    ax.legend(frameon=False, fontsize=9)


def series(ax, sims, labels, key, ylabel, colors=None, styles=None):
    colors, styles = colors or COLORS, styles or STYLES
    for i, (sim, label) in enumerate(zip(sims, labels)):
        tr = sim["trajectory"]
        ax.plot(tr["time_s"], tr[key], color=colors[i], ls=styles[i], lw=1.8, label=label)
    ax.set(xlabel="时间 (s)", ylabel=ylabel)
    ax.legend(frameon=False, fontsize=9)


# 1. One-shot turns, preserving manual vs real-Agent provenance.
right = get_run("ground-6793cceb9d23", "10°右转：手动输入")
left = get_run("ground-f745f2fbe046", "−10°左转：真实Agent")
fig, ax = canvas("01 低速左右转向", "初始速度5 kn、关车、释放驻车，运行8秒；右转为手动角度，左转由真实Agent输出。")
trajectory(ax[0], [right, left], ["+10°右转", "−10°左转"], [BLUE, BROWN], ["-", "--"])
ax[0].set_title("地面轨迹 · 等比例")
series(ax[1], [right, left], ["+10°右转", "−10°左转"], "heading_deg", "航向角 (°)", [BLUE, BROWN], ["-", "--"])
ax[1].set_title("航向响应")
finish(fig, "01_low_speed_turns", "保存采样点直接连线，无平滑；两次试验均保持三轮接地。此处不是完整掉头。")

# 2. Static wheel range and independent-throttle controls.
cap = RUNS / "ground-capability-20261110"
cap_summary = read(cap / "summary.json")
cap_cases = {}
for summary in cap_summary["cases"]:
    name = summary["case_id"]; path = cap / f"{name}.json"; record = read(path)
    sim = {**summary, "trajectory": record["trajectory"]}
    if "control" in record: sim["control"] = record["control"]
    register("capability_" + name, name, sim, path)
    cap_cases[name] = sim
fig, ax = canvas("02 静态75°与差动油门链路", "静态关车验证轮角范围；动态三组均从静止加速到5 kn，3.85秒后施加固定油门并保持8秒。", 2, 2, (12, 8.8))
static = cap_cases["static_75"]
for i, label in enumerate(["前轮", "左主轮", "右主轮"]):
    lo, hi = static[f"wheel{i+1}_min_deg"], static[f"wheel{i+1}_max_deg"]
    ax[0].plot([lo, hi], [i, i], lw=4, color=BLUE)
    ax[0].scatter([lo, hi], [i, i], color=BLUE, marker="s", s=30)
    ax[0].text(hi+3, i, f"{lo:g}° ～ {hi:g}°", va="center", fontsize=9)
ax[0].set(yticks=[0, 1, 2], yticklabels=["前轮", "左主轮", "右主轮"], xlim=(-85, 125), ylim=(-0.6, 2.6), xlabel="实际轮角范围 (°)", title="静态实际角度范围 · 不是时序曲线")
dynamic = [cap_cases[k] for k in ("symmetric", "reduce_left", "reduce_right")]
labels = ["对称油门", "降低左油门", "降低右油门"]
positions = np.arange(3)
for offset, key, label, color, hatch in [(-0.18, "mean_thrust1_N", "左发", BLUE, ""), (0.18, "mean_thrust2_N", "右发", BROWN, "//")]:
    ax[1].bar(positions+offset, [s[key] for s in dynamic], 0.34, label=label, color=color, hatch=hatch)
ax[1].set(xticks=positions, xticklabels=labels, ylabel="阶段平均推力 (N)", title="实测发动机推力")
ax[1].legend(frameon=False)
series(ax[2], dynamic, labels, "heading_deg", "航向角 (°)")
series(ax[3], dynamic, labels, "y_m", "横向位置 Ye (m)")
for a in ax[2:]: a.axvline(3.85, color=GREY, ls=":", lw=1)
ax[2].set_title("前轮保持0°时的偏航响应")
ax[3].set_title("横向响应 · 虚线为油门切换时刻")
finish(fig, "02_wheel_and_differential", "动态方向响应约±0.47°；通过推力和方向链路判据，不代表大幅度转向效能。静态轮角仅绘制实测范围。")

# 3. Small-angle U-turn policies.
small = [get_run(k, label) for k, label in zip(
    ["ground-6a4fc8b7fe7f", "ground-e58377183157", "ground-0a96dc99392c"],
    ["10°掉头：对称油门", "10°掉头：固定差0.1", "10°掉头：内侧零油门"])]
labels = ["对称油门", "固定差0.1", "内侧零油门"]
fig, ax = canvas("03 10°掉头 · 三种推力策略", "均为从静止起步、5 kn速度目标、1°/s转向限制；后两组复用基准角度，不另调Agent。", 2, 2, (12, 8.8))
trajectory(ax[0], small, labels); ax[0].set_title("重心轨迹 · 等比例")
series(ax[1], small, labels, "heading_deg", "航向角 (°)"); ax[1].set_title("航向变化")
series(ax[2], small, labels, "speed_kn", "速度 (kn)"); ax[2].axhline(5, color=GREY, ls=":"); ax[2].set_title("速度目标5 kn，并非全程恒速")
for i, sim in enumerate(small):
    c = sim["control"]
    ax[3].plot(c["time_s"], np.array(c["throttle_left"])-np.array(c["throttle_right"]), color=COLORS[i], ls=STYLES[i], label=labels[i])
ax[3].set(xlabel="时间 (s)", ylabel="左油门 − 右油门", title="实际施加的油门差")
ax[3].legend(frameon=False, fontsize=9)
finish(fig, "03_small_angle_uturn", "177°为Demo结束阈值；内侧零油门对应模型零推力，不等同真实发动机慢车。各策略均保持三轮接地。")

# 4. Large-angle matched pairs, preserving the failed original 75-degree cases.
stage = RUNS / "ground-large-angle-20261110"
repeat = RUNS / "ground-angle75-rate30-20261110"
stage_summary, repeat_summary = read(stage / "summary.json"), read(repeat / "summary.json")
large = {}
for folder, summary in [(stage, stage_summary), (repeat, repeat_summary)]:
    for row in summary["cases"]:
        path = folder / row["case_id"] / "simulation.json"; sim = read(path)
        status = "功能判据通过" if row["angle_case_passed"] else "未达到75°目标"
        register(folder.name + "_" + row["case_id"], row["case_id"], sim, path, status)
        if folder == repeat or row["requested_max_angle_deg"] != 75:
            large[(row["requested_max_angle_deg"], row["inner_idle"])] = sim
fig, ax = canvas("04 大角度掉头 · 配对比较", "20°/40°/60°采用15°/s；75°来自30°/s补测。只在同一角度、相同速率下比较推力策略。", 2, 3, (15, 8.8))
angles = [20, 40, 60, 75]; xpos = np.arange(4)
for offset, policy, color, label, hatch in [(-0.18, False, BLUE, "对称油门", ""), (0.18, True, BROWN, "内侧零油门", "//")]:
    for panel, key in [(0, "duration_s"), (1, "lateral_extent_m")]:
        vals = [large[(angle, policy)][key] for angle in angles]
        ax[panel].bar(xpos+offset, vals, 0.34, color=color, hatch=hatch, label=label)
        for pos, val in zip(xpos+offset, vals): ax[panel].text(pos, val+0.13, f"{val:.2f}", ha="center", fontsize=8)
for a in ax[:2]:
    a.set(xticks=xpos, xticklabels=["20°", "40°", "60°", "75°*"], xlabel="目标前轮角")
    a.legend(frameon=False, fontsize=9)
ax[0].set(ylabel="总耗时 (s)", title="掉头总时间 · 包含加速")
ax[1].set(ylabel="Ye最大值 − 最小值 (m)", title="重心轨迹横向占用")
for a, angle in zip(ax[2:], angles):
    trajectory(a, [large[(angle, False)], large[(angle, True)]], ["对称", "内侧零油门"], [BLUE, BROWN], ["-", "--"])
    a.set_title(f"{angle}°轨迹 · {30 if angle == 75 else 15}°/s")
finish(fig, "04_large_angle_comparison", "*75°使用独立补测；轨迹范围不是飞机扫掠宽度。不同角度的坐标范围不同，但每幅轨迹均采用空间等比例。")

# 5. Detailed actual-75-degree run traces.
seventyfive = [large[(75, False)], large[(75, True)]]
labels = ["对称油门", "内侧零油门"]
fig, ax = canvas("05 实际75°掉头 · 完整对照", "两组转向限制均为30°/s，实际前轮均达到75°；全程保持三轮接地，按177°Demo阈值结束。", 2, 3, (15, 8.8))
trajectory(ax[0], seventyfive, labels, [BLUE, BROWN], ["-", "--"]); ax[0].set_title("轨迹 · 等比例")
series(ax[1], seventyfive, labels, "heading_deg", "航向角 (°)", [BLUE, BROWN], ["-", "--"]); ax[1].set_title("航向变化")
series(ax[2], seventyfive, labels, "speed_kn", "速度 (kn)", [BLUE, BROWN], ["-", "--"]); ax[2].axhline(5, color=GREY, ls=":"); ax[2].set_title("速度 · 均未全程保持5 kn")
for i, sim in enumerate(seventyfive):
    c = sim["control"]
    ax[3].plot(c["time_s"], c["nose_wheel_deg"], color=[BLUE, BROWN][i], ls=["-", "--"][i], label=labels[i])
    for side, ls in [("left", "-"), ("right", "--")]:
        ax[4].plot(c["time_s"], c["throttle_"+side], color=[BLUE, BROWN][i], ls=ls,
                   label=labels[i]+("左发" if side == "left" else "右发"), alpha=0.85)
ax[3].set(xlabel="时间 (s)", ylabel="转向指令 (°)", title="转向指令 · 实测峰值均75°"); ax[3].legend(frameon=False, fontsize=9)
ax[4].set(xlabel="时间 (s)", ylabel="油门指令 (0–1)", title="左右油门时序"); ax[4].legend(frameon=False, fontsize=8)
for offset, key, label, color, hatch in [(-0.18, "mean_turn_thrust1_N", "左发", BLUE, ""), (0.18, "mean_turn_thrust2_N", "右发", BROWN, "//")]:
    ax[5].bar(np.arange(2)+offset, [s[key] for s in seventyfive], 0.34, color=color, hatch=hatch, label=label)
ax[5].set(xticks=[0, 1], xticklabels=labels, ylabel="转弯阶段平均推力 (N)", title="实际推力"); ax[5].legend(frameon=False)
finish(fig, "05_actual_75_detail", "差动组轨迹横向占用约少20.2%；两组速度不同，不能把变化全部归因于差动力矩。结束时角度回中不代表已验证稳定直线保持。")

# 6. Preserve unsuccessful attempts instead of silently omitting them.
failed = get_run("ground-3b588b77bf18", "起步失败：速度未达到5 kn")
fig, ax = canvas("06 未覆盖目标的记录", "保留初始失败和未覆盖工况，避免把“完成转弯”与“通过指定试验点”混为一谈。", 1, 3, (14, 5.7))
series(ax[0], [failed], ["初始比例速度控制"], "speed_kn", "速度 (kn)")
ax[0].axhline(5, color=BROWN, ls="--", label="进入转弯门槛5 kn"); ax[0].set_title("初始掉头：最高仅4.46 kn"); ax[0].legend(frameon=False, fontsize=8)
original75 = [s for s in stage_summary["cases"] if s["requested_max_angle_deg"] == 75]
ax[1].bar([0, 1], [s["max_command_angle_deg"] for s in original75], color=[BLUE, BROWN])
ax[1].axhline(75, color=GREY, ls="--")
ax[1].set(xticks=[0, 1], xticklabels=["对称", "内侧零油门"], ylabel="达到的最大指令角 (°)", ylim=(0, 85), title="首轮75°：未实际达到目标")
for i, s in enumerate(original75): ax[1].text(i, s["max_command_angle_deg"]+2, f"{s['max_command_angle_deg']:.2f}°", ha="center")
ax[2].axis("off")
ax[2].text(0, 0.92, "另一次初始化失败", fontsize=13, transform=ax[2].transAxes)
ax[2].text(0, 0.75, "ground-c076c41cc8e8\n\n临时接线端口已被占用，\n未产生有效飞机仿真轨迹。\n\n后续已修复接线并完成复测。\n此项只登记，不绘制虚构数据。", fontsize=10, va="top", transform=ax[2].transAxes, linespacing=1.6)
registry.append({"case_id": "ground-c076c41cc8e8", "label": "初始化接线失败", "status": "无有效轨迹", "source": "data/runs/ground-c076c41cc8e8/matlab.log"})
finish(fig, "06_incomplete_attempts", "首轮75°未覆盖结果保留；30°/s补测的实际75°结果见图05。基础5 kn起步随后通过PI控制修正。")

# Export complete inventory, hashes, source data and an offline gallery.
columns = list(dict.fromkeys(k for row in registry for k in row))
with (OUT / "all_experiments.csv").open("w", newline="", encoding="utf-8-sig") as stream:
    writer = csv.DictWriter(stream, fieldnames=columns); writer.writeheader(); writer.writerows(registry)
(OUT / "all_experiments.json").write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
manifest = {"script": str(Path(__file__).resolve()), "matplotlib": matplotlib.__version__,
            "source_sha256": sources, "scope": "All saved scene-three experiments from this development sequence; not historical scene-one runs",
            "transformations": ["Direct lines between saved samples, no smoothing or resimulation", "Ye horizontal and Xe vertical with equal spatial scale for trajectories", "No replicate averaging or error bars; one deterministic run per condition", "Static wheel angles shown as recorded min/max ranges, not invented time series"],
            "figures": figures, "experiment_count": len(registry)}
(OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
table = "".join("<tr>"+"".join("<td>"+html.escape(str(row.get(k, "")))+"</td>" for k in ["label", "status", "duration_s", "heading_change_deg", "source"])+"</tr>" for row in registry)
gallery = "".join(f'<section><h2>{html.escape(f["title"])}</h2><img src="{f["name"]}.png" alt="{html.escape(f["caption"])}"><p>{html.escape(f["caption"])}</p><a href="{f["name"]}.svg">下载SVG</a></section>' for f in figures)
page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>场景三实验结果汇总</title>
<style>body{{font-family:"Microsoft YaHei",sans-serif;color:#263746;max-width:1450px;margin:36px auto;padding:0 24px;background:#fafafa}}h1{{font-size:30px}}h2{{font-size:21px}}section{{margin:38px 0}}img{{width:100%;background:white}}p{{line-height:1.8}}table{{border-collapse:collapse;width:100%;font-size:12px}}td,th{{border:1px solid #ddd;padding:9px;word-break:break-all}}a{{color:#355c75}}</style>
<h1>场景三实验结果汇总</h1><p>共登记{len(registry)}次试验或初始化尝试。以下图表只读取已有记录，没有重跑仿真。试验范围为本轮场景三开发，不包含历史场景一。</p>
<p>所有“通过”均指各自功能或Demo判据，不代表原始试验点完整验收。75°补测速率不同，内侧零推力未作真实慢车标定，速度未恒定保持5 kn。</p>
<p><a href="all_experiments.csv">全部指标CSV</a> · <a href="manifest.json">来源与处理说明</a></p>{gallery}
<h2>全部实验索引</h2><table><tr><th>实验</th><th>状态</th><th>时长s</th><th>航向变化°</th><th>源文件</th></tr>{table}</table></html>'''
(OUT / "index.html").write_text(page, encoding="utf-8")
manifest["image_metadata"] = {}
for item in figures:
    with Image.open(OUT / (item["name"] + ".png")) as im:
        manifest["image_metadata"][item["name"]] = {"pixels": list(im.size), "dpi": im.info.get("dpi"), "mode": im.mode}
for row in registry:
    source = ROOT / row["source"]
    if source.is_file():
        manifest["source_sha256"][row["source"]] = hashlib.sha256(source.read_bytes()).hexdigest()
(OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
with zipfile.ZipFile(OUT.with_suffix(".zip"), "w", zipfile.ZIP_DEFLATED) as archive:
    for path in OUT.iterdir():
        if path.is_file(): archive.write(path, path.relative_to(OUT.parent))
print(f"Saved {len(figures)} figures and {len(registry)} experiment records to {OUT}")
