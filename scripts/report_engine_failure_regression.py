"""Export an auditable report from the saved scene-one regression matrix."""

import argparse
import hashlib
import html
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--input', default='data/runs/scene1-regression-20261111')
args = parser.parse_args()
folder = ROOT / args.input
reports = json.loads((folder / 'summary.json').read_text(encoding='utf-8'))
matrix = json.loads((folder / 'matrix.json').read_text(encoding='utf-8'))
by_id = {r['case_id']: r for r in reports}
positive = [r for r in reports if r['expected_event'] == 'GO_AROUND_SUCCESS']
negative = [r for r in reports if r['expected_event'] != 'GO_AROUND_SUCCESS']
success = [r for r in positive if r['completed'] and r['state_safe']]
pipeline_path = folder / 'pipeline_verification.json'
pipeline = json.loads(pipeline_path.read_text(encoding='utf-8')) if pipeline_path.exists() else {}
presets = [{'case_id': r['case_id'], 'parameters': r['parameters'], 'tested_steps': r['steps'],
            'controller_matlab_verified': True, 'dify_verification': pipeline.get(r['case_id'])}
           for r in success if r['steps'] <= 90]
(folder / 'frontend_presets.json').write_text(json.dumps(presets, ensure_ascii=False, indent=2), encoding='utf-8')
sources = {str((folder / 'summary.json').relative_to(ROOT)): hashlib.sha256((folder / 'summary.json').read_bytes()).hexdigest()}
if pipeline_path.exists():
    sources[str(pipeline_path.relative_to(ROOT))] = hashlib.sha256(pipeline_path.read_bytes()).hexdigest()
pipeline_text = '; '.join(f"{cid}: {v.get('run_id')} / {v.get('status')}" for cid, v in pipeline.items())
budget_cases = [r['case_id'] for r in success if r['steps'] > 97]


def states(cid):
    path = folder / cid / 'records.json'
    if not path.exists():
        return []
    sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return [r['result']['state'] for r in json.loads(path.read_text(encoding='utf-8'))]


def label(r):
    if r['event'] == 'GO_AROUND_SUCCESS':
        return '完成复飞'
    if r['event'] == 'TIME_LIMIT_REACHED':
        return '按时限终止'
    if not r['steps'] and r.get('error'):
        return '配平/初始化失败'
    return r['event']


plt.rcParams.update({'font.family': 'Microsoft YaHei', 'font.size': 10, 'axes.unicode_minus': False,
                     'axes.spines.top': False, 'axes.spines.right': False, 'svg.fonttype': 'path'})
BLUE, BROWN, GREY = '#355C75', '#915A3C', '#63717C'
fig, axes = plt.subplots(2, 2, figsize=(15, 9))
fig.subplots_adjust(left=.075, right=.97, top=.81, bottom=.11, hspace=.52, wspace=.27)
fig.suptitle('场景一 · 参数回归测试', x=.06, y=.965, ha='left', fontsize=23)
fig.text(.06, .90, f"控制周期2 s · 真实MATLAB模型 · {len(success)}/{len(positive)}组复飞工况完成 · 另有{len(negative)}组时限对照", color=GREY, fontsize=12)
panels = [(['C02', 'C03', 'C04', 'C05', 'C06'], '400 ft初始 · 150 ft复飞 · 速度对比'),
          (['C03', 'C07', 'C04', 'C08'], '400 ft初始 · 复飞高度100 / 150 ft'),
          (['C09', 'C10', 'C11', 'C12', 'C13', 'C14'], '其他高度与目标组合'),
          (['C01', 'C15'], '同一基准工况 · 300 / 60 s时限')]
styles = ['-', '--', ':', '-.', '-', '--']
markers = ['o', 's', '^', 'D', 'v', 'x']
for ax, (ids, title) in zip(axes.flat, panels):
    for index, cid in enumerate(ids):
        if cid not in by_id:
            continue
        r = by_id[cid]
        ss = states(cid)
        p = r['parameters']
        if not ss:
            ax.add_line(Line2D([], [], color=GREY, ls='none', marker='x',
                               label=f"{cid} {p['initial_airspeed_ft_s']:g} ft/s · 配平失败"))
            continue
        if title.startswith('同一'):
            legend = f"{cid} 时限{p['max_simulation_time_s']:g} s"
        elif title.startswith('400 ft初始 · 复飞'):
            legend = f"{cid} {p['initial_airspeed_ft_s']:g} ft/s · 复飞{p['go_around_altitude_ft']:g} ft"
        else:
            legend = f"{cid} {p['initial_airspeed_ft_s']:g} ft/s"
        ax.plot([s['time'] for s in ss], [s['altitude'] for s in ss],
                color=[BLUE, BROWN, GREY][index % 3], ls=styles[index], marker=markers[index],
                markevery=max(1, len(ss) // 8), markersize=3, lw=1.6, label=legend)
    ax.set_title(title, loc='left', fontsize=12)
    ax.set_xlabel('仿真时间 (s)')
    ax.set_ylabel('高度 (ft)')
    ax.axhline(0, color=GREY, lw=.8)
    ax.grid(alpha=.15)
    ax.legend(frameon=False, fontsize=8, loc='best')
fig.text(.06, .035, '曲线为原始采样，无平滑；各面板坐标范围不同。无轨迹的配平失败仅列入图例。全部参数、失败记录和原始数据见报告。', color=GREY, fontsize=10)
for ext in ['png', 'svg', 'pdf']:
    fig.savefig(folder / ('regression_overview.' + ext), dpi=180, facecolor='white')
plt.close(fig)

headers = ['工况', '初始高度 / 空速', '失效 / 复飞 / 目标高度', '运行结果', '最低高度', '最大滚转', '时间 / 步数']
rows, markdown_rows = [], []
for r in reports:
    p, s = r['parameters'], r.get('final_state') or {}
    lo = '—' if r['minimum_altitude_ft'] is None else f"{r['minimum_altitude_ft']:.2f} ft"
    roll = '—' if r['max_abs_roll_deg'] is None else f"{r['max_abs_roll_deg']:.2f}°"
    cells = [r['case_id'], f"{p['initial_altitude_ft']:g} ft / {p['initial_airspeed_ft_s']:g} ft/s",
             ' / '.join(f"{p[k]:g}" for k in ['engine_failure_altitude_ft', 'go_around_altitude_ft', 'target_altitude_ft']) + ' ft',
             label(r), lo, roll, f"{s.get('time', 0):g} s / {r['steps']}"]
    rows.append('<tr>' + ''.join('<td>' + html.escape(c) + '</td>' for c in cells) + '</tr>')
    markdown_rows.append('| ' + ' | '.join(cells) + ' |')

note = ('本报告按预先列出的代表工况统计，未将有限测试点推断为整个连续参数范围的通过率。'
        '控制器测试直接使用当前生产FlightEnv与真实MATLAB模型，未调用Dify；完整Agent验证单独记录。'
        '135 ft/s配平失败属于准备阶段失败；60 s时限对照应返回未完成，不计为复飞成功。'
        '模型控制器最多测试到当前场景时限；超过约97次step的工况仍可能超过现有Dify Agent迭代预算。')
page = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>场景一参数回归</title>
<style>body{{max-width:1450px;margin:30px auto;padding:0 24px;color:#27343e;font:16px 'Microsoft YaHei',sans-serif;line-height:1.7}}img{{width:100%}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border-bottom:1px solid #dce2e6;padding:10px;text-align:left}}th{{background:#e9eef1}}a{{color:#355c75}}</style>
<h1>场景一参数回归</h1><p>已测试{len(reports)}/{len(matrix)}组；复飞工况{len(success)}/{len(positive)}组完成并满足现有安全阈值。</p>
<p>{note}</p><img src="regression_overview.png" alt="不同速度、高度组合及运行时限的原始高度曲线对比">
<table><thead><tr>{''.join('<th>'+h+'</th>' for h in headers)}</tr></thead><tbody>{''.join(rows)}</tbody></table>
<p><a href="summary.csv">汇总CSV</a> · <a href="summary.json">详细结果JSON</a> · <a href="matrix.json">测试矩阵</a> · <a href="regression_overview.pdf">PDF图</a></p>
<p><a href="frontend_presets.json">已测通过且步数不超过90的前端参考参数</a>；其中完整Dify验证单独标记。</p>
<p>完整Dify验证：{html.escape(pipeline_text or '尚未记录')}。<a href="pipeline_verification.json">验证记录</a></p>
<p>超过约97步的模型工况：{html.escape(', '.join(budget_cases) or '无')}；未作为默认演示参数。</p>
<p>每组目录保存configuration.json、records.json、report.json，可逐项追溯。数据来源校验值见visualization_manifest.json。</p></html>"""
(folder / 'index.html').write_text(page, encoding='utf-8')
doc = '# 场景一参数回归测试\n\n' + f"完成{len(reports)}/{len(matrix)}组测试；复飞工况{len(success)}/{len(positive)}组成功。\n\n" + note + '\n\n'
doc += '| ' + ' | '.join(headers) + ' |\n|' + '|'.join(['---'] * len(headers)) + '|\n' + '\n'.join(markdown_rows)
doc += '\n\n完整数据目录：`' + str(folder.relative_to(ROOT)).replace('\\', '/') + '`。\n'
doc += '\n## 完整Dify验证\n\n' + (pipeline_text or '尚未记录') + '\n'
doc += '\n前端参考参数保存于`frontend_presets.json`，仅取模型通过且不超过90步的工况，给Agent迭代预算预留余量。'
doc += '\n\n超过约97步的模型工况：' + (', '.join(budget_cases) or '无') + '。\n'
(ROOT / 'docs/ENGINE_FAILURE_REGRESSION.md').write_text(doc, encoding='utf-8')
(folder / 'visualization_manifest.json').write_text(json.dumps({'source_sha256': sources,
     'transforms': ['raw sampled state lines; no smoothing', 'parameter grouping only; no statistical generalization'],
     'matplotlib': matplotlib.__version__}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'directory': str(folder), 'tested': len(reports), 'positive_cases': len(positive), 'completed': len(success)}))
