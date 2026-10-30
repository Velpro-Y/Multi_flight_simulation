# 场景：单发失效复飞

完整实验流程：从 {{initial_altitude_ft}} ft 双发稳定下降；{{engine_failure_altitude_ft}} ft 左发动机失效后继续单发下降；只有到达 {{go_around_altitude_ft}} ft 才开始单发复飞；最终爬升到 {{target_altitude_ft}} ft。

阶段判断必须以工具返回的 `flight_phase` 和 `event` 为准。

## TWIN_DESCENT

- 目标：从 {{initial_altitude_ft}} ft 稳定下降到 {{engine_failure_altitude_ft}} ft。
- 使用双发下降配平附近的绝对控制量。
- `left_engine_fail=false`。
- 收到 `LEFT_ENGINE_FAILURE` 后立即切换到单发下降规则。

## ENGINE_OUT_DESCENT

- 左油门永久保持 0。
- 使用单发下降配平附近的控制量。
- 继续稳定下降到 {{go_around_altitude_ft}} ft。
- 本阶段明确禁止使用单发爬升配平，禁止提前复飞。
- 只有收到 `GO_AROUND_INITIATED` 或 `flight_phase=GO_AROUND` 才能进入复飞阶段。

## GO_AROUND

- 左油门保持 0。
- 使用单发复飞配平附近的控制量。
- 环境会在 6 秒内从单发下降配平平滑过渡到单发爬升配平，开始阶段禁止跳变到极端控制量。
- `roll=0.08484 rad` 是必要的稳定右倾，不得强制控制为 0。
- 以约 +4.92 ft/s 爬升，直到工具返回成功。

## 通用修正优先级

1. 抑制滚转角速度和偏航角速度；
2. 防止失速、过大滚转和俯冲；
3. 控制垂直速度；
4. 控制高度。

状态正在返回目标时必须减小修正。正常状态优先保持当前阶段配平，不要回到全零舵量。

