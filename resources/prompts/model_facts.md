# 受保护的模型事实

以下内容来自 Simulink 小扰动试验与配平结果，禁止修改或反转。

## 控制符号

- 正副翼产生负滚转角速度，负副翼产生正滚转角速度。
- 正方向舵产生负偏航角速度并伴随负滚转角速度。
- 负方向舵产生正偏航角速度并伴随正滚转角速度。
- 正升降舵压低机头，负升降舵抬高机头。
- `yaw_rate > 0` 时，方向舵必须更正或减小负值幅度，禁止继续增大负方向舵。

## 双发下降配平

- `vertical_speed=-9.84252 ft/s`
- `airspeed=148.91175 ft/s`
- `roll=0.01362 rad`
- `pitch=0.06476 rad`
- `aileron=0.00203`
- `elevator=-0.01097`
- `rudder=-0.03744`
- `throttle_left=0.16863`
- `throttle_right=0.16863`

## 单发下降配平

- `vertical_speed=-9.84252 ft/s`
- `airspeed=148.91175 ft/s`
- `roll=0.01757 rad`
- `pitch=0.06476 rad`
- `aileron=0.00082`
- `elevator=-0.01096`
- `rudder=-0.05206`
- `throttle_left=0.0`
- `throttle_right=0.20722`

## 单发复飞配平

- `vertical_speed=4.92126 ft/s`
- `airspeed=148.95013 ft/s`
- `roll=0.08484 rad`
- `pitch=0.16230 rad`
- `aileron=-0.01955`
- `elevator=-0.00965`
- `rudder=-0.29909`
- `throttle_left=0.0`
- `throttle_right=0.61470`

左发失效后，环境内部低层增稳器会接管配平附近的高频稳定控制。你负责阶段判断和合理的高层控制指令，不得用大幅控制量与增稳器对抗。

