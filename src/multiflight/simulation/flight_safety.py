"""Scene-one termination checks against the registered safety limits."""

import math


def state_limit_reason(state, safety):
    try:
        altitude, airspeed, roll, pitch = (
            float(state[k]) for k in ('altitude', 'airspeed', 'roll', 'pitch')
        )
    except (KeyError, TypeError, ValueError):
        return 'INVALID_STATE'
    if not all(math.isfinite(v) for v in (altitude, airspeed, roll, pitch)):
        return 'INVALID_STATE'
    if altitude <= 0:
        return 'GROUND_CONTACT'
    if ((safety.min_airspeed_ft_s is not None and airspeed < safety.min_airspeed_ft_s)
            or (safety.max_airspeed_ft_s is not None and airspeed > safety.max_airspeed_ft_s)):
        return 'AIRSPEED_LIMIT'
    if safety.max_abs_roll_rad is not None and abs(roll) > safety.max_abs_roll_rad:
        return 'ROLL_LIMIT'
    if ((safety.min_pitch_rad is not None and pitch < safety.min_pitch_rad)
            or (safety.max_pitch_rad is not None and pitch > safety.max_pitch_rad)):
        return 'PITCH_LIMIT'
    return None
