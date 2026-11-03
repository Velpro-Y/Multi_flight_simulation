"""MATLAB-backed trim preparation for parameterized simulations."""

from __future__ import annotations

from typing import Any, Protocol

from .simulation.matlab_engine import get_engine


class TrimProvider(Protocol):
    def prepare_engine_failure(self, parameters: dict[str, Any]) -> dict[str, Any]: ...


class MatlabTrimProvider:
    """Call the project-local MATLAB trim entry point on demand."""

    def prepare_engine_failure(self, parameters: dict[str, Any]) -> dict[str, Any]:
        engine = get_engine()
        raw = engine.feval(
            "prepare_engine_failure_trim",
            float(parameters["initial_altitude_ft"]),
            float(parameters["initial_airspeed_ft_s"]),
            float(parameters["engine_failure_altitude_ft"]),
            float(parameters["go_around_altitude_ft"]),
            nargout=1,
        )
        result = _to_python(raw)
        if not isinstance(result, dict) or not result.get("converged"):
            message = (
                result.get("message", "配平未收敛")
                if isinstance(result, dict)
                else "MATLAB 未返回有效配平结果"
            )
            raise RuntimeError(message)
        return result


def _to_python(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _to_python(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_python(item) for item in value]
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    if hasattr(value, "_data"):
        data = [_to_python(item) for item in value._data]
        return data[0] if len(data) == 1 else data
    return value
