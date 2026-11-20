# Multi Flight Simulation 智能体接手指南

交接日期：2026-11-20。项目根目录：`E:\Multi_flight_simulation`。本指南用于继续开发、复验和交付，不需要依赖历史聊天才能启动工作。

先阅读[工作清单与交付索引](docs/PROJECT_STATUS_20261120.md)，再按本指南选择运行入口。代码、原始运行记录和当前参数约束优先于早期设计文档中的描述。

## 1. 当前交付基线

| 项目 | 当前状态 |
| --- | --- |
| 仓库 | `https://github.com/Velpro-Y/Multi_flight_simulation.git` |
| 当前交付分支 | `codex/scene3-ground-direction`，包含场景一与场景三 |
| 场景一集成分支 | `develop`，基线提交 `5b20454a5ee66ae799ce36a53b4d66382058ae32` |
| 固定参数历史版本 | `main`，提交 `80297ac6a3daf84f97c388ae7565deb94d526027`，标签 `v0.1.0` |
| 本次交付前 HEAD | `131b83f17027d0461fa03911b2df5283f8e14b7f` |
| 本次交付 | 刹车扩展、验证快照和交接文档在场景三分支一并提交，具体提交号以 `git log -1` 为准 |
| 发布提示词 | 场景一 `1.0.0`，场景三 `0.2.0` |
| 刹车扩展提示词 | 场景三 `0.3.0`，候选版本，需显式选择 |
| 场景二 | 注册为 `reserved`，完整实验流程尚未启用 |

本次未把场景三合入 `develop`，也未发布新标签。不要把 Python API 的 `0.2.0-dev`、提示词版本和 Git 标签视为同一种版本号。

2026-11-20 接手核查时，`127.0.0.1:8000/health` 与 `http://localhost` 均拒绝连接。数据库有历史 `session=running` 记录，这不代表有真实仿真正在运行。服务状态会变化，实际操作前重新检查。

## 2. 已确定的开发要求

- 所有运行代码、模型和接口留在本项目。`E:\6DOF_Airframe` 是迁移来源，不参与新项目运行。
- 最终目标为离线小模型决策，目前使用独立 Dify Agent 的应用 API。离线小模型替换还没有完成。
- 用户选择场景及实验参数，后端自动加载对应提示词。当前按场景编号和版本注册表选择，不进行自然语言任务分类或自动寻找最优提示词。
- 场景三正式实时决策须逐步请求 Dify，不复用已有决策，不以固定角度或 PI 速度控制替代这一流程。
- 场景一保留既有低层增稳器。Agent 原始动作与实际施加动作分别留存，两者可能不同。
- 场景一控制周期保持 `STEP_TIME=2.0`。曾试验的 1 秒版本已经撤销。
- 前端由其他成员负责，本项目提供 API、参数规范、结果和联调资料。
- 场景三模型由成员扩展，本项目负责接入、必要修正和验证。不要覆盖成员源模型。
- 场景二完整地面减速实验仍预留。场景三已有刹车模型，不等于场景二已经交付。
- 当前不要求刹车效率、能量、VMCG 等定量指标。右转功能通过不代表原试验文档全部科目通过。
- Dify 调用额度有限。优先检查现有记录和运行无模型调用的测试，再针对问题运行单例真实闭环，不自动启动候选批量试验。
- 最近 PPT 删除刹车内容属于汇报取舍，刹车代码与验证结果仍保留。

## 3. 目录与主要修改入口

| 位置 | 用途 |
| --- | --- |
| `src/multiflight/main.py` | FastAPI 路由与服务实例 |
| `schemas.py`、`parameter_registry.py` | 请求字段、参数范围及前端元数据 |
| `services/preparation_service.py`、`trimming.py` | 参数校验、动态配平和配平记录 |
| `services/run_service.py` | 版本选择、提示词编译、Dify 调用和运行归档 |
| `simulation/manager.py` | 统一仿真入口、原始/施加动作记录 |
| `simulation/flight_env.py`、`engine_failure_control.py`、`flight_safety.py` | 场景一状态推进、增稳和终止检查 |
| `simulation/matlab_engine.py` | 场景一共享 MATLAB Engine 连接 |
| `simulation/ground_env.py` | 历史两阶段地面流程 |
| `simulation/ground_realtime.py` | 场景三 0.2/0.3 逐步动作协议与 MATLAB 工作进程通信 |
| `simulink03/ground_realtime_worker.m` | 持续恢复模型运行点并推进地面仿真 |
| `prompts/compiler.py`、`store.py`、`candidates.py` | 模板组装、版本管理及预设候选规则 |
| `evaluation/evaluator.py`、`regression.py` | 场景评估与基线/候选门控 |
| `resources/scenes/`、`resources/prompts/` | 场景注册、提示词模板、种子版本表 |
| `resources/dify/` | Agent DSL 和兼容工具 Schema |
| `resources/validation/` | 可随仓库移交的精简结果快照 |
| `data/runs/` | 本机原始运行数据，不随 Git 提交 |

上表中省略前缀的 Python 路径均位于 `src/multiflight/`。

### 模型选择

| 流程 | 模型 |
| --- | --- |
| 场景一 | `simulink/beaver_agent_env.slx` |
| 场景三默认 0.2.0 与前期配对试验 | `simulink03/beaver_agent_env_ground_static_preserved.slx` |
| 场景三 0.3.0 刹车扩展 | `simulink03/beaver_agent_env_ground_brake.slx` |
| 成员提供的刹车源模型 | `新增差动刹车和自动刹车/beaver_agent_env_ground_autobrake_steering.slx` |

修正副本由 `simulink03/prepare_ground_brake_model.m` 生成。源模型与副本均随本次交付纳入版本管理，哈希见验证快照。尚未验证使用地面模型替换场景一模型，保持两个运行模型分别使用。

## 4. 环境和启动

本机已使用的环境：Windows、MATLAB R2022a、Conda `simulink`。Python 路径为 `C:\Users\velpro\.conda\envs\simulink\python.exe`，MATLAB 为 `D:\soft\MATLAB\bin\matlab.exe`。新机器应替换实际安装路径，并安装与 MATLAB 版本匹配的 Engine。

```powershell
Set-Location E:\Multi_flight_simulation
$env:PYTHONPATH="$PWD\src"
$env:PYTHONIOENCODING='utf-8'
& 'C:\Users\velpro\.conda\envs\simulink\python.exe' -m pytest tests -q
```

本次核查：41 项通过。测试使用替身验证代码与协议，不会证明当前 Dify、MATLAB 服务可用，也不会代替真实仿真。

按 `.env.example` 配置 `.env`。实际密钥仅留在部署机器，禁止提交或打印。Dify 默认基础地址为 `http://localhost/v1`，输入变量为 `scene_prompt`。配置说明见 [resources/dify/README.md](resources/dify/README.md)。DSL 中的 provider ID 可能需要在新 Dify 实例重新绑定，模型名称以该实例实际配置为准。

场景一运行前，在 MATLAB 执行：

```matlab
matlab.engine.shareEngine
```

另开 PowerShell 启动后端：

```powershell
Set-Location E:\Multi_flight_simulation
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

脚本默认只监听 `127.0.0.1:8000`。Swagger：`http://127.0.0.1:8000/docs`。场景一还需要 Dify 工具能回调后端；如果 Dify 在 Docker 内，确认 `host.docker.internal` 地址、实际监听地址及端口连通，不能把容器中的 `localhost` 当成 Windows 主机。

场景三 0.2/0.3 自动启动独立 MATLAB `-batch` 工作进程，不使用场景一共享 Engine。路径由 `MATLAB_EXECUTABLE` 环境变量覆盖，默认指向上述 MATLAB 安装。

只允许一轮真实仿真占用统一后端。不要在运行任务期间调用 `/reset` 或 `/api/sessions/.../reset`，也不要同时运行多个模型验证脚本。脚本和其他后端进程不共享当前进程的全局锁。

## 5. 场景一的正确调用

先获取参数规范，再同步调用配平接口。`prepare` 会在请求内执行配平，成功后直接返回 `preparation_id`，同时在数据库保存准备任务。

```json
POST /api/simulations/prepare
{
  "scene_id": "engine_failure",
  "parameters": {
    "initial_altitude_ft": 400,
    "initial_airspeed_ft_s": 140,
    "engine_failure_altitude_ft": 250,
    "go_around_altitude_ft": 150,
    "target_altitude_ft": 400,
    "wind_speed_ft_s": 0,
    "wind_direction_deg": 0,
    "max_simulation_time_s": 300
  }
}
```

```json
POST /api/runs
{
  "scene_id": "engine_failure",
  "preparation_id": "使用本机刚返回的prep编号",
  "prompt_version": null,
  "query": null
}
```

通过 `GET /api/runs/{run_id}` 轮询。终态包括 `succeeded`、`completed_with_failures`、`failed`。`GET /api/runs/{run_id}/report` 获取结果摘要，终止事件、最终高度和评估结果一起判断复飞是否完成。

`POST /api/runs` 不接收自定义 `parameters` 字段；参数必须经准备接口进入运行。省略 `preparation_id` 是固定默认参数流程。不要移植其他机器的配平编号，也不要在 Swagger 中传占位字符串 `"string"`、`"null"` 作为版本。

### 当前校验范围

| 字段 | 范围 | 默认值 |
| --- | --- | --- |
| `initial_altitude_ft` | 400～1000 ft | 500 |
| `initial_airspeed_ft_s` | 135～165 ft/s | 148.911745406824 |
| `engine_failure_altitude_ft` | 250～800 ft | 300 |
| `go_around_altitude_ft` | 100～700 ft | 200 |
| `target_altitude_ft` | 400～1500 ft | 500 |
| `max_simulation_time_s` | 60～600 s | 300 |
| `wind_speed_ft_s` | Schema 为 0～30，但准备服务只接受 0 | 0 |
| `wind_direction_deg` | 0～360°，预留且无风场作用 | 0 |

约束：初始高度 > 失效高度 > 复飞高度；目标高度 > 复飞高度。校验通过不保证配平收敛或复飞成功。135 ft/s 代表测试点未配平成功；1500 ft 目标代表工况在模型端需要 105 步，可能超出 Dify Agent 迭代预算。优先使用 `resources/validation/engine_failure_20261111/frontend_presets.json` 中 12 组参考参数。

场景一 Python 状态中高度为 ft、速度及垂速为 ft/s、姿态及角速度为 rad 和 rad/s，Simulink 内部为 SI。不要把 140 ft/s 当成 140 kn。

## 6. 场景三的正确调用

### 逐步 Dify 决策

```json
POST /api/runs
{"scene_id":"ground_direction","prompt_version":"0.2.0"}
```

后端 reset 后，每步发送当前状态给 Dify，解析一个动作 JSON，运行约 0.5 秒仿真，再取新状态。最多 40 步，最后一步可能提前终止。等待 Dify 时仿真暂停，0.5 秒指仿真时间，不是现实时间响应保证。

0.2.0 动作：`nose_wheel_deg` 为 0～75°，`throttle_left/right` 为 0～0.4。当前正式逐步协议只验证右转；未达到 5 kn 前不允许转向。运行以航向变化达到 177°且运动反向为完成条件，评价器另查实际最大轮角达到约 75°及接地/姿态等条件。没有完成稳定对正或全程 5 kn 恒速验收。

### 刹车扩展

```json
POST /api/runs
{"scene_id":"ground_direction","prompt_version":"0.3.0"}
```

0.3.0 增加 `brake_left/right`（0～1）、`brake_system_mode`（0 手动，1 自动）、`auto_brake_armed`（布尔）。自动模式下两侧手动输入须为 0，预位且接地后实际两侧输出各 0.15。随速前轮限角为低速 75°、高速 6°，5 kn 对应约 72.81°。实际角受 30°/s 作动限制。

完整字段定义用 `GET /api/ground-direction/action-schemas` 查询。`resources/scenes/ground_direction.yaml` 中的通用 `action_fields` 仍保留旧字段，不能代替逐步协议。`/api/sessions`、旧 `/step` 和地面 Demo 仍用于兼容调试，不是 0.2/0.3 的自动逐步入口。

未附加专项要求时，Dify 可能不使用刹车或差动油门，不能仅凭流程完成就声称这些功能被实际触发。验证刹车覆盖使用 `scripts/verify_ground_brake_dify.py`，它提交附带专项要求的一次全新运行，并保存 `brake_coverage.json`。

`replay_decisions_file` 和历史恢复脚本仅用于诊断。用户要求的完整流程不得复用历史决策；报告中检查 `model_calls` 与 `reused_decisions=0`。

## 7. 结果读取和复验

优先检查归档结果，确认问题后才调用模型：

```powershell
# 无Dify、无MATLAB仿真的现有自动测试
python -m pytest tests -q

# 无Dify，运行真实MATLAB连续步进，检查刹车协议
python scripts/verify_ground_brake_protocol.py

# 后端和Dify已启动后，运行一次真实专项闭环，会消耗模型调用
python scripts/verify_ground_brake_dify.py

# 只对已有数据作图或导出，不调用Dify
python scripts/plot_ground_brake.py --run-id run-d38f47576572
python scripts/export_ground_realtime.py --run-id run-d38f47576572
```

绘图使用 `requirements-analysis.txt`，本机也使用过 `D:\soft\anaconda\python.exe`。上述脚本的历史运行编号只在已有数据的本机有效。新机器改用新产生的运行编号。

刹车模型 11 工况复验会重新生成修正副本，应在模型未打开、无其他仿真时运行并使用新的结果目录：

```matlab
addpath('E:/Multi_flight_simulation/simulink03');
verify_ground_brake_model('E:/Multi_flight_simulation/data/runs/brake-recheck');
```

旧 `scripts/verify_ground_pipeline.py` 在后端缺失时会自动监听 `0.0.0.0`。建议先用 `start.ps1` 启动本机服务，或直接通过 API 提交任务，避免不必要地改变监听范围。

### 结果文件

- `compiled_prompt.md`：本轮实际提示词。`GET /api/prompts/.../compiled` 未接入准备记录，只能查看默认参数编译结果，不能替代本轮文件。
- `records.json`：reset 与每步 `state_before`、`raw_action`、`applied_action`、`result`。
- `evaluation.json`：门槛、失败标签和完成条件。`completed_with_failures` 不等于全部通过。
- `dify_result.json`：完整 Agent 结果或逐步决策次数摘要。
- `decisions.json`、`dify_response_*.json`：场景三逐步输入、动作、来源与原始响应。
- `realtime-*/response_*.json`：连续分段轨迹和实际模型输出，`matlab.log` 为工作进程日志。
- `records.partial.json`：失败时已完成部分，不能冒充完整实验。

场景三状态使用 kn、m、deg、deg/s，与场景一单位不同。刹车曲线是模型最终归一化指令，不是实测制动力；差动油门配对实验是固定策略模型试验，不是 Dify 自主驾驶实验。

## 8. 尚待继续的工作

| 事项 | 接手时的处理 |
| --- | --- |
| 场景三集成到 develop | 当前只推送场景三分支，按用户后续指令再合并 |
| 场景二完整地面减速 | 基于已有刹车模型评估并设计独立场景、参数、阶段和评价器，不能仅改状态为 enabled |
| 场景三参数化、左转与其他原始科目 | 按实验要求逐项扩展；当前右转和有限工况结果不能外推 |
| 提示词自动优化 | 有预设候选、比较和发布基础流程，有历史试验；继续做多工况、多次重复与跨场景验证 |
| 离线小模型 | 尚未训练部署和替换 Dify，需确定统一决策适配与数据使用方式 |
| 前端集成 | 按公开 API 对接，由前端成员实施 |

接手后先确认用户当前目标，选择一个最小可验证改动。不得因为历史计划包含某项工作就自行启动大量 Dify 试验或发布提示词。

## 9. 可直接交给下一智能体的任务开场

> 请接手 E:\Multi_flight_simulation。先阅读 AGENT_HANDOFF.md、docs/PROJECT_STATUS_20261120.md 和相关验证快照，再检查当前分支、工作区与服务状态。场景一使用独立飞行模型，场景三在 codex/scene3-ground-direction；0.2.0 为三字段逐步 Dify 决策，0.3.0 为显式选择的刹车候选。保持场景一 2 秒周期，场景三完整流程每步全新调用，不复用决策。先使用已有记录与无模型调用测试，明确当前任务后继续开发。不要自动合并 develop、发布候选、提交密钥或把历史固定策略试验称为 Dify 闭环。
