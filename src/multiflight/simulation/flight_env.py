"""
=========================================================
Flight Environment

负责：

1. reset()
2. step()
3. get_state()

=========================================================
"""

import os
import logging

from ..settings import *
from .matlab_engine import get_engine
from .engine_failure_control import single_engine_controls
from .flight_safety import state_limit_reason
from ..scene_registry import SceneRegistry

import csv
from copy import deepcopy


logger = logging.getLogger(__name__)


class FlightEnv:

    def __init__(self, run_id: str = "manual", configuration=None):

        self.eng = get_engine()

        self.configuration = deepcopy(configuration) if configuration else {}
        parameters = self.configuration.get("normalized_parameters", {})
        trim_result = self.configuration.get("trim", {})
        profiles = trim_result.get("profiles", {})
        self.twin_descent_trim = deepcopy(
            profiles.get("twin_descent", TWIN_DESCENT_TRIM)
        )
        self.engine_out_descent_trim = deepcopy(
            profiles.get("engine_out_descent", ENGINE_OUT_DESCENT_TRIM)
        )
        self.engine_out_climb_trim = deepcopy(
            profiles.get("engine_out_climb", ENGINE_OUT_CLIMB_TRIM)
        )
        self.initial_state = deepcopy(trim_result.get("initial_state"))
        self.initial_altitude = float(
            parameters.get("initial_altitude_ft", DEFAULT_STATE["AltitudeMSL"])
        )
        self.engine_failure_altitude = float(
            parameters.get(
                "engine_failure_altitude_ft", ENGINE_FAILURE_ALTITUDE_FT
            )
        )
        self.go_around_altitude = float(
            parameters.get("go_around_altitude_ft", GO_AROUND_ALTITUDE_FT)
        )
        self.max_simulation_time = float(
            parameters.get("max_simulation_time_s", 300.0)
        )

        self.model = MODEL_NAME
        self.state_file = str(STATE_FILE)
        self.time = 0
        self.current_altitude = self.initial_altitude
        self.last_altitude = self.initial_altitude
        self.target_altitude = float(
            parameters.get("target_altitude_ft", TARGET_ALTITUDE_FT)
        )
        self.left_engine_fail = False
        self.flight_phase = PHASE_TWIN_DESCENT
        self.go_around_time = 0.0
        self._reset_single_engine_stabilizer(self.engine_out_descent_trim)
        self.run_id = run_id
        self.safety_limits = SceneRegistry().get("engine_failure").safety
        self._terminal_result = None
        self.log_file = LOG_DIR / f"{run_id}_telemetry.csv"


        # 创建目录
        # STATE_DIR.mkdir(exist_ok=True)
        LOG_DIR.mkdir(exist_ok=True)

    # =====================================================
    # Reset
    # =====================================================

    def reset(self):

        logger.info("Reset Flight Environment")
        self._terminal_result = None

        self.time = 0
        self.last_altitude = self.initial_altitude
        self.current_altitude = self.initial_altitude
        self.left_engine_fail = False
        self.flight_phase = PHASE_TWIN_DESCENT
        self.go_around_time = 0.0
        self._reset_single_engine_stabilizer(self.engine_out_descent_trim)

        # 初始化/清空历史日志并写入表头
        with open(self.log_file, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "time", "altitude", "airspeed", "vertical_speed", "roll",
                "pitch", "roll_rate", "pitch_rate", "yaw_rate", "event",
                "flight_phase",
                "aileron", "elevator", "rudder", "throttle_left",
                "throttle_right"
            ])

        logger.info(f"Current Working Directory: {os.getcwd()}")
        logger.info(f"State File: {self.state_file}")
        if os.path.exists(self.state_file):
            os.remove(self.state_file)

        # 清除上一轮 Simulink 状态
        self.eng.eval("""
                clear xFinal simIn simOut;
                """, nargout=0)

        logger.info("Environment Ready")

        initial_state = self.get_state()

        return {
            "done": False,
            "event": "RESET",
            "instruction": (
                "Aircraft initialized successfully. Maintain twin-engine "
                f"descent to {self.engine_failure_altitude:.1f} ft."
            ),
            "state": initial_state
        }
    # =====================================================
    # Step
    # =====================================================

    def step(self, action: dict):

        if self._terminal_result is not None:
            return deepcopy(self._terminal_result)

        logger.info(f"Receive Action : {action}")

        event = "NORMAL"
        instruction = "Maintain stable descent."

        # -------------------------
        #  控制限幅与左发强制切断
        # -------------------------
        aileron = max(ACTION_LIMIT["aileron"][0], min(ACTION_LIMIT["aileron"][1], action["aileron"]))
        elevator = max(ACTION_LIMIT["elevator"][0], min(ACTION_LIMIT["elevator"][1], action["elevator"]))
        rudder = max(ACTION_LIMIT["rudder"][0], min(ACTION_LIMIT["rudder"][1], action["rudder"]))

        # 如果左发失效，强制覆盖左油门为 0.0，否则使用传入动作
        if self.left_engine_fail:
            throttle_left = 0.0
        else:
            throttle_left = max(ACTION_LIMIT["throttle"][0], min(ACTION_LIMIT["throttle"][1], action["throttle_left"]))

        throttle_right = max(ACTION_LIMIT["throttle"][0], min(ACTION_LIMIT["throttle"][1], action["throttle_right"]))

        # 左发失效后由低层增稳器接管。300--200 ft 使用单发下降配平；
        # 到 200 ft 后才在 6 s 内平滑过渡到单发爬升配平。
        engine_out_active_at_step_start = (
            self.flight_phase in {PHASE_ENGINE_OUT_DESCENT, PHASE_GO_AROUND}
        )
        go_around_active_at_step_start = self.flight_phase == PHASE_GO_AROUND
        if engine_out_active_at_step_start:
            state_before_step = self.get_state()
            stabilized = self._single_engine_stabilizer(
                state_before_step,
                go_around=go_around_active_at_step_start,
            )
            aileron = stabilized["aileron"]
            elevator = stabilized["elevator"]
            rudder = stabilized["rudder"]
            throttle_left = 0.0
            throttle_right = stabilized["throttle_right"]
            logger.info(f"Single-engine stabilizer applied: {stabilized}")

        # -------------------------
        # 左发失效
        # -------------------------
        if engine_out_active_at_step_start:
            throttle_left = 0.0

        # -------------------------
        # 1. 计算这一步的起始时间和停止时间
        # -------------------------
        start_time = self.time
        next_stop_time = self.time + STEP_TIME

        # -------------------------
        # 2. 核心修复代码：注入控制量 + 严格指定仿真时间区间 [start_time, next_stop_time]
        # -------------------------
        self.eng.workspace['AileronCmd'] = float(aileron)
        self.eng.workspace['ElevatorCmd'] = float(elevator)
        self.eng.workspace['RudderCmd'] = float(rudder)
        self.eng.workspace['Throttle_Left'] = float(throttle_left)
        self.eng.workspace['Throttle_Right'] = float(throttle_right)

        sim_prep_cmds = (
            f"simIn = Simulink.SimulationInput('{self.model}'); "
            f"simIn = simIn.setModelParameter('StartTime', '{start_time}'); "  # 👈 必须指定 StartTime!
            f"simIn = simIn.setModelParameter('StopTime', '{next_stop_time}'); "
            f"simIn = simIn.setVariable('AileronCmd', {float(aileron)}); "
            f"simIn = simIn.setVariable('ElevatorCmd', {float(elevator)}); "
            f"simIn = simIn.setVariable('RudderCmd', {float(rudder)}); "
            f"simIn = simIn.setVariable('Throttle_Left', {float(throttle_left)}); "
            f"simIn = simIn.setVariable('Throttle_Right', {float(throttle_right)}); "
        )
        self.eng.eval(sim_prep_cmds, nargout=0)

        if not os.path.exists(self.state_file) and self.initial_state:
            initial = self.initial_state
            eom = f"{self.model}/6DOF EOM/6DOF (Euler Angles)"
            initial_cmd = (
                f"simIn = simIn.setBlockParameter('{eom}', "
                f"'xme_0', '{_vector(initial, ('XN', 'YE', 'ZD'))}'); "
                f"simIn = simIn.setBlockParameter('{eom}', "
                f"'Vm_0', '{_vector(initial, ('U', 'V', 'W'))}'); "
                f"simIn = simIn.setBlockParameter('{eom}', "
                f"'eul_0', '{_vector(initial, ('phi', 'theta', 'psi'))}'); "
                f"simIn = simIn.setBlockParameter('{eom}', "
                f"'pm_0', '{_vector(initial, ('p', 'q', 'r'))}');"
            )
            self.eng.eval(initial_cmd, nargout=0)

        # -------------------------
        # 3. 如果存在上一时刻状态，载入 xFinal 作为当前 step 的 InitialState
        # -------------------------
        if os.path.exists(self.state_file):
            self.eng.eval(
                f"load('{self.state_file}', 'xFinal'); "
                # f"simIn = simIn.setModelParameter('LoadInitialState', 'on'); "  # 👈 强制开启标志位
                f"simIn = simIn.setInitialState(xFinal);",
                nargout=0
            )

        self.last_altitude = self.current_altitude
        # -------------------------
        # 4. 执行单步仿真并保存最新的 xFinal 状态
        # -------------------------
        sim_run_cmds = (
            "simOut = sim(simIn); "
            "xFinal = simOut.xFinal; "
            f"save('{self.state_file}', 'xFinal');"
        )
        self.eng.eval(sim_run_cmds, nargout=0)

        # -------------------------
        # 5. 仿真成功后，Python 侧时间戳跟随累计
        # -------------------------
        self.time = next_stop_time
        if go_around_active_at_step_start:
            self.go_around_time += STEP_TIME

        state = self.get_state()
        self.current_altitude = state["altitude"]

        # 阶段 1 -> 2：300 ft 左发失效，但继续稳定下降。
        if (
            self.flight_phase == PHASE_TWIN_DESCENT
            and state["altitude"] <= self.engine_failure_altitude
        ):
            self.left_engine_fail = True
            self.flight_phase = PHASE_ENGINE_OUT_DESCENT
            self.go_around_time = 0.0
            self._reset_single_engine_stabilizer(self.engine_out_descent_trim)
            event = "LEFT_ENGINE_FAILURE"
            instruction = (
                f"LEFT ENGINE FAILURE at {self.engine_failure_altitude:.1f} ft. Keep throttle_left "
                "at 0.0 and continue a stabilized single-engine descent to "
                f"{self.go_around_altitude:.1f} ft; do not initiate the go-around yet."
            )

        # 阶段 2 -> 3：200 ft 才发出复飞指令并启动平滑调度。
        elif (
            self.flight_phase == PHASE_ENGINE_OUT_DESCENT
            and state["altitude"] <= self.go_around_altitude
        ):
            self.flight_phase = PHASE_GO_AROUND
            self.go_around_time = 0.0
            event = "GO_AROUND_INITIATED"
            instruction = (
                f"GO-AROUND initiated at {self.go_around_altitude:.1f} ft. The stabilizer will "
                "blend from engine-out descent trim to validated single-engine "
                "climb trim over 6 seconds."
            )
        elif self.flight_phase == PHASE_ENGINE_OUT_DESCENT:
            event = "SINGLE_ENGINE_DESCENT"
            instruction = (
                "Continue stabilized single-engine descent at about -9.84 ft/s "
                f"towards {self.go_around_altitude:.1f} ft."
            )
        elif self.flight_phase == PHASE_GO_AROUND:
            event = "SINGLE_ENGINE_GO_AROUND"
            instruction = (
                "Executing single-engine go-around. Do not fight the internal "
                f"rate-feedback stabilizer; climb steadily towards {self.target_altitude:.1f} ft."
            )

        # -------------------------
        # 6. 完成判定与最终状态
        # -------------------------
        state = self.get_state()
        done = (
            self.flight_phase == PHASE_GO_AROUND
            and state["altitude"] >= self.target_altitude
        )
        safety_reason = state_limit_reason(state, self.safety_limits)
        if safety_reason:
            done = True
            event = safety_reason
            instruction = f"Simulation terminated: {safety_reason}. Do not call step again."
            state["termination_reason"] = safety_reason
        elif done:
            self.flight_phase = PHASE_SUCCESS
            state["flight_phase"] = PHASE_SUCCESS
            event = "GO_AROUND_SUCCESS"
            instruction = (
                "Go-around successful! Target altitude reached on single engine."
            )
        elif self.time >= self.max_simulation_time:
            done = True
            event = "TIME_LIMIT_REACHED"
            instruction = "Maximum simulation time reached before task completion."

        # -------------------------
        # 7. 记录本步最终事件和阶段
        # -------------------------
        try:
            with open(self.log_file, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    round(self.time, 2),
                    round(state["altitude"], 2),
                    round(state["airspeed"], 2),
                    round(state["vertical_speed"], 2),
                    round(state["roll"], 5),
                    round(state["pitch"], 5),
                    round(state["roll_rate"], 5),
                    round(state["pitch_rate"], 5),
                    round(state["yaw_rate"], 5),
                    event,
                    state["flight_phase"],
                    round(aileron, 6),
                    round(elevator, 6),
                    round(rudder, 6),
                    round(throttle_left, 6),
                    round(throttle_right, 6)
                ])
        except Exception as e:
            logger.error(f"Failed to write telemetry log: {e}")

        result = {
            "done": done,
            "event": event,
            "instruction": instruction,
            "state": state,
            "applied_action": {
                "aileron": float(aileron),
                "elevator": float(elevator),
                "rudder": float(rudder),
                "throttle_left": float(throttle_left),
                "throttle_right": float(throttle_right),
            },
        }
        if done:
            self._terminal_result = deepcopy(result)
        return result

    # =====================================================
    # 单发低层增稳器
    # =====================================================

    @staticmethod
    def _clamp(value, lower, upper):
        return min(max(value, lower), upper)

    def _reset_single_engine_stabilizer(self, trim):
        self._se_previous_aileron = trim["aileron"]
        self._se_previous_elevator = trim["elevator"]
        self._se_previous_rudder = trim["rudder"]
        self._se_previous_throttle = trim["throttle_right"]

    @staticmethod
    def _interpolate_trim(start_trim, end_trim, blend):
        keys = (
            "vertical_speed", "airspeed", "roll", "pitch", "aileron",
            "elevator", "rudder", "throttle_right",
        )
        return {
            key: start_trim[key] + blend * (end_trim[key] - start_trim[key])
            for key in keys
        }

    def _single_engine_stabilizer(self, state, go_around=False):
        """Coordinate trim transition and feedback at the two-second interval."""
        return single_engine_controls(self, state, go_around)

    # =====================================================
    # 获取飞机状态
    # =====================================================

    def get_state(self):
        # 1. 检查 simOut 是否存在
        is_exist = self.eng.eval("exist('simOut', 'var')", nargout=1)

        # 预定义一套完整的默认/初始状态字典（防止 KeyError）
        default_state = {
            "status": "reset",
            "time": self.time,
            "altitude": self.initial_altitude,
            "airspeed": self.twin_descent_trim["airspeed"],
            "vertical_speed": self.twin_descent_trim["vertical_speed"],
            "roll": self.twin_descent_trim["roll"],
            "pitch": self.twin_descent_trim["pitch"],
            "yaw": float((self.initial_state or {}).get("psi", 0.0)),
            "roll_rate": float((self.initial_state or {}).get("p", 0.0)),
            "pitch_rate": float((self.initial_state or {}).get("q", 0.0)),
            "yaw_rate": float((self.initial_state or {}).get("r", 0.0)),
            "left_engine_fail": self.left_engine_fail,
            "flight_phase": self.flight_phase,
        }

        if is_exist == 0:
            self.last_altitude = self.initial_altitude
            return default_state
        ze = float(self.eng.eval("simOut.Ze.Data(end)"))

        u = float(self.eng.eval("simOut.u.Data(end)"))
        v = float(self.eng.eval("simOut.v.Data(end)"))
        w = float(self.eng.eval("simOut.w.Data(end)"))

        phi = float(self.eng.eval("simOut.phi.Data(end)"))
        theta = float(self.eng.eval("simOut.theta.Data(end)"))
        psi = float(self.eng.eval("simOut.psi.Data(end)"))

        p = float(self.eng.eval("simOut.p.Data(end)"))
        q = float(self.eng.eval("simOut.q.Data(end)"))
        r = float(self.eng.eval("simOut.r.Data(end)"))

        altitude = -ze * M_TO_FT

        airspeed = ((u ** 2 + v ** 2 + w ** 2) ** 0.5) * MPS_TO_FPS
        actual_vertical_speed = (altitude - self.last_altitude) / STEP_TIME
        logger.info(f"Actual vertical speed: {actual_vertical_speed}")
        return {

            "time": self.time,

            "altitude": altitude,

            "airspeed": airspeed,

            "vertical_speed": actual_vertical_speed,

            "roll": phi,

            "pitch": theta,

            "yaw": psi,

            "roll_rate": p,

            "pitch_rate": q,

            "yaw_rate": r,

            "left_engine_fail": self.left_engine_fail,

            "flight_phase": self.flight_phase,
        }

    # =====================================================
    # 关闭环境
    # =====================================================

    def close(self):

        logger.info("Flight Environment Closed")


def _vector(values, keys):
    return "[" + " ".join(f"{float(values[key]):.15g}" for key in keys) + "]"
