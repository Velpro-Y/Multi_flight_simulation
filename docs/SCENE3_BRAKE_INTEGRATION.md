# 场景三刹车模型集成与验证

日期：2026-11-16；分支：`codex/scene3-ground-direction`。

## 模型接入

运行模型为 `simulink03/beaver_agent_env_ground_brake.slx`，由成员提供的 `新增差动刹车和自动刹车/beaver_agent_env_ground_autobrake_steering.slx` 生成。原文件保持不变。

修正了 `GroundContactTireSteering/BrakeSystemSelector` 中左右两路 Switch 的数据端接线。控制条件为自动模式时，第一数据端应接自动刹车需求，第三数据端接手动/差动刹车需求；原接线顺序相反。

模型保留随速前轮限角和接地自动刹车逻辑。Dify 逐步控制左右油门、前轮目标角、左右主轮刹车、刹车模式及自动刹车预位。模型内部跑道偏差 PD 控制器设为手动输入模式，左右刹车输入直接来自本轮 Agent 决策。

## 接口

`POST /api/runs` 启动完整 Dify 闭环：

```json
{
  "scene_id": "ground_direction",
  "prompt_version": "0.3.0"
}
```

通过 `GET /api/runs/{run_id}` 查询进度，`GET /api/runs/{run_id}/report` 获取评估及数据路径。`GET /api/ground-direction/action-schemas` 返回两个协议版本的动作定义。

`0.3.0` 为刹车扩展候选版本，需要显式指定；当前发布版本仍为 `0.2.0`。省略版本会使用已发布版本。上述请求中的 `query` 可选，用于附加本轮实验要求。

Agent 每次输出以下七个字段：

| 字段 | 含义及范围 |
| --- | --- |
| `nose_wheel_deg` | 前轮目标角，0～75°，正值右转 |
| `throttle_left`、`throttle_right` | 左右油门，0～0.4 |
| `brake_left`、`brake_right` | 左右手动主轮刹车，0～1 |
| `brake_system_mode` | 0：手动/差动；1：自动 |
| `auto_brake_armed` | 自动刹车预位，布尔值 |

自动模式下左右手动刹车指令须为 0；预位且接地后，模型输出左右各 0.15。实际前轮角受 30°/s 作动速率和随速限角约束：速度不高于 2 m/s 时限角 75°，不低于 20 m/s 时限角 6°，中间线性变化；5 kn 对应约 72.81°。

每步推进约 0.5 s 仿真时间，Agent 读取最新速度、航向、轮角和位置后重新决策。观测增加实际左右刹车、模式、预位、自动激活状态、当前转角上限，以及累计标记 `manual_brake_used`、`auto_brake_used`。记录中分别保存原始动作、施加动作和模型响应；自动模式施加动作中的左右刹车记录为实际输出。

## 验证结果

| 验证 | 结果 |
| --- | --- |
| 模型直接验证 | 11 个工况，12 项检查全部通过 |
| 后端—MATLAB 连续步进 | 11 步、5.5 s，8 项检查全部通过，无 Dify 调用 |
| Dify 常规掉头 | 17 次独立调用，8.12 s，航向变化 177.10°，9 项检查通过；本轮未使用刹车 |
| Dify 刹车专项并掉头 | 18 次独立调用，8.91 s，航向变化 177.32°，实际轮角达到 75°，9 项检查通过；手动右刹车及自动刹车均实际触发 |

模型验证覆盖左右单侧刹车、自动刹车与手动输入互斥、解除预位、接地触发、三档速度限角及左右转向。单侧 0.2 刹车在测试初始时刻分别产生约 −839.24、+839.24 N·m 偏航力矩；接地自动刹车输出左右各 0.15。0.5 s 后自然滑行速度为 2.496 m/s，自动刹车为 2.233 m/s。

专项任务要求先达到 5 kn，再依据状态使用一次右刹车和自动刹车，释放后完成右转。各步动作由 Dify 根据实际反馈生成，复用次数为 0。终止判断为航向变化达到 177°且运动反向，属于本轮功能验证条件。

专项运行编号：`run-d38f47576572`。原始数据位于 `data/runs/run-d38f47576572/`：

- `compiled_prompt.md`：本轮实际提示词。
- `dify_response_*.json`、`decisions.json`：逐次原始响应、决策及输入观测。
- `records.json`：仿真重置、原始动作、施加动作和反馈。
- `realtime-*/response_*.json`：各步模型响应及轨迹采样。
- `evaluation.json`、`brake_coverage.json`：通用检查及刹车使用覆盖结果。
- `decision_trace.csv`：逐步决策与状态对照表。

精简验证快照归档于 `resources/validation/ground_brake_20261116/`。完整仿真数据保留在本地 `data/runs/`，不随代码提交。

## 复测

在项目根目录、`simulink` 环境运行：

```powershell
$env:PYTHONPATH="$PWD\src"

# 模型物理验证：会从成员源文件重新生成修正副本
matlab -batch "addpath('simulink03'); verify_ground_brake_model('data/runs/ground-brake-recheck')"

# 后端—MATLAB 接口验证，不调用 Dify
python scripts/verify_ground_brake_protocol.py

# 后端与 Dify 已启动后，提交一次完整专项闭环
python scripts/verify_ground_brake_dify.py
```

首轮专项运行因 Dify 在 JSON 前附带说明文字而中断。现已支持从响应中提取一个明确动作对象，并保留原始响应；多个动作或越界字段仍会拒绝。修改后专项重试通过。

本次完成模型功能和场景三链路验证。场景一继续使用原模型；场景二完整地面减速实验尚未接入。当前结果不代表真实飞机性能标定或全部试验科目验收。
