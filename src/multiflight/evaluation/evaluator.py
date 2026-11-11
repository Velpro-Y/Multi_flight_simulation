"""Evaluate raw model decisions and resulting aircraft trajectories."""

from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any, Optional

from ..scene_registry import SceneSpec
from ..settings import (
    ENGINE_OUT_CLIMB_TRIM,
    ENGINE_OUT_DESCENT_TRIM,
    GO_AROUND_ALTITUDE_FT,
    PHASE_ENGINE_OUT_DESCENT,
    PHASE_GO_AROUND,
    PHASE_TWIN_DESCENT,
    TWIN_DESCENT_TRIM,
)


ACTION_FIELDS = (
    "aileron",
    "elevator",
    "rudder",
    "throttle_left",
    "throttle_right",
)


class RunEvaluator:
    def evaluate(
        self,
        scene: SceneSpec,
        records: list[dict[str, Any]],
        prompt_version: str,
        prompt_hash: str,
        runtime_context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if scene.scene_id == "ground_direction":
            return _evaluate_ground(scene, records, prompt_version, prompt_hash)
        steps = [item for item in records if item.get("kind") == "step"]
        parameters = (runtime_context or {}).get("normalized_parameters", {})
        profiles = (runtime_context or {}).get("trim", {}).get("profiles", {})
        go_around_altitude = float(
            parameters.get("go_around_altitude_ft", GO_AROUND_ALTITUDE_FT)
        )
        gates = {
            "has_steps": bool(steps),
            "format_valid": self._format_valid(steps),
            "phase_order_valid": self._phase_order_valid(scene, steps),
            "no_early_go_around": self._no_early_go_around(
                steps, go_around_altitude
            ),
            "control_direction_valid": self._control_direction_valid(
                steps, profiles
            ),
            "state_safe": self._state_safe(scene, steps),
            "completed": self._completed(steps),
        }
        failures = self._failure_labels(gates)
        smoothness = self._smoothness(steps)
        saturation_rate = self._saturation_rate(steps)
        score = self._score(gates, smoothness, saturation_rate)
        return {
            "scene_id": scene.scene_id,
            "prompt_version": prompt_version,
            "prompt_hash": prompt_hash,
            "passed": all(gates.values()),
            "hard_gates": gates,
            "failure_labels": failures,
            "metrics": {
                "steps": len(steps),
                "smoothness": round(smoothness, 6),
                "saturation_rate": round(saturation_rate, 6),
                "score": round(score, 3),
            },
            "phase_trace": self._phase_trace(steps),
        }

    @staticmethod
    def _format_valid(steps: list[dict[str, Any]]) -> bool:
        for step in steps:
            action = step.get("raw_action", {})
            if not all(field in action for field in ACTION_FIELDS):
                return False
            try:
                values = {field: float(action[field]) for field in ACTION_FIELDS}
            except (TypeError, ValueError):
                return False
            if not all(isfinite(value) for value in values.values()):
                return False
            if not all(-1.0 <= values[field] <= 1.0 for field in ACTION_FIELDS[:3]):
                return False
            if not all(0.0 <= values[field] <= 1.0 for field in ACTION_FIELDS[3:]):
                return False
        return True

    @staticmethod
    def _phase_trace(steps: list[dict[str, Any]]) -> list[str]:
        trace: list[str] = []
        for step in steps:
            phase = step.get("result", {}).get("state", {}).get("flight_phase")
            if phase and (not trace or trace[-1] != phase):
                trace.append(phase)
        return trace

    def _phase_order_valid(
        self, scene: SceneSpec, steps: list[dict[str, Any]]
    ) -> bool:
        trace = self._phase_trace(steps)
        if not trace:
            return False
        expected_index = {phase: index for index, phase in enumerate(scene.expected_phase_order)}
        try:
            indices = [expected_index[phase] for phase in trace]
        except KeyError:
            return False
        return indices == sorted(indices) and all(
            after - before <= 1 for before, after in zip(indices, indices[1:])
        )

    @staticmethod
    def _no_early_go_around(
        steps: list[dict[str, Any]], go_around_altitude: float
    ) -> bool:
        for step in steps:
            state_before = step.get("state_before", {})
            result = step.get("result", {})
            state = result.get("state", {})
            # Only assess the transition into GO_AROUND. Once the aircraft is
            # climbing, altitude is expected to exceed the 200 ft trigger.
            transitioned_to_go_around = (
                state_before.get("flight_phase") != PHASE_GO_AROUND
                and state.get("flight_phase") == PHASE_GO_AROUND
            )
            if transitioned_to_go_around:
                if float(state.get("altitude", 1e9)) > go_around_altitude + 2.0:
                    return False
        return True

    @staticmethod
    def _control_direction_valid(
        steps: list[dict[str, Any]], profiles: dict[str, Any]
    ) -> bool:
        for step in steps:
            state = step.get("state_before", {})
            action = step.get("raw_action", {})
            if not state or not action:
                continue
            try:
                rudder = float(action["rudder"])
                aileron = float(action["aileron"])
                yaw_rate = float(state.get("yaw_rate", 0.0))
                roll = float(state.get("roll", 0.0))
                phase = state.get("flight_phase")
            except (TypeError, ValueError, KeyError):
                return False

            trim = _trim_for_phase(phase, profiles)
            # The protected model facts make these two wrong-direction cases
            # unambiguous enough for a deterministic regression gate.
            if yaw_rate > 0.03 and rudder < trim["rudder"] - 0.02:
                return False
            roll_error = roll - trim["roll"]
            if roll_error > 0.04 and aileron < trim["aileron"] - 0.02:
                return False
            if roll_error < -0.04 and aileron > trim["aileron"] + 0.02:
                return False
        return True

    @staticmethod
    def _state_safe(scene: SceneSpec, steps: list[dict[str, Any]]) -> bool:
        safety = scene.safety
        for step in steps:
            state = step.get("result", {}).get("state", {})
            try:
                airspeed = float(state["airspeed"])
                roll = float(state["roll"])
                pitch = float(state["pitch"])
                altitude = float(state["altitude"])
            except (TypeError, ValueError, KeyError):
                return False
            if not all(isfinite(v) for v in (airspeed, roll, pitch, altitude)):
                return False
            if scene.scene_id == "engine_failure" and altitude <= 0:
                return False
            if safety.min_airspeed_ft_s is not None and airspeed < safety.min_airspeed_ft_s:
                return False
            if safety.max_airspeed_ft_s is not None and airspeed > safety.max_airspeed_ft_s:
                return False
            if safety.max_abs_roll_rad is not None and abs(roll) > safety.max_abs_roll_rad:
                return False
            if safety.min_pitch_rad is not None and pitch < safety.min_pitch_rad:
                return False
            if safety.max_pitch_rad is not None and pitch > safety.max_pitch_rad:
                return False
        return len(steps) <= safety.max_steps

    @staticmethod
    def _completed(steps: list[dict[str, Any]]) -> bool:
        if not steps:
            return False
        result = steps[-1].get("result", {})
        return bool(
            result.get("done")
            and (
                result.get("event") == "GO_AROUND_SUCCESS"
                or result.get("state", {}).get("flight_phase") == "SUCCESS"
            )
        )

    @staticmethod
    def _smoothness(steps: list[dict[str, Any]]) -> float:
        if len(steps) < 2:
            return 0.0
        deltas: list[float] = []
        for previous, current in zip(steps, steps[1:]):
            p_action = previous.get("raw_action", {})
            c_action = current.get("raw_action", {})
            try:
                deltas.append(
                    mean(abs(float(c_action[f]) - float(p_action[f])) for f in ACTION_FIELDS)
                )
            except (TypeError, ValueError, KeyError):
                return 1.0
        return mean(deltas) if deltas else 0.0

    @staticmethod
    def _saturation_rate(steps: list[dict[str, Any]]) -> float:
        if not steps:
            return 1.0
        saturated = 0
        total = 0
        for step in steps:
            action = step.get("raw_action", {})
            for field in ACTION_FIELDS[:3]:
                total += 1
                try:
                    if abs(float(action[field])) >= 0.95:
                        saturated += 1
                except (TypeError, ValueError, KeyError):
                    saturated += 1
        return saturated / total if total else 1.0

    @staticmethod
    def _score(gates: dict[str, bool], smoothness: float, saturation_rate: float) -> float:
        hard_score = 90.0 * sum(gates.values()) / len(gates)
        soft_score = max(0.0, 10.0 - 20.0 * smoothness - 10.0 * saturation_rate)
        return hard_score + soft_score

    @staticmethod
    def _failure_labels(gates: dict[str, bool]) -> list[str]:
        mapping = {
            "has_steps": "TIMEOUT",
            "format_valid": "FORMAT_INVALID",
            "phase_order_valid": "PHASE_INVALID",
            "no_early_go_around": "PHASE_EARLY",
            "control_direction_valid": "CONTROL_SIGN_ERROR",
            "state_safe": "STATE_UNSAFE",
            "completed": "TIMEOUT",
        }
        return sorted({mapping[name] for name, passed in gates.items() if not passed})


def _evaluate_ground(scene, records, version, prompt_hash):
    if version.startswith("0.2."):
        return _evaluate_ground_realtime(scene, records, version, prompt_hash)
    steps = [r for r in records if r.get("kind") == "step"]
    reset = [r for r in records if r.get("kind") == "reset"]
    trace = [r["result"]["state"]["flight_phase"] for r in records]
    simulations = [r["result"].get("simulation", {}) for r in steps]
    continuity = False
    if len(simulations) == 2:
        a, b = simulations
        # The first logged point after restoring an operating point can be a
        # solver step after the checkpoint (observed ~10us), not at its exact time.
        # Bound both the gap and physically possible motion, rather than compare
        # two samples at different times using a single unitless tolerance.
        try:
            gap = b["start_time_s"] - a["duration_s"]
            position_bound = max(a["final_speed_kn"], b["initial_speed_kn"]) * 0.5144444444 * max(gap, 0) + 1e-5
            continuity = (-1e-9 <= gap <= 0.001 and
                          abs(b["initial_x_m"]-a["final_x_m"]) <= position_bound and
                          abs(b["initial_y_m"]-a["final_y_m"]) <= position_bound and
                          abs(b["initial_speed_kn"]-a["final_speed_kn"]) <= 10*max(gap, 0)+1e-5)
        except (KeyError, TypeError):
            continuity = False
    final = simulations[-1] if simulations else {}
    gates = {
        "reset_and_two_steps": len(reset) == 1 and len(steps) == 2,
        "format_valid": RunEvaluator._format_valid(steps),
        "phase_order_valid": trace == ["READY", "TURN_READY", "SUCCESS"],
        "accelerated_before_turn": bool(simulations and simulations[0].get("final_speed_kn", 0) >= 5),
        "state_continuity": continuity,
        "state_safe": bool(simulations) and all(s.get("safe") and s.get("all_wheels_contact") for s in simulations),
        "actual_75_reached": final.get("max_actual_front_wheel_angle_deg", 0) >= 74.9,
        "completed": bool(final.get("passed") and final.get("reverse_motion") and steps[-1]["result"].get("done")),
    }
    labels = {"reset_and_two_steps": "TOOL_SEQUENCE_INVALID", "format_valid": "FORMAT_INVALID",
              "phase_order_valid": "PHASE_INVALID", "accelerated_before_turn": "PHASE_EARLY",
              "state_continuity": "STATE_DISCONTINUITY", "state_safe": "STATE_UNSAFE",
              "actual_75_reached": "ANGLE_NOT_REACHED", "completed": "TIMEOUT"}
    return {"scene_id": scene.scene_id, "prompt_version": version, "prompt_hash": prompt_hash,
            "passed": all(gates.values()), "hard_gates": gates,
            "failure_labels": sorted({labels[k] for k, v in gates.items() if not v}),
            "phase_trace": trace,
            "metrics": {"steps": len(steps), "score": 100*sum(gates.values())/len(gates),
                        "heading_change_deg": final.get("heading_change_deg"),
                        "time_s": final.get("duration_s"), "min_turn_speed_kn": final.get("min_turn_speed_kn")},
            "scope": "固定75度右转、两阶段Agent工具决策功能验证，非原试验点完整验收"}


def _evaluate_ground_realtime(scene, records, version, prompt_hash):
    from ..simulation.ground_realtime import GroundRealtimeAction
    steps = [r for r in records if r.get("kind") == "step"]
    reset = [r for r in records if r.get("kind") == "reset"]
    valid = True
    early = False
    continuity = True
    previous = {"time_s": 0, "x_m": 0, "y_m": 0, "speed_kn": 0}
    for record in steps:
        try:
            action = GroundRealtimeAction.model_validate(record["raw_action"])
            early |= action.nose_wheel_deg > 0 and not record["state_before"].get("reached_5kn")
        except Exception:
            valid = False
        s = record["result"].get("simulation", {})
        try:
            gap = s["start_time_s"]-previous["time_s"]
            motion = max(previous["speed_kn"], s["initial_speed_kn"])*0.5144444444*max(gap, 0)+1e-5
            continuity &= (-1e-9 <= gap <= .001 and
                           abs(s["initial_x_m"]-previous["x_m"]) <= motion and
                           abs(s["initial_y_m"]-previous["y_m"]) <= motion and
                           0 < s["time_s"]-previous["time_s"] <= .5001)
        except (KeyError, TypeError):
            continuity = False
        previous = s
    sims = [r["result"].get("simulation", {}) for r in steps]
    final = sims[-1] if sims else {}
    gates = {
        "reset_and_multiple_decisions": len(reset) == 1 and 3 <= len(steps) <= 40,
        "format_valid": valid and bool(steps), "no_early_steering": not early,
        "state_continuity": continuity and bool(steps),
        "state_safe": bool(sims) and all(s.get("safe") and s.get("on_ground") for s in sims),
        "actual_75_reached": any(s.get("max_wheel_deg", 0) >= 74.9 for s in sims),
        "completed": bool(final.get("complete") and steps[-1]["result"].get("done")),
    }
    trace = []
    for record in records:
        phase = record["result"]["state"]["flight_phase"]
        if not trace or trace[-1] != phase: trace.append(phase)
    return {"scene_id": scene.scene_id, "prompt_version": version, "prompt_hash": prompt_hash,
            "passed": all(gates.values()), "hard_gates": gates,
            "failure_labels": [k.upper() for k, ok in gates.items() if not ok], "phase_trace": trace,
            "metrics": {"steps": len(steps), "score": 100*sum(gates.values())/len(gates),
                        "time_s": final.get("time_s"), "heading_change_deg": final.get("heading_deg"),
                        "max_wheel_deg": max([s.get("max_wheel_deg", 0) for s in sims], default=0)},
            "scope": "Dify每0.5秒仿真时间直接决定油门和前轮角，无PI代驾；非墙钟硬实时"}


def _trim_for_phase(
    phase: Optional[str], profiles: Optional[dict[str, Any]] = None
) -> dict[str, float]:
    profiles = profiles or {}
    if phase == PHASE_ENGINE_OUT_DESCENT:
        return profiles.get("engine_out_descent", ENGINE_OUT_DESCENT_TRIM)
    if phase == PHASE_GO_AROUND:
        return profiles.get("engine_out_climb", ENGINE_OUT_CLIMB_TRIM)
    if phase == PHASE_TWIN_DESCENT:
        return profiles.get("twin_descent", TWIN_DESCENT_TRIM)
    return profiles.get("twin_descent", TWIN_DESCENT_TRIM)

