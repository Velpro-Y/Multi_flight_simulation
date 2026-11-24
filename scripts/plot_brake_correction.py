"""Plot native saved samples of the independent differential-brake correction test."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--run-id",required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1];folder=root/"data/runs"/args.run_id
    sources={}
    def read(path):
        sources[str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest()
        return json.loads(path.read_text(encoding="utf-8"))
    records=read(folder/"records.json");evaluation=read(folder/"evaluation.json");decisions=read(folder/"decisions.json")
    steps=[r for r in records if r["kind"]=="step"]
    traces=[read(Path(r["result"]["simulation_file"])) for r in steps]
    assert len(steps)==len(decisions) and all(d["source"]=="live_dify" for d in decisions)
    style={"font.family":"Microsoft YaHei","font.size":11,"axes.unicode_minus":False,
           "axes.spines.top":False,"axes.spines.right":False,"svg.fonttype":"path"}
    blue,brown,grey="#355C75","#915A3C","#6B6B6B"
    final=steps[-1]["result"]["state"];p=evaluation["parameters"]
    with plt.rc_context(style):
        fig,grid=plt.subplots(2,3,figsize=(16,9.5));axes=list(grid.flat)
        fig.subplots_adjust(left=.07,right=.97,top=.79,bottom=.14,wspace=.35,hspace=.5)
        fig.suptitle("场景三 · 差动刹车纠偏",x=.06,y=.96,ha="left",fontsize=24,weight="bold")
        fig.text(.06,.9,f"试验点2-4（6DOF适配）   ·   初始 {p['initial_speed_kn']:g} kn   ·   {len(decisions)}次Dify决策",color=grey,fontsize=12)
        fig.text(.06,.85,"超过50 ft触发纠偏，回到30 ft以内并稳定保持",color=grey,fontsize=12)
        for ax in axes:ax.grid(alpha=.15);ax.set_xlabel("仿真时间 (s)");ax.set_xlim(0,final["time"]+.1)
        for trace in traces:
            tr=trace["trajectory"];t=tr["time_s"]
            for ax,key in [(axes[0],"lateral_deviation_ft"),(axes[1],"heading_deg"),
                           (axes[4],"speed_kn"),(axes[5],"lateral_velocity_m_s")]:
                ax.plot(t,tr[key],color=blue,lw=2)
            # Yaw rate is an actual step-end observation, not an interpolated solver output.
        end=[r["result"]["state"]["time"] for r in steps]
        axes[2].plot(end,[r["result"]["state"]["yaw_rate_deg_s"] for r in steps],color=blue,marker=".")
        axes[0].axhspan(-30,30,color="#EDF2F6",zorder=0)
        for v in [-50,50]:axes[0].axhline(v,color=grey,ls=":",lw=1,label="触发 ±50 ft" if v==50 else None)
        for v in [-30,30]:axes[0].axhline(v,color=grey,ls="--",lw=1,label="目标 ±30 ft" if v==30 else None)
        axes[0].set(title="横向偏差",ylabel="偏差 (ft)");axes[0].legend(frameon=False,fontsize=9)
        axes[1].set(title="航向偏差",ylabel="航向偏差 (°)")
        axes[2].set(title="偏航角速度",ylabel="偏航角速度 (°/s)")
        for ax,bound in [(axes[1],3),(axes[2],1),(axes[5],.75)]:
            for v in [-bound,bound]:ax.axhline(v,color=grey,ls=":",lw=.8)
        for key,color,line,label in [("brake_left",blue,"-","左刹车"),("brake_right",brown,"--","右刹车")]:
            for i,trace in enumerate(traces):
                axes[3].step(trace["trajectory"]["time_s"],trace["trajectory"][key],where="post",
                             color=color,ls=line,lw=1.8,label=label if i==0 else None)
        axes[3].set(title="实际主轮刹车指令",ylabel="归一化指令 (0–1)",ylim=(-.02,1.05));axes[3].legend(frameon=False)
        axes[4].set(title="地面速度",ylabel="速度 (kn)",ylim=(0,max(105,max(s["max_speed_kn"] for s in traces)*1.05)))
        axes[5].set(title="横向速度",ylabel="横向速度 (m/s)")
        status="综合评估通过" if evaluation["passed"] else "综合评估未通过"
        fig.text(.06,.055,f"仿真 {final['time']:.2f} s    最终偏差 {final['lateral_deviation_ft']:.2f} ft    稳定保持 {final['stable_duration_s']:.2f} s    检查 {sum(evaluation['hard_gates'].values())}/{len(evaluation['hard_gates'])}    {status}",color=blue,fontsize=12)
        for suffix in ["png","svg"]:fig.savefig(folder/f"correction_visualization.{suffix}",dpi=180,facecolor="white")
        plt.close(fig)
    keys=["time_s","x_m","y_m","lateral_deviation_ft","heading_deg","lateral_velocity_m_s","speed_kn","brake_left","brake_right"]
    with (folder/"correction_trajectory.csv").open("w",newline="",encoding="utf-8-sig") as stream:
        writer=csv.writer(stream);writer.writerow(["step",*keys])
        for i,trace in enumerate(traces,1):writer.writerows((i,*row) for row in zip(*(trace["trajectory"][k] for k in keys)))
    with Image.open(folder/"correction_visualization.png") as im:metadata={"pixels":list(im.size),"dpi":im.info.get("dpi")}
    manifest={"run_id":args.run_id,"script":"scripts/plot_brake_correction.py","source_sha256":sources,
              "script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"image_metadata":metadata,
              "transformations":["Native segments plotted separately; no smoothing or resampling","Yaw rate shown at actual step endpoints","Normalized actual brake commands; no inference of calibrated pressure or forces"],
              "parameters":p,"visual_review":"pending"}
    (folder/"correction_figure_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(folder/"correction_visualization.png")


if __name__=="__main__":main()
