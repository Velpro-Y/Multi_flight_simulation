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
    ) -> dict[str, Any]:
        steps = [item for item in records if item.get("kind") == "step"]
        gates = {
            "has_steps": bool(steps),
            "format_valid": self._format_valid(steps),
            "phase_order_valid": self._phase_order_valid(scene, steps),
            "no_early_go_around": self._no_early_go_around(steps),
            "control_direction_valid": self._control_direction_valid(steps),
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
    def _no_early_go_around(steps: list[dict[str, Any]]) -> bool:
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
                if float(state.get("altitude", 1e9)) > GO_AROUND_ALTITUDE_FT + 2.0:
                    return False
        return True

    @staticmethod
    def _control_direction_valid(steps: list[dict[str, Any]]) -> bool:
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

            trim = _trim_for_phase(phase)
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
            except (TypeError, ValueError, KeyError):
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
        return bool(steps and steps[-1].get("result", {}).get("done"))

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


def _trim_for_phase(phase: Optional[str]) -> dict[str, float]:
    if phase == PHASE_ENGINE_OUT_DESCENT:
        return ENGINE_OUT_DESCENT_TRIM
    if phase == PHASE_GO_AROUND:
        return ENGINE_OUT_CLIMB_TRIM
    if phase == PHASE_TWIN_DESCENT:
        return TWIN_DESCENT_TRIM
    return TWIN_DESCENT_TRIM

