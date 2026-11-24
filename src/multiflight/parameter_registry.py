"""Front-end parameter metadata for the supported simulation scenes."""

from __future__ import annotations

from typing import Any

from .schemas import EngineFailureParameters, GroundDirectionParameters, GroundCorrectionParameters


SCHEMA_VERSION = "0.2.0-draft.1"


class ParameterRegistry:
    def schema(self, scene_id: str, experiment: str | None = None) -> dict[str, Any]:
        if experiment not in {None, "turn", "brake_correction"}:
            raise KeyError(f"Unknown experiment: {experiment}")
        if scene_id == "ground_direction" and experiment == "brake_correction":
            p = GroundCorrectionParameters()
            return {"scene_id": scene_id, "experiment": "brake_correction", "schema_version": "0.4.0-candidate",
                    "runnable": True, "requires_preparation": False, "submit_to": "/api/runs", "parameter_field": "parameters",
                    "supported_prompt_versions": ["0.4.0", "0.4.1"], "parameter_defaults": p.model_dump(),
                    "groups": [{"id": "correction", "label": "试验点2-4 差动刹车纠偏", "fields": [
                        _field(name, label, unit, getattr(p, name), lo, hi)
                        for name, label, unit, lo, hi in [
                            ("initial_speed_kn", "初始地速", "kn", 100, 100),
                            ("initial_lateral_deviation_ft", "初始横向偏差", "ft", -80, 80),
                            ("initial_heading_deg", "初始航向偏差", "deg", -5, 5),
                            ("max_simulation_time_s", "最长仿真时间", "s", 5, 20)]]}],
                    "constraints": ["parameters.experiment必须为brake_correction，显式选择0.4.0",
                                    "超过50ft触发，回到30ft内且姿态/横向运动稳定保持1s",
                                    "前轮0、左右油门相同、自动刹车关闭，使用左右手动刹车纠偏",
                                    "使用原生6DOF质量重心，原文大型机配置不直接套用"]}
        if scene_id == "engine_failure":
            return _engine_failure_schema()
        if scene_id == "ground_deceleration":
            return {
                "scene_id": scene_id,
                "schema_version": SCHEMA_VERSION,
                "runnable": False,
                "reason": "地面减速完整实验流程尚未接入，保留接口",
                "groups": [],
                "constraints": [],
            }
        if scene_id == "ground_direction":
            return {
                "scene_id": scene_id,
                "schema_version": SCHEMA_VERSION,
                "runnable": True,
                "reason": "0.2/0.3逐步协议支持参数化右转；0.3.0仍为刹车候选版本",
                "requires_preparation": False,
                "submit_to": "/api/runs",
                "parameter_field": "parameters",
                "supported_prompt_versions": ["0.2.0", "0.3.0"],
                "experiments": [{"id": "turn", "name": "低速转向", "prompt_versions": ["0.2.0", "0.3.0"]},
                                {"id": "brake_correction", "name": "差动刹车纠偏", "prompt_versions": ["0.4.0"],
                                 "parameters_url": "/api/scenarios/ground_direction/parameters?experiment=brake_correction"}],
                "groups": [{"id": "ground_experiment", "label": "地面状态与目标", "fields": [
                    _field(name, label, unit, getattr(GroundDirectionParameters(), name), lo, hi)
                    for name, label, unit, lo, hi in [
                        ("initial_speed_kn", "初始地速", "kn", 0, 5),
                        ("target_nose_wheel_deg", "目标前轮角", "deg", 20, 75),
                        ("target_heading_change_deg", "目标航向变化", "deg", 150, 180),
                        ("max_simulation_time_s", "最长仿真时间", "s", 5, 20),
                    ]
                ]}],
                "constraints": ["仅支持右转；初始航向、位置和轮角为0",
                                "达到5kn前禁止转向；达到目标航向且运动反向后结束",
                                "参数范围为接口边界，不保证每个组合都完成实验"],
            }
        raise KeyError(f"Unknown scene_id: {scene_id}")

    def defaults(self, scene_id: str) -> dict[str, Any]:
        if scene_id == "ground_direction":
            return GroundDirectionParameters().model_dump()
        if scene_id != "engine_failure":
            raise KeyError(f"No parameter defaults for scene: {scene_id}")
        return EngineFailureParameters().model_dump()


def _field(
    name: str,
    label: str,
    unit: str,
    default: float,
    minimum: float,
    maximum: float,
    *,
    capability: str = "supported",
    reason: str | None = None,
) -> dict[str, Any]:
    value = {
        "name": name,
        "label": label,
        "type": "number",
        "unit": unit,
        "default": default,
        "minimum": minimum,
        "maximum": maximum,
        "required": True,
        "capability": capability,
    }
    if reason:
        value["reason"] = reason
    return value


def _engine_failure_schema() -> dict[str, Any]:
    defaults = EngineFailureParameters()
    return {
        "scene_id": "engine_failure",
        "schema_version": SCHEMA_VERSION,
        "runnable": True,
        "groups": [
            {
                "id": "initial_state",
                "label": "初始状态",
                "fields": [
                    _field(
                        "initial_altitude_ft",
                        "初始高度",
                        "ft",
                        defaults.initial_altitude_ft,
                        400.0,
                        1000.0,
                    ),
                    _field(
                        "initial_airspeed_ft_s",
                        "初始空速",
                        "ft/s",
                        defaults.initial_airspeed_ft_s,
                        135.0,
                        165.0,
                    ),
                ],
            },
            {
                "id": "events",
                "label": "事件高度",
                "fields": [
                    _field(
                        "engine_failure_altitude_ft",
                        "左发失效高度",
                        "ft",
                        defaults.engine_failure_altitude_ft,
                        250.0,
                        800.0,
                    ),
                    _field(
                        "go_around_altitude_ft",
                        "复飞高度",
                        "ft",
                        defaults.go_around_altitude_ft,
                        100.0,
                        700.0,
                    ),
                    _field(
                        "target_altitude_ft",
                        "目标高度",
                        "ft",
                        defaults.target_altitude_ft,
                        400.0,
                        1500.0,
                    ),
                ],
            },
            {
                "id": "environment",
                "label": "环境与运行",
                "fields": [
                    _field(
                        "wind_speed_ft_s",
                        "风速",
                        "ft/s",
                        defaults.wind_speed_ft_s,
                        0.0,
                        30.0,
                        capability="reserved",
                        reason="当前模型尚未接入风场，只允许 0",
                    ),
                    _field(
                        "wind_direction_deg",
                        "风向",
                        "deg",
                        defaults.wind_direction_deg,
                        0.0,
                        360.0,
                        capability="reserved",
                        reason="随风场接口启用",
                    ),
                    _field(
                        "max_simulation_time_s",
                        "最长仿真时间",
                        "s",
                        defaults.max_simulation_time_s,
                        60.0,
                        600.0,
                    ),
                ],
            },
        ],
        "constraints": [
            "initial_altitude_ft > engine_failure_altitude_ft",
            "engine_failure_altitude_ft > go_around_altitude_ft",
            "target_altitude_ft > go_around_altitude_ft",
        ],
    }
