"""Visualize saved scene-one experiments in a fixed local-time interval; no simulations."""

import argparse
import csv
import hashlib
import html
import json
import math
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TZ = timezone(timedelta(hours=8))
parser = argparse.ArgumentParser()
parser.add_argument("--end", default="2026-11-11T12:05:30+08:00")
parser.add_argument("--hours", type=float, default=3)
args = parser.parse_args()
end = datetime.fromisoformat(args.end)
start = end - timedelta(hours=args.hours)
out = ROOT / "data/runs" / ("scene1_recent_" + end.strftime("%Y%m%d_%H%M%S"))
out.mkdir(exist_ok=True)
sources = {}


def load(path):
    sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text(encoding="utf-8"))


def savejson(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


con = sqlite3.connect((ROOT / "data/multiflight.db").as_uri() + "?mode=ro", uri=True)
con.row_factory = sqlite3.Row
jobs = []
for row in con.execute("SELECT * FROM jobs WHERE kind='run' ORDER BY created_at"):
    when = datetime.fromisoformat(row["created_at"])
    payload = json.loads(row["payload_json"] or "{}")
    if not start <= when <= end or payload.get("scene_id") != "engine_failure":
        continue
    result = json.loads(row["result_json"] or "{}")
    jobs.append({"id": row["id"], "created_at": row["created_at"],
                 "status": row["status"], "payload": payload, "error": row["error"],
                 "trim": result.get("trim"), "evaluation": result.get("evaluation")})
con.close()
savejson(out / "selected_jobs.json", jobs)
sources["selected_jobs.json"] = hashlib.sha256((out / "selected_jobs.json").read_bytes()).hexdigest()

experiments, flat = [], []
for i, job in enumerate(jobs, 1):
    folder = ROOT / "data/runs" / job["id"]
    records = load(folder / "records.json") if (folder / "records.json").exists() else []
    ev = load(folder / "evaluation.json") if (folder / "evaluation.json").exists() else (job["evaluation"] or {})
    states = [r["result"]["state"] for r in records if "state" in r.get("result", {})]
    steps = [r for r in records if r.get("kind") == "step"]
    p = job["payload"].get("parameters", {})
    first_negative = next((s["time"] for s in states if s["altitude"] < 0), None)
    reached = bool(ev.get("hard_gates", {}).get("completed"))
    if not steps:
        outcome = "未执行仿真" if job["status"] == "failed" else "未产生仿真步"
    elif first_negative is not None:
        outcome = "高度跌破零"
    elif reached:
        outcome = "完成复飞"
    else:
        outcome = "提前结束"
    e = {**job, "label": f"R{i:02d}", "local_time": datetime.fromisoformat(job["created_at"]).astimezone(TZ).strftime("%H:%M:%S"),
         "records": records, "states": states, "steps": steps, "parameters": p, "evaluation": ev,
         "outcome": outcome, "reached": reached, "first_negative_s": first_negative}
    experiments.append(e)
    for record in records:
        s = record.get("result", {}).get("state")
        if not s:
            continue
        item = {"label": e["label"], "run_id": e["id"], **s}
        for kind in ["raw_action", "applied_action"]:
            item.update({kind + "_" + k: v for k, v in record.get(kind, {}).items()})
        flat.append(item)


def writecsv(name, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with (out / name).open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, keys)
        w.writeheader()
        w.writerows(rows)


summary = []
for e in experiments:
    states, p, ev = e["states"], e["parameters"], e["evaluation"]
    summary.append({"label": e["label"], "run_id": e["id"], "start_local": e["local_time"],
                    **p, "steps": len(e["steps"]), "final_time_s": states[-1]["time"] if states else None,
                    "final_altitude_ft": states[-1]["altitude"] if states else None,
                    "min_altitude_ft": min(s["altitude"] for s in states) if states else None,
                    "max_abs_roll_deg": max(abs(math.degrees(s["roll"])) for s in states) if states else None,
                    "first_negative_s": e["first_negative_s"], "outcome": e["outcome"],
                    "evaluation_passed": ev.get("passed", False),
                    "failure_labels": ", ".join(ev.get("failure_labels", [])), "error": e["error"] or "",
                    "prompt_hash": ev.get("prompt_hash", "")})
writecsv("experiments.csv", summary)
writecsv("trajectories_and_actions.csv", flat)

plt.rcParams.update({"font.family": "Microsoft YaHei", "font.size": 11,
                     "axes.unicode_minus": False, "axes.spines.top": False,
                     "axes.spines.right": False, "svg.fonttype": "path",
                     "axes.labelcolor": "#333B43", "text.color": "#27343E"})
BLUE, BROWN, GREY = "#355C75", "#915A3C", "#63717C"
images = []


def base(title, subtitle, rows=2, cols=2, height=9):
    fig, axes = plt.subplots(rows, cols, figsize=(15, height), squeeze=False)
    fig.subplots_adjust(left=.075, right=.97, bottom=.105, top=.80, hspace=.52, wspace=.30)
    fig.suptitle(title, x=.065, y=.965, ha="left", fontsize=23)
    fig.text(.065, .895, subtitle, color=GREY, fontsize=11)
    for ax in axes.flat:
        ax.grid(alpha=.14)
        ax.set_xlabel("仿真时间 (s)")
    return fig, axes


def export(fig, name, caption):
    for ext in ["png", "svg", "pdf"]:
        fig.savefig(out / f"{name}.{ext}", dpi=180, facecolor="white")
    plt.close(fig)
    with Image.open(out / f"{name}.png") as im:
        assert im.width >= 2000 and im.height >= 1400
    images.append({"name": name, "caption": caption})


simulated = [e for e in experiments if e["steps"]]
groups = {}
for e in simulated:
    key = tuple(e["parameters"][k] for k in ["initial_altitude_ft", "initial_airspeed_ft_s", "engine_failure_altitude_ft", "go_around_altitude_ft", "target_altitude_ft"])
    groups.setdefault(key, []).append(e)
assert len(groups) <= 4, "Expand grid if more than four parameter groups exist"
fig, axes = base("场景一 · 近三小时仿真概览",
                 f"{start:%Y-%m-%d %H:%M}—{end:%H:%M}   |   {len(jobs)}次请求 · {len(simulated)}次有仿真轨迹 · {sum(e['reached'] for e in simulated)}次完成复飞 · {sum(e['evaluation'].get('passed', False) for e in experiments)}次全部评估通过")
styles = ["-", "--", ":"]
markers = ["o", "s", "^"]
for ax, (key, items) in zip(axes.flat, groups.items()):
    h, v, fail, go, target = key
    ax.set_title(f"初始 {h:g} ft / {v:g} ft/s · 失效 {fail:g} ft · 复飞 {go:g} ft", loc="left", fontsize=12)
    ax.axhline(0, color=GREY, lw=.9)
    ax.axhline(target, color=GREY, lw=.9, ls="--", alpha=.7)
    for j, e in enumerate(items):
        s = e["states"]
        ax.plot([x["time"] for x in s], [x["altitude"] for x in s],
                color=[BLUE, BROWN, GREY][j], ls=styles[j], marker=markers[j],
                markersize=3.0, markevery=max(1, len(s)//9), lw=1.9,
                label=f"{e['label']} {e['local_time'][:5]} · {e['outcome']}")
    ax.set_xlim(0, 130)
    ax.set_ylabel("高度 (ft)")
    ax.legend(frameon=False, fontsize=9, loc="best")
fig.text(.065, .03, "虚线横线：目标高度；实线横线：零高度。各工况纵轴范围不同；重合曲线按原始记录保留。", fontsize=10, color=GREY)
export(fig, "01_parameter_overview", "四组参数下的全部八次仿真高度轨迹；同工况重复运行的轨迹保留，负高度完整显示。")

failed = next(e for e in simulated if e["id"] == "run-e3a43e61b25a")
recovered = next(e for e in simulated if e["id"] == "run-d7fd6e1f316e")
fig, axes = base("低高度工况 · 140 与 150 ft/s 对比",
                 "初始400 ft · 左发失效250 ft · 复飞150 ft · 目标400 ft   |   显示起始0—50 s", rows=2, cols=3, height=9)
panels = [("altitude", "高度 (ft)", "高度变化"), ("vertical_speed", "垂直速度 (ft/s)", "下降与拉起"),
          ("roll", "滚转角 (°)", "滚转姿态"), ("airspeed", "空速 (ft/s)", "实际空速"),
          ("throttle_right", "油门指令 (0—1)", "实际施加的右发油门"), ("aileron", "副翼指令 (rad)", "实际施加的副翼")]
for ax, (field, unit, title) in zip(axes.flat, panels):
    for e, color, style in [(failed, BROWN, "--"), (recovered, BLUE, "-")]:
        if field in ["throttle_right", "aileron"]:
            rr = [r for r in e["steps"] if r["state_before"]["time"] <= 50]
            xx = [r["state_before"]["time"] for r in rr]
            yy = [r["applied_action"][field] for r in rr]
            # Segment command applies from state_before.time to result.state.time.
            xx.append(rr[-1]["result"]["state"]["time"])
            yy.append(yy[-1])
            ax.step(xx, yy, where="post", color=color, ls=style, lw=1.9,
                    label=f"{e['label']} · {e['parameters']['initial_airspeed_ft_s']:g} ft/s")
        else:
            ss = [s for s in e["states"] if s["time"] <= 50]
            yy = [math.degrees(s[field]) if field == "roll" else s[field] for s in ss]
            ax.plot([s["time"] for s in ss], yy, color=color, ls=style, lw=1.9, marker="o" if e == recovered else "s", markersize=3,
                    label=f"{e['label']} · {e['parameters']['initial_airspeed_ft_s']:g} ft/s")
        ax.axvline(26, color=GREY, ls=":", lw=.9)
    ax.set_title(title, loc="left", fontsize=13)
    ax.set_ylabel(unit)
    ax.set_xlim(0, 50)
    if field in ["altitude", "vertical_speed", "roll"]:
        ax.axhline(0, color=GREY, lw=.8)
    if field == "roll":
        for sign in [-1, 1]:
            ax.axhline(sign * math.degrees(.35), color=GREY, lw=.8, ls="--")
    if field == "airspeed":
        ax.axhline(120, color=GREY, lw=.8, ls="--")
    if field == "throttle_right":
        ax.set_ylim(0, 1)
    ax.legend(frameon=False, fontsize=9, loc="best")
fig.text(.065, .03, "竖虚线：26 s进入复飞；滚转虚线：±20.1°评估边界。两次运行的配平与提示词内容也不同，此图不构成单因素因果验证。", fontsize=10, color=GREY)
export(fig, "02_low_altitude_comparison", "低高度两工况起始50秒的高度、垂直速度、滚转、空速、实际油门和实际副翼；所有后续记录在概览图及原始数据中保留。")

fig, axes = base("复飞完成的三次运行 · 完整过程", "保留全部仿真步；完成复飞与自动评估结果分别统计", height=9)
completed = [e for e in simulated if e["reached"]]
for ax, (field, unit, title) in zip(axes.flat, [("altitude", "高度 (ft)", "高度"), ("airspeed", "空速 (ft/s)", "空速"),
                                                             ("roll", "滚转角 (°)", "滚转角"), ("vertical_speed", "垂直速度 (ft/s)", "垂直速度")]):
    for i, e in enumerate(completed):
        ss = e["states"]
        yy = [math.degrees(s[field]) if field == "roll" else s[field] for s in ss]
        ax.plot([s["time"] for s in ss], yy, color=[BLUE, BROWN, GREY][i], ls=styles[i], lw=1.8,
                marker=markers[i], markersize=3, markevery=7,
                label=f"{e['label']} · {e['parameters']['initial_altitude_ft']:g} ft / {e['parameters']['initial_airspeed_ft_s']:g} ft/s")
    ax.set_title(title, loc="left", fontsize=13)
    ax.set_ylabel(unit)
    ax.axhline(0 if field != "airspeed" else 120, color=GREY, lw=.8, ls="--")
    if field == "roll":
        for v in [-math.degrees(.35), math.degrees(.35)]:
            ax.axhline(v, color=GREY, lw=.8, ls="--")
    if field == "airspeed":
        ax.axhline(190, color=GREY, lw=.8, ls="--")
    ax.set_xlim(0, 130)
    ax.legend(frameon=False, fontsize=9)
fig.text(.065, .03, "R05、R11完成复飞但存在原始决策控制符号检查项；R07全部评估通过。", fontsize=10, color=GREY)
export(fig, "03_completed_runs", "三次完成复飞的全时段状态曲线；不同工况并列展示，不作为受控单因素对照。")

headers = ["编号 / 时间", "初始高度 / 速度", "失效 / 复飞 / 目标 (ft)", "步数 / 仿真时长", "最低 / 最终高度 (ft)", "运行结果", "自动评估"]
table = []
for e, r in zip(experiments, summary):
    p = e["parameters"]
    fmt = lambda value: "—" if value is None else f"{value:.1f}"
    cells = [f"{e['label']} · {e['local_time']}\n{e['id']}", f"{p.get('initial_altitude_ft', 0):g} ft / {p.get('initial_airspeed_ft_s', 0):g} ft/s",
             " / ".join(f"{p.get(k, 0):g}" for k in ["engine_failure_altitude_ft", "go_around_altitude_ft", "target_altitude_ft"]),
             f"{r['steps']} / {fmt(r['final_time_s'])} s", f"{fmt(r['min_altitude_ft'])} / {fmt(r['final_altitude_ft'])}",
             e["outcome"], "通过" if r["evaluation_passed"] else (r["failure_labels"] or r["error"])]
    table.append("<tr>" + "".join("<td>" + html.escape(str(c)).replace("\n", "<br>") + "</td>" for c in cells) + "</tr>")
caption = "时间范围按任务创建时间筛选；北京时间。仅绘制持久化状态记录，每个标记代表原始采样，无平滑；控制量按实际保持区间绘制。TIMEOUT表示未完成，不等于达到300 s。零高度后的轨迹为模型继续计算的输出，不能视为有效的正常飞行性能。初始空速列为请求参数，曲线为模型实际输出。"
page = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>场景一 · 近三小时仿真</title>
<style>body{{font:16px 'Microsoft YaHei',sans-serif;color:#27343e;background:#f5f7f8;margin:30px auto;max-width:1450px;padding:0 25px}}h1{{font-size:28px}}p{{line-height:1.8}}img{{width:100%;background:white}}section{{margin:28px 0;background:white;padding:22px}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:12px 9px;text-align:left;border-bottom:1px solid #dce2e6}}th{{background:#e9eef1}}a{{color:#355c75}}</style>
<h1>场景一 · 近三小时仿真实验</h1><p>{start:%Y-%m-%d %H:%M}—{end:%H:%M}（北京时间）<br>{html.escape(caption)}</p>
<p><a href="experiments.csv">实验汇总 CSV</a> · <a href="trajectories_and_actions.csv">状态与控制量 CSV</a> · <a href="selected_jobs.json">任务元数据</a></p>
<section><h2>实验记录</h2><table><thead><tr>{''.join('<th>'+h+'</th>' for h in headers)}</tr></thead><tbody>{''.join(table)}</tbody></table></section>
{''.join('<section><img src="'+v['name']+'.png" alt="'+html.escape(v['caption'])+'"><p>'+html.escape(v['caption'])+' <a href="'+v['name']+'.svg">SVG</a> · <a href="'+v['name']+'.pdf">PDF</a></p></section>' for v in images)}
<p>本页不调用仿真服务；脚本与源文件校验值见 manifest.json。</p></html>"""
(out / "index.html").write_text(page, encoding="utf-8")
shutil.copy2(__file__, out / Path(__file__).name)
savejson(out / "manifest.json", {"time_window": {"start": start.isoformat(), "end": end.isoformat()},
         "selection": "run jobs by created_at, scene engine_failure", "source_hashes_sha256": sources,
         "transformations": ["radians to degrees for roll", "raw sampled state lines; no smoothing", "zero-order hold for applied actions",
                             "figure 02 explicitly restricts view to first 50 simulated seconds", "failed/no-step requests tabulated without invented trajectories"],
         "figures": images, "matplotlib_version": matplotlib.__version__, "numpy_version": np.__version__,
         "counts": {"requests": len(jobs), "with_steps": len(simulated), "completed": len(completed),
                    "all_gates_passed": sum(e['evaluation'].get('passed', False) for e in experiments)}})
archive = shutil.make_archive(str(out), "zip", out)
print(json.dumps({"output": str(out), "archive": archive, "summary": summary}, ensure_ascii=False, indent=2))
