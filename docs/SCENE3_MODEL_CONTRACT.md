# 场景三模型接口与交付规范

## 1. 场景定义

场景三用于验证飞机在地面滑跑阶段的方向控制能力。本版本关注：

- 地面接触和轮胎侧向力。
- 前轮转向或经确认的等效转向机构。
- 方向舵对地面方向控制的作用。
- 航向误差、横向偏差和偏航状态输出。
- 风场接口。

本版本不实现差动刹车闭环控制。`brake_left`、`brake_right` 字段为兼容后续版本而保留，模型必须明确返回其未启用状态，不能静默当作有效控制。

## 2. 目录与文件交付

模型负责人在 `feature/scene3-model` 分支至少交付：

```text
simulink/
├── ground_direction_env.slx
├── ground_direction_reset.m
├── ground_direction_step.m
├── run_ground_direction_smoke_test.m
└── README_ground_direction.md
```

允许对文件名进行一次协商，但合并前必须冻结；后端不得依赖临时模型名或人工修改 Base Workspace。

不要提交以下生成文件：

- `slprj/`
- `*.slxc`
- 临时 `*.mat`
- 自动保存文件 `*.asv`
- 本机绝对路径配置

## 3. 坐标系和单位

- 模型内部统一使用 SI 单位。
- 地面平面采用 NED/跑道局部坐标时，必须在模型 README 中说明轴向和正方向。
- 角度输入输出统一使用 `rad`；仅前端展示层可以使用 `deg`。
- 横向偏差必须约定正方向。建议“跑道中心线右侧为正”。
- 航向误差统一归一化到 `[-pi, pi]`。
- 风向由后端转换为模型坐标分量后传入，模型入口不自行猜测气象风向约定。

## 4. 初始化接口

MATLAB 入口：

```matlab
result = ground_direction_reset(config)
```

`config` 至少包含：

| 字段 | 单位 | 必需 | 说明 |
| --- | --- | --- | --- |
| `run_id` | string | 是 | 本次运行唯一标识 |
| `initial_speed_mps` | m/s | 是 | 初始地速 |
| `initial_lateral_offset_m` | m | 是 | 相对跑道中心线偏差 |
| `initial_heading_rad` | rad | 是 | 初始航向 |
| `runway_heading_rad` | rad | 是 | 跑道方向 |
| `wind_north_mps` | m/s | 是 | 北向风速分量 |
| `wind_east_mps` | m/s | 是 | 东向风速分量 |
| `step_time_s` | s | 是 | 单步仿真时间 |
| `max_simulation_time_s` | s | 是 | 终止保护时间 |

成功返回：

```matlab
result.ok = true;
result.done = false;
result.event = "RESET";
result.model_version = "scene3-0.2.0";
result.state = struct(...);
result.capabilities = struct( ...
    'nose_wheel_steering', true, ...
    'wind', true, ...
    'differential_braking', false);
```

初始化失败时不得仅在 MATLAB 控制台打印错误；必须抛出可识别异常，或返回 `ok=false`、`error_code` 和 `message`。

## 5. 单步接口

MATLAB 入口：

```matlab
result = ground_direction_step(action)
```

`action` 字段：

| 字段 | 单位/范围 | v0.2.0 状态 | 说明 |
| --- | --- | --- | --- |
| `rudder_rad` | 模型舵面物理范围 | supported | 方向舵指令 |
| `nose_wheel_rad` | 转向机构物理范围 | supported | 前轮或等效转向指令 |
| `throttle_left` | 0–1 | supported | 左油门 |
| `throttle_right` | 0–1 | supported | 右油门 |
| `brake_left` | 0–1 | reserved | 本版不产生制动力 |
| `brake_right` | 0–1 | reserved | 本版不产生制动力 |

模型必须执行限幅，并同时返回原始动作和实际施加动作，便于后端审计。

返回的 `state` 至少包含：

| 字段 | 单位 | 说明 |
| --- | --- | --- |
| `time_s` | s | 累计仿真时间 |
| `x_m` | m | 跑道方向位置 |
| `y_m` | m | 横向位置 |
| `ground_speed_mps` | m/s | 地速 |
| `heading_rad` | rad | 当前航向 |
| `yaw_rate_radps` | rad/s | 偏航角速度 |
| `lateral_error_m` | m | 相对中心线横向偏差 |
| `heading_error_rad` | rad | 相对跑道方向误差 |
| `on_ground` | bool | 是否保持有效地面接触 |
| `flight_phase` | string | `GROUND_ROLL`、`SUCCESS` 或 `FAILED` |

完整返回至少包含：

```matlab
result.ok
result.done
result.event
result.instruction
result.state
result.raw_action
result.applied_action
result.capabilities
```

## 6. 事件与终止条件

模型至少产生以下标准事件：

- `RESET`
- `GROUND_ROLL`
- `DIRECTION_RECOVERED`
- `RUNWAY_DEVIATION_LIMIT`
- `GROUND_CONTACT_LOST`
- `TIME_LIMIT_REACHED`

默认成功条件由场景规范配置，不硬编码在模型内部。建议第一版使用“在给定持续时间内横向偏差和航向误差均回到阈值内并保持若干秒”。阈值由后端 SceneSpec 传入或由模型返回原始量后在评价器中判断。

## 7. Python 集成要求

后端将通过统一适配器把 MATLAB 返回值转换成与现有 `FlightEnv` 相同的结构：

```json
{
  "done": false,
  "event": "GROUND_ROLL",
  "instruction": "继续修正航向和横向偏差",
  "state": {},
  "applied_action": {}
}
```

模型入口不得：

- 要求人工打开模型后才能运行。
- 从 `E:\\6DOF_Airframe` 加载文件。
- 使用模型负责人的本机绝对路径。
- 通过手工修改脚本常量才能切换工况。
- 在 reset 之后丢失连续仿真状态。

## 8. 模型负责人交付说明模板

提交或合并请求中必须填写：

```text
模型版本：
MATLAB/Simulink 版本：
入口函数：
输入字段及范围：
输出字段及单位：
已实现能力：
预留但未实现能力：
默认测试工况：
测试命令：
测试结果：
已知限制：
```

## 9. 模型验收条件

- `run_ground_direction_smoke_test` 可以从全新 MATLAB 会话直接运行。
- reset 后返回字段完整且所有数值有限。
- 连续 step 不出现状态时间回退或重置。
- 正、负转向指令能够产生方向相反且可解释的响应。
- 零输入基线结果可复现。
- 超范围动作会被限幅并在 `applied_action` 中体现。
- 差动刹车明确标记为未实现。
- 运行不读取 `E:\6DOF_Airframe`。
- 模型和入口脚本通过后端真实调用测试。
