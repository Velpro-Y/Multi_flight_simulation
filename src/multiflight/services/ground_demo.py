"""Small scene-three smoke test: one decision followed by a fresh simulation."""

import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from ..settings import PROJECT_ROOT, RUN_DIR


class GroundDemoRequest(BaseModel):
    maneuver: Literal["turn", "uturn"] = "turn"
    direction: Literal["left", "right", "straight"] = "right"
    # An explicit angle bypasses Dify for model/interface debugging.
    nose_wheel_deg: Optional[float] = Field(default=None, ge=-10, le=10)
    initial_speed_kn: float = Field(default=5, ge=1, le=5)
    duration_s: float = Field(default=8, ge=1, le=8)
    differential_throttle: float = Field(default=0, ge=0, le=0.1)
    thrust_policy: Literal["offset", "inner_idle"] = "offset"

    @model_validator(mode="after")
    def validate_differential(self):
        if (self.differential_throttle or self.thrust_policy == "inner_idle") and self.maneuver != "uturn":
            raise ValueError("差动油门仅用于uturn模式")
        if self.thrust_policy == "inner_idle" and self.differential_throttle:
            raise ValueError("inner_idle模式不叠加固定油门差")
        return self


class SteeringDecision(BaseModel):
    nose_wheel_deg: float = Field(ge=-10, le=10)


def parse_decision(answer: str) -> SteeringDecision:
    text = answer.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return SteeringDecision.model_validate_json(text)


class GroundDemoService:
    def __init__(self, jobs, dify, executor, execution_lock):
        self.jobs, self.dify = jobs, dify
        self.executor, self.execution_lock = executor, execution_lock

    def start(self, request: GroundDemoRequest):
        run_id = "ground-" + uuid.uuid4().hex[:12]
        job = self.jobs.create(run_id, "run", {
            "scene_id": "ground_direction", **request.model_dump()
        }, "等待地面转向演示")
        self.executor.submit(self.execute, run_id, request)
        return job

    def execute(self, run_id: str, request: GroundDemoRequest):
        folder = RUN_DIR / run_id
        folder.mkdir(parents=True, exist_ok=True)
        try:
            with self.execution_lock:
                self.jobs.update(run_id, status="running", progress=0.1,
                                 message="生成前轮转向指令")
                dify_result = None
                if request.nose_wheel_deg is None:
                    prompt = (
                        "当前为场景三低速地面转向的单次决策测试。仿真由后端执行。"
                        "不要调用reset_simulation或step_simulation等工具。"
                        "只返回JSON对象，格式为{\"nose_wheel_deg\":数字}。"
                        "正角为右转，负角为左转，直行为0；角度范围[-10,10]度。"
                        f"初始速度{request.initial_speed_kn}kn，发动机关闭，释放驻车。"
                        "请对右转选择10度，左转选择-10度，直行选择0度。"
                    )
                    if request.maneuver == "uturn":
                        prompt = prompt.replace(
                            f"初始速度{request.initial_speed_kn}kn，发动机关闭，释放驻车。", "")
                        prompt += ("本次从静止开始，释放驻车，后端开启双发并执行5kn速度控制，"
                                   "达到5kn后按你的转向方向执行掉头。你只选择转向角，"
                                   "后端限制转角速率并在航向变化达到177度时结束。")
                        if request.thrust_policy == "inner_idle":
                            prompt += "转弯期间内侧油门设为模型慢车0，外侧油门根据地速闭环控制。"
                        elif request.differential_throttle:
                            prompt += f"转弯期间后端将内侧发动机油门降低{request.differential_throttle}。"
                    (folder / "prompt.txt").write_text(prompt, encoding="utf-8")
                    dify_result = self.dify.run_agent(
                        scene_prompt=prompt, query=f"任务：{request.direction}。只返回转向JSON。",
                        user=run_id,
                    )
                    (folder / "decision.json").write_text(
                        json.dumps(dify_result, ensure_ascii=False, indent=2), encoding="utf-8")
                    angle = parse_decision(dify_result["answer"]).nose_wheel_deg
                else:
                    angle = request.nose_wheel_deg
                self.jobs.update(run_id, progress=0.3, message="正在运行场景三模型")
                payload = {**request.model_dump(), "nose_wheel_deg": angle}
                if request.maneuver == "uturn":
                    if request.direction == "straight" or angle == 0:
                        raise ValueError("掉头需要left/right方向和非零转向角")
                    payload.update(initial_speed_kn=0, target_speed_kn=5, duration_s=120)
                request_file = folder / "request.json"
                request_file.write_text(json.dumps(payload), encoding="utf-8")
                result_file = folder / "simulation.json"
                matlab = os.getenv("MATLAB_EXECUTABLE", "D:/soft/MATLAB/bin/matlab.exe")
                script_dir = PROJECT_ROOT / "simulink03"
                quote = lambda p: str(p).replace("'", "''")
                command = (f"addpath('{quote(script_dir)}'); "
                           f"{'run_ground_uturn_demo' if request.maneuver == 'uturn' else 'run_ground_direction_demo'}"
                           f"('{quote(request_file)}','{quote(result_file)}')")
                with (folder / "matlab.log").open("w", encoding="utf-8") as log:
                    subprocess.run([matlab, "-batch", command], cwd=str(folder),
                                   stdout=log, stderr=subprocess.STDOUT, check=True, timeout=240)
                simulation = json.loads(result_file.read_text(encoding="utf-8"))
                if dify_result is not None:
                    change = simulation["heading_change_deg"]
                    expected = {"left": -1, "right": 1, "straight": 0}[request.direction]
                    matches = abs(change) < 2 if expected == 0 else expected * change > 1
                    simulation["requested_direction_matches"] = matches
                    simulation["passed"] = simulation["passed"] and matches
                result = {"run_id": run_id, "scene_id": "ground_direction",
                          "parameters": payload,
                          "decision_source": "dify" if dify_result is not None else "manual",
                          "applied_action": {"nose_wheel_deg": angle},
                          "simulation": simulation, "artifact_directory": str(folder),
                          "scope": (f"静止加速至5kn后低速掉头，推力策略{request.thrust_policy}，固定油门差{request.differential_throttle}，177度完成判据"
                                    if request.maneuver == "uturn" else "低速定角转向验证")}
                (folder / "result.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                self.jobs.update(run_id, status="succeeded" if simulation["passed"] else
                                 "completed_with_failures", progress=1,
                                 message="地面转向演示完成", result=result)
                return result
        except Exception as exc:
            self.jobs.update(run_id, status="failed", progress=1,
                             message="地面转向演示失败", error=str(exc))
            return None
