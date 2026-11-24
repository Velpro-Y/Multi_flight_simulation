# 场景三参数化实验接口

更新日期：2026-11-24。适用于场景三 `0.2.0` 和 `0.3.0` 逐步决策协议，交付分支为 `codex/scene3-ground-direction`，尚未合入 `develop`。

## 参数与调用

前端读取 `GET /api/scenarios/ground_direction/parameters` 生成表单，直接提交 `POST /api/runs`。场景三使用地面状态初始化，不调用场景一的动态配平接口。

| 参数 | 单位 | 范围 | 默认值 |
| --- | --- | --- | --- |
| `initial_speed_kn` | kn | 0～5 | 0 |
| `target_nose_wheel_deg` | ° | 20～75 | 75 |
| `target_heading_change_deg` | ° | 150～180 | 177 |
| `max_simulation_time_s` | s | 5～20 | 20 |

```json
{
  "scene_id": "ground_direction",
  "prompt_version": "0.2.0",
  "parameters": {
    "initial_speed_kn": 5,
    "target_nose_wheel_deg": 40,
    "target_heading_change_deg": 150,
    "max_simulation_time_s": 20
  }
}
```

省略参数时使用原有默认值。省略版本时选择已发布 `0.2.0`；刹车扩展仍需显式选择候选 `0.3.0`。Swagger 的 `/api/runs` 提供默认场景一、参数化场景三和刹车候选三个请求示例。

参数越界、非有限数值、未知参数、向场景一直接提交 `parameters`、向场景三提交 `preparation_id` 均返回422。向旧0.1协议提交地面参数返回409。场景二仍未启用。

## 实现与结果判定

1. 后端校验参数并写入任务。提示词按本轮初始地速、目标角、航向和时限组装，保存全文及哈希。
2. MATLAB读取 `realtime-*/configuration.json`。初始地速按 kn→m/s 转为模型初始速度；初始航向、位置和轮角固定为0，地面支承高度沿用现有模型设置。
3. 达到5kn前保持前轮0；初始5kn允许首步转向。Dify每0.5秒仿真时间重新决策，前轮指令不得超过本轮目标角；0.3协议继续受随速限角约束。
4. 达到目标航向变化且运动反向后结束。评价器另检查实际轮角达到目标、连续性、动作合法性和安全状态。模型完成不代表所有评估门槛均通过。
5. 仿真达到时限则终止；非0.5倍数的最后一步缩短至剩余时间。未完成目标的超时运行返回 `completed_with_failures`，模型不安全也会终止。

设置可在 `payload.parameters`、报告 `parameters`、`evaluation.parameters` 和实际提示词中核对。逐步观测包含本轮目标和时限，真实模型响应保留在 `response_*.json`。默认75°工况保留原 `actual_75_reached` 门槛名，其他角度使用 `target_angle_reached`。

本轮未修改 `.slx` 文件，通过运行时初始化及停止条件适配参数。场景一仍使用原有模型、配平入口和2秒控制周期。

## 验证结果

代码及API测试59项通过，覆盖两个逐步协议的参数传递、提示词组装、归档、越界拒绝、非整数时限、目标评估及实际刹车覆盖判定。使用测试决策替身，不调用Dify。

真实MATLAB测试采用固定测试输入，三组接口验证全部通过：

| 工况 | 实际结果 | 结论 |
| --- | --- | --- |
| 默认：静止、75°、目标177°、20s | 8.70s，航向177.205° | 完成并通过评估 |
| 自定义：5kn、40°、目标150°、20s | 6.31s，航向150.123° | 初始速度实际生效，完成并通过评估 |
| 刹车协议：2kn、40°、目标150°、5.25s | 5.25s，航向64.283° | 准确超时终止，评估不通过符合预期 |

三组全程接地、状态安全，实际轮角未超过本轮目标。第三组仅验证0.3协议的参数及超时，不是新增刹车作用试验。精简记录见 `resources/validation/ground_parameters_20261124/summary.json`，完整轨迹保留在对应 `data/runs/ground-parameters-*/`。

上述三组模型测试Dify调用数为0。接口范围是输入边界，尚未完成全范围工况验证。左转、初始航向/横向偏差、风场和场景二仍待后续扩展。

### 参数化真实Dify闭环

`run-8deb2c3e180a`：初始5kn、目标前轮40°、目标右转150°、时限20s，使用发布提示词0.2.0，无附加人工策略。

- 10次全新Dify决策、0次复用，仿真时长4.67s。
- 最终航向150.3436°，实际最大前轮角40°，末速度5.9002kn。
- 全程接地且状态安全，最大绝对滚转1.6204°。
- 7项场景评估通过；额外核对初始速度、参数传递、提示词全文哈希及每步调用来源，全部通过。
- Dify实际使用不同的左右油门并逐步调整前轮角；这是单次完整闭环结果，没有对称油门对照，不能据此单独量化差动推力收益。

精简报告、运行记录、决策表、轨迹表和可视化见 `resources/validation/ground_parameters_20261124/`。完整Dify响应及模型分段轨迹位于本机 `data/runs/run-8deb2c3e180a/`。本轮未验证恒速保持、稳定对正或其他参数组合的驾驶成功率。

首次尝试 `run-2a92c516e95b` 因MATLAB冷启动约101s超过90s等待上限，在决策前失败，Dify调用数0。将两种地面模型的初始化等待统一为180s后重试成功；控制周期仍为0.5s。

### 参数化手动与自动刹车闭环

`run-898e6112d853` 使用候选0.3.0，参数仍为初始5kn、前轮40°、目标右转150°、时限20s。本轮附加“实际覆盖单侧手动刹车和自动刹车”的任务要求，刹车时机、手动大小和其余动作由Dify逐步决定。

| 阶段 | 模型实际输出 | 地速变化 |
| --- | --- | --- |
| 0～0.5s：手动右刹车 | 左0、右0.35，手动模式 | 5.00→4.54kn |
| 0.5～1s：自动刹车 | 模式切换、预位及激活生效，左右各0.15 | 4.54→3.73kn |
| 1s后：释放刹车并继续转向 | 恢复手动模式、两侧刹车0 | 最终5.14kn |

11次新Dify决策、0次复用，5.09s达到150.3541°；实际前轮40°，最大绝对滚转1.2417°，全程接地且状态安全。9项场景评估和9项运行一致性/刹车覆盖核查全部通过。

左右油门在本轮保持相同。表中速度变化同时受油门和转向影响，只用于记录刹车阶段的实际响应；这组功能覆盖试验不单独量化刹车性能，也不是差动油门对照。刹车值为模型归一化指令。0.3.0继续保留候选状态。

精简交付见 `resources/validation/ground_parameters_brake_20261124/`，完整响应、提示词、决策和分段轨迹位于本机 `data/runs/run-898e6112d853/`。

## 复验

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

打开 `/docs`，在 `POST /api/runs` 选择“场景三：参数化右转”示例提交，取得编号后查询 `GET /api/runs/{run_id}` 和 `/{run_id}/report`。真实Dify实验需要先启动Dify并配置Agent。

无Dify额度消耗的真实模型测试：

```powershell
$env:PYTHONPATH="$PWD\src"
python scripts/verify_ground_parameters.py
# 单独复验自定义工况
python scripts/verify_ground_parameters.py --case custom
```

模型测试会启动并关闭独立MATLAB工作进程；运行前确认没有其他真实仿真占用模型。

真实Dify闭环（提交一次新实验，会消耗调用额度）：

```powershell
python scripts/verify_ground_parameterized_dify.py
```

只核对已有记录，不产生新决策：

```powershell
python scripts/verify_ground_parameterized_dify.py --run-id run-8deb2c3e180a
```

参数化刹车覆盖（提交一次新实验，会消耗调用额度）：

```powershell
python scripts/verify_ground_parameterized_dify.py --prompt-version 0.3.0 --require-braking
# 只核对已有刹车实验
python scripts/verify_ground_parameterized_dify.py --run-id run-898e6112d853 --require-braking
```

读取上述本机编号需要保留对应数据库及运行目录。
