"""Ground scenario adapter for existing Dify reset/step tools, in two stages."""

import json
import math
import os
import subprocess
from pathlib import Path

from ..settings import PROJECT_ROOT, RUN_DIR


class GroundEnv:
    def __init__(self, run_id, configuration=None):
        self.folder = RUN_DIR / run_id
        self.folder.mkdir(parents=True, exist_ok=True)
        self.state = None
        self.sequence = 0

    def get_state(self):
        return self.state

    def reset(self):
        self.sequence = 0
        self.state = {"flight_phase": "READY", "time": 0, "speed_kn": 0,
                      "heading_deg": 0, "x_m": 0, "y_m": 0,
                      "target_wheel_deg": 75, "target_speed_kn": 5}
        return {"state": self.state, "done": False, "event": "GROUND_READY",
                "instruction": "调用step：三个舵面为0，左右油门均0.4，先加速到5kn。"}

    def step(self, action):
        if self.state is None or self.state["flight_phase"] not in {"READY", "TURN_READY"}:
            raise ValueError("先reset，且完成后不可继续step")
        fields = ("aileron", "elevator", "rudder", "throttle_left", "throttle_right")
        values = {k: float(action[k]) for k in fields}
        if not all(math.isfinite(v) for v in values.values()):
            raise ValueError("控制量必须为有限值")
        if any(abs(values[k]) > 1e-8 for k in fields[:3]) or action.get("left_engine_fail"):
            raise ValueError("此地面工况舵面为0，不注入发动机失效")
        accelerate = self.state["flight_phase"] == "READY"
        left, right = values["throttle_left"], values["throttle_right"]
        if not 0 < left <= 0.4 or not 0 <= right <= 0.4:
            raise ValueError("油门必须在已验证的0至0.4范围，左发须大于0")
        if accelerate and abs(left-right) > 1e-8:
            raise ValueError("加速阶段必须对称油门")
        if not accelerate and right != 0 and abs(left-right) > 1e-8:
            raise ValueError("右转阶段仅允许对称油门或内侧右油门0")
        self.sequence += 1
        request = {"nose_wheel_deg": 75, "large_angle_test": True,
                   "steering_rate_deg_s": 30, "differential_throttle": 0,
                   "thrust_policy": "inner_idle" if right == 0 else "offset",
                   "outer_throttle_cap": left,
                   "stage": "accelerate" if accelerate else "turn",
                   "checkpoint_file": str(self.folder / f"ground_step{self.sequence}_checkpoint.mat")}
        if not accelerate:
            request["resume_file"] = str(self.folder / f"ground_step{self.sequence-1}_checkpoint.mat")
        request_path = self.folder / f"ground_step{self.sequence}_request.json"
        output_path = self.folder / f"ground_step{self.sequence}_simulation.json"
        request_path.write_text(json.dumps(request), encoding="utf-8")
        quote = lambda p: str(p).replace("'", "''")
        command = (f"addpath('{quote(PROJECT_ROOT / 'simulink03')}'); "
                   f"run_ground_uturn_demo('{quote(request_path)}','{quote(output_path)}')")
        with (self.folder / f"ground_step{self.sequence}_matlab.log").open("w", encoding="utf-8") as log:
            subprocess.run([os.getenv("MATLAB_EXECUTABLE", "D:/soft/MATLAB/bin/matlab.exe"), "-batch", command],
                           cwd=str(self.folder), stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=240)
        sim = json.loads(output_path.read_text(encoding="utf-8"))
        if accelerate:
            passed = sim["safe"] and sim["final_phase"] == 1 and sim["final_speed_kn"] >= 5
            phase = "TURN_READY" if passed else "FAILED"
        else:
            passed = sim["passed"] and sim["max_actual_front_wheel_angle_deg"] >= 74.9
            phase = "SUCCESS" if passed else "FAILED"
        self.state = {"flight_phase": phase, "time": sim["duration_s"],
                      "speed_kn": sim["final_speed_kn"], "heading_deg": sim["trajectory"]["heading_deg"][-1],
                      "x_m": sim["final_x_m"], "y_m": sim["final_y_m"],
                      "safe": sim["safe"], "on_ground": sim["all_wheels_contact"]}
        return {"state": self.state, "done": not accelerate or not passed,
                "event": "GROUND_SUCCESS" if phase == "SUCCESS" else phase,
                "instruction": ("已达到5kn，从完整保存状态继续：三个舵面0，左油门0.4；"
                                "右油门可0（内侧零推力）或0.4（对称）。75度前轮与速度控制由底层执行。"
                                if phase == "TURN_READY" else "实验结束。"),
                "applied_action": values,
                # Full traces stay in artifacts, not the LLM context/token bill.
                "simulation": {k: v for k, v in sim.items() if k not in {"trajectory", "control"}},
                "simulation_file": str(output_path)}
