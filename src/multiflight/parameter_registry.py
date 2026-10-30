"""Front-end parameter metadata for the supported simulation scenes."""

from __future__ import annotations

from typing import Any

from .schemas import EngineFailureParameters


SCHEMA_VERSION = "0.2.0-draft.1"


class ParameterRegistry:
    def schema(self, scene_id: str) -> dict[str, Any]:
        if scene_id == "engine_failure":
            return _engine_failure_schema()
        if scene_id == "ground_deceleration":
            return {
                "scene_id": scene_id,
                "schema_version": SCHEMA_VERSION,
                "runnable": False,
                "reason": "刹车模块暂缓实现",
                "groups": [],
                "constraints": [],
            }
        if scene_id == "ground_direction":
            return {
                "scene_id": scene_id,
                "schema_version": SCHEMA_VERSION,
                "runnable": False,
                "reason": "场景三模型扩展尚未交付",
                "groups": [],
                "constraints": [],
            }
        raise KeyError(f"Unknown scene_id: {scene_id}")

    def defaults(self, scene_id: str) -> dict[str, Any]:
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
