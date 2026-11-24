"""Visualize a saved seven-field Dify run; no simulation or API calls."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch
from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', default='run-d38f47576572')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    folder = root / 'data/runs' / args.run_id
    sources = {}

    def read(path):
        sources[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return json.loads(path.read_text(encoding='utf-8'))

    records = read(folder / 'records.json')
    decisions = read(folder / 'decisions.json')
    evaluation = read(folder / 'evaluation.json')
    parameters = evaluation.get('parameters', {})
    target_heading = parameters.get('target_heading_change_deg', 177)
    steps = [r for r in records if r['kind'] == 'step']
    traces = [read(Path(r['result']['simulation_file'])) for r in steps]
    assert len(steps) == len(decisions) and steps
    assert all(d['source'] == 'live_dify' for d in decisions)
    final = steps[-1]['result']['state']
    start = np.array([r['state_before']['time'] for r in steps])
    end = np.array([r['result']['state']['time'] for r in steps])
    times = np.r_[start, final['time']]
    blue, brown, grey = '#355C75', '#915A3C', '#6B6B6B'
    style = {'font.family': 'Microsoft YaHei', 'font.size': 11,
             'axes.unicode_minus': False, 'axes.spines.top': False,
             'axes.spines.right': False, 'svg.fonttype': 'path', 'pdf.fonttype': 42}

    with plt.rc_context(style):
        fig, grid = plt.subplots(2, 3, figsize=(16, 9.5))
        ax = list(grid.flat)
        fig.subplots_adjust(left=.065, right=.975, bottom=.14, top=.77 if parameters else .81,
                            wspace=.34, hspace=.48)
        fig.suptitle('场景三 · 刹车与转向闭环仿真', x=.055, y=.965,
                     ha='left', fontsize=24, weight='bold')
        fig.text(.055, .905, f"提示词 v{evaluation['prompt_version']}   ·   {len(decisions)} 次实时决策   ·   手动差动刹车 / 自动刹车",
                 color=grey, fontsize=12)
        if parameters:
            fig.text(.055, .855, f"初始地速 {parameters['initial_speed_kn']:g} kn   ·   前轮目标 {parameters['target_nose_wheel_deg']:g}°   ·   航向目标 {target_heading:g}°",
                     color=grey, fontsize=12)
        for a in ax:
            a.grid(color='#E6E6E6', lw=.7)
            a.set_axisbelow(True)

        keys = ['time_s', 'x_m', 'y_m', 'heading_deg', 'speed_kn',
                'brake_left', 'brake_right', 'steering_limit_deg']
        rows = []
        for index, trace in enumerate(traces):
            tr = trace['trajectory']
            assert all(np.isfinite(tr[k]).all() for k in keys)
            assert len(set(len(tr[k]) for k in keys)) == 1
            # Plot stored segments separately, preserving any boundaries/gaps.
            ax[0].plot(tr['y_m'], tr['x_m'], color=blue, lw=2.2)
            ax[1].plot(tr['time_s'], tr['heading_deg'], color=blue, lw=2)
            ax[2].plot(tr['time_s'], tr['speed_kn'], color=blue, lw=2)
            ax[3].plot(tr['time_s'], tr['steering_limit_deg'], color=grey,
                       ls=':', lw=1.3, label='转角上限' if index == 0 else None)
            for field, color, ls, label in [('brake_left', blue, '-', '左刹车'),
                                          ('brake_right', brown, '--', '右刹车')]:
                ax[5].step(tr['time_s'], tr[field], where='post', color=color,
                           ls=ls, lw=2, label=label if index == 0 else None)
            rows.extend((index+1, *row) for row in zip(*(tr[k] for k in keys)))

        initial = steps[0]['state_before']
        ax[0].scatter(initial['y_m'], initial['x_m'], marker='o', s=42,
                      color=blue, label='起点', zorder=4)
        ax[0].scatter(final['y_m'], final['x_m'], marker='*', s=120,
                      color=brown, label='终点', zorder=4)
        ax[0].set(title='01  重心地面轨迹', xlabel='横向 Ye (m)',
                  ylabel='初始前进方向 Xe (m)')
        ax[0].set_aspect('equal', adjustable='box')
        ax[0].legend(frameon=False, fontsize=10, loc='lower right')
        ax[1].axhline(target_heading, color=grey, ls=':', label=f'终止阈值 {target_heading:g}°')
        ax[1].set(title='02  航向变化', ylabel='航向角 (°)', ylim=(-5, max(target_heading, final['heading_deg'])+10))
        ax[1].legend(frameon=False, fontsize=10, loc='lower right')
        ax[2].axhline(5, color=grey, ls=':', label='起转速度 5 kn')
        ax[2].set(title='03  地面速度', ylabel='速度 (kn)')
        ax[2].set_ylim(bottom=0)
        ax[2].legend(frameon=False, fontsize=10, loc='upper right')

        def command(axis, key, color, label, ls='-'):
            values = [r['raw_action'][key] for r in steps]
            axis.step(times, [*values, values[-1]], where='post',
                      color=color, label=label, ls=ls, lw=1.9)

        command(ax[3], 'nose_wheel_deg', brown, '目标角', '--')
        ax[3].plot(np.r_[0, end], [0, *[r['result']['state']['wheel_deg'] for r in steps]],
                   color=blue, marker='o', ms=3, lw=1.7, label='实际角（步末）')
        ax[3].set(title='04  前轮转角', ylabel='转角 (°)', ylim=(-3, 85))
        ax[3].legend(frameon=False, fontsize=9, loc='lower right')
        command(ax[4], 'throttle_left', blue, '左油门')
        command(ax[4], 'throttle_right', brown, '右油门', '--')
        ax[4].set(title='05  左右油门', ylabel='油门指令 (0–1)', ylim=(-.015, .45))
        ax[4].legend(frameon=False, fontsize=10, loc='upper right')
        for r, t0, t1 in zip(steps, start, end):
            if r['raw_action']['brake_system_mode'] == 1:
                ax[5].axvspan(t0, t1, color='#E5E5E5', zorder=0)
        max_brake = max(max(t['trajectory'][k]) for t in traces for k in ['brake_left', 'brake_right'])
        ax[5].set(title='06  实际主轮刹车指令', ylabel='刹车指令 (0–1)', ylim=(-.01, max(.42, max_brake*1.1)))
        handles, labels = ax[5].get_legend_handles_labels()
        ax[5].legend(handles + [Patch(facecolor='#E5E5E5')],
                     labels + ['自动模式'], frameon=False, fontsize=10, loc='upper right')
        for a in ax[1:]:
            a.set_xlabel('仿真时间 (s)')
            a.set_xlim(0, final['time']+.08)
        fig.text(.055, .055,
                 f"仿真 {final['time']:.2f} s     航向变化 {final['heading_deg']:.2f}°"
                 f"     最大前轮角 {max(t['max_wheel_deg'] for t in traces):.0f}°"
                 f"     末速度 {final['speed_kn']:.2f} kn"
                 f"     检查 {sum(evaluation['hard_gates'].values())}/{len(evaluation['hard_gates'])} 通过",
                 fontsize=13, color=blue)
        stem = folder / 'brake_visualization'
        for suffix in ['png', 'svg', 'pdf']:
            fig.savefig(stem.with_suffix('.'+suffix), dpi=180, facecolor='white')
        plt.close(fig)

    with (folder / 'brake_visualization_data.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream)
        writer.writerow(['step', *keys]); writer.writerows(rows)
    with Image.open(stem.with_suffix('.png')) as image:
        metadata = {'pixels': list(image.size), 'dpi': image.info.get('dpi'), 'mode': image.mode}
    manifest = {'run_id': args.run_id, 'script': str(Path(__file__).resolve()),
                'parameters': parameters,
                'source_sha256': sources, 'source_segments': len(traces),
                'sample_rows': len(rows), 'image_metadata': metadata,
                'matplotlib_version': matplotlib.__version__,
                'transformations': ['Native trajectory segments; no smoothing or resampling',
                                    'Raw commands shown as zero-order holds',
                                    'Actual wheel angle shown only at step endpoints',
                                    'Automatic brake mode highlighted from requested mode'],
                'validation': {'layout_review': 'pending', 'data_finite': True},
                'alt_text': '六联图展示重心轨迹、航向、速度、前轮角、油门和实际刹车指令。'
                            f"{final['time']:.2f}秒时航向变化{final['heading_deg']:.2f}度。"
                            '刹车曲线为模型归一化指令，灰色区间为自动模式。'}
    (folder/'brake_visualization_manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(stem.with_suffix('.png'))


if __name__ == '__main__':
    main()
