"""Coordinated single-engine trim transition and sampled-state stabilization."""

from ..settings import GO_AROUND_TRANSITION_TIME_S, MPS_TO_FPS, STEP_TIME


def single_engine_controls(env, state, go_around=False):
    """Return bounded controls using the prepared descent and climb trims.

    Gains are validated for the two-second scene-one update interval. Actuator
    slew limits below are rates per simulated second, not engine spool rates.
    """
    clamp = env._clamp
    # Apply the first transition increment in the first go-around interval.
    blend = clamp((env.go_around_time + STEP_TIME) / GO_AROUND_TRANSITION_TIME_S, 0., 1.) if go_around else 0.
    scheduled = env._interpolate_trim(env.engine_out_descent_trim, env.engine_out_climb_trim, blend)

    # Reduced sampled-loop gain limits roll/yaw oscillations. Retain the
    # model's measured coupled lateral effectiveness and control signs.
    p_command = clamp(-.8 * (state['roll'] - scheduled['roll']), -.10, .10)
    delta_p = .7 * (p_command - state['roll_rate'])
    delta_r = .7 * -state['yaw_rate']
    delta_aileron = (-1.7955 * delta_p + 1.033 * delta_r) / 2.217
    delta_rudder = (-.5425 * delta_p - .923 * delta_r) / 2.217
    aileron = clamp(clamp(scheduled['aileron'] + delta_aileron, -.25, .25),
                    env._se_previous_aileron - .03 * STEP_TIME, env._se_previous_aileron + .03 * STEP_TIME)
    rudder = clamp(clamp(scheduled['rudder'] + delta_rudder, -.50, .15),
                   env._se_previous_rudder - .05 * STEP_TIME, env._se_previous_rudder + .05 * STEP_TIME)

    target_pitch = scheduled['pitch'] + .015 / MPS_TO_FPS * (scheduled['vertical_speed'] - state['vertical_speed'])
    # An airspeed deficit must not demand a higher nose-up pitch target.
    target_pitch -= .008 / MPS_TO_FPS * (scheduled['airspeed'] - state['airspeed'])
    target_pitch = clamp(target_pitch, .04, .21)
    q_command = clamp(.65 * (target_pitch - state['pitch']), -.08, .08)
    raw_elevator = clamp(scheduled['elevator'] - .34 * (q_command - state['pitch_rate']), -.05, .03)
    elevator = clamp(raw_elevator, env._se_previous_elevator - .006 * STEP_TIME,
                     env._se_previous_elevator + .006 * STEP_TIME)

    # Preserve low-throttle descent trim and build thrust with the six-second
    # control transition, instead of a separate slow 0.06-per-step ramp.
    raw_throttle = clamp(scheduled['throttle_right'] + .020 / MPS_TO_FPS * (scheduled['airspeed'] - state['airspeed'])
                         + .012 / MPS_TO_FPS * (scheduled['vertical_speed'] - state['vertical_speed']), 0., .78)
    throttle = clamp(raw_throttle, env._se_previous_throttle - .08 * STEP_TIME,
                     env._se_previous_throttle + .08 * STEP_TIME)
    env._se_previous_aileron, env._se_previous_rudder = aileron, rudder
    env._se_previous_elevator, env._se_previous_throttle = elevator, throttle
    return {'aileron': aileron, 'rudder': rudder, 'elevator': elevator, 'throttle_left': 0., 'throttle_right': throttle,
            'trim_blend': blend, 'target_roll': scheduled['roll'], 'target_pitch': target_pitch,
            'target_vertical_speed': scheduled['vertical_speed']}
