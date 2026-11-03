# Multi Flight Simulation Demo

独立的多场景飞行仿真 Demo。所有运行代码、Simulink 模型、提示词、Dify 配置和回归验证都位于本项目；`E:\6DOF_Airframe` 仅作为迁移来源，不参与运行。

当前基线版本：`v0.1.0`。该版本为固定参数单发失效复飞 Demo，场景参数化和场景三地面方向控制将在后续版本中扩展。

`feature/parameterized-simulation` 分支正在开发 `v0.2.0` 场景一参数化链路，已支持参数 Schema、参数校验、MATLAB 动态配平、配平结果保存及使用 `preparation_id` 启动实验。

## 协作开发与交付

第二版在 `develop` 分支开发，目标版本为 `v0.2.0`。协作开发以以下文档为准：

- [v0.2.0 开发计划与分工](docs/DEVELOPMENT_PLAN.md)
- [前端 API 交付规范](docs/FRONTEND_API.md)
- [场景三模型接口与交付规范](docs/SCENE3_MODEL_CONTRACT.md)
- [验收与合并检查表](docs/ACCEPTANCE_CHECKLIST.md)

文档中会分别标注“v0.1.0 已实现”和“v0.2.0 计划实现”。`main` 和
`v0.1.0` 标签只保存已验证基线，尚未完成的第二版功能不得直接提交到
`main`。

## 首版范围

- 场景一“单发失效复飞”可运行：500 ft双发下降，300 ft左发失效，200 ft开始单发复飞并返回500 ft。
- 场景二“地面减速”保留接口，刹车模块暂缓。
- 场景三“地面方向控制”标记为后续扩展。
- 通过专用 Dify Agent 应用 API 完成决策。
- 用户不输入提示词；后端按场景和已发布版本自动编译并传入。
- 支持基线/候选批量运行、自动评估、回归门控和人工发布。

## 运行架构

```text
调用方 → 本项目 /api/runs
             ↓
        Dify应用API
             ↓
Multi_Flight_Simulation_Demo Agent
             ↓ 工具回调
本项目 /reset、/step
             ↓
FlightEnv → MATLAB Engine → simulink/beaver_agent_env.slx
```

## 环境准备

1. 使用已有的 Conda 环境 `simulink`。本机对应的 Python 路径为：

   ```text
   C:\Users\velpro\.conda\envs\simulink\python.exe
   ```

   该环境已包含 MATLAB Engine 和 FastAPI。需要补装或更新项目依赖时，直接调用环境内的 Python（不依赖 `conda activate`）：

   ```powershell
   & 'C:\Users\velpro\.conda\envs\simulink\python.exe' -m pip install -r requirements.txt
   ```

2. 复制 `.env.example` 为 `.env`，填入新 Dify Agent 的 App API Key。
3. 按照 [Dify配置说明](resources/dify/README.md)导入工具 Schema 和 Agent DSL。
4. 打开 MATLAB R2022a，在命令窗口执行：

   ```matlab
   matlab.engine.shareEngine
   ```

5. 启动服务：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
   ```

API 文档地址：<http://localhost:8000/docs>

参数化场景一依次调用：

```text
GET  /api/scenarios/engine_failure/parameters
POST /api/simulations/prepare
POST /api/runs
GET  /api/runs/{run_id}
```

`POST /api/simulations/prepare` 会调用 MATLAB `findop` 重新计算双发下降、单发下降和单发复飞配平。当前风场接口标记为预留，非零风速会被明确拒绝。

## 首次验证

服务启动后依次检查：

```text
GET  /health
GET  /api/scenarios
GET  /api/prompts/engine_failure/compiled
POST /api/runs
GET  /api/runs/{run_id}
```

一键实验请求：

```json
{
  "scene_id": "engine_failure"
}
```

提示词优化请求：

```json
{
  "scene_id": "engine_failure",
  "candidate_count": 2,
  "auto_publish": false
}
```

优化默认不会自动发布。通过回归的候选仍需调用发布接口，或显式将 `auto_publish` 设置为 `true` 且候选被判定为实际改善。

## 重要运行限制

- 当前 MATLAB Engine 和 Simulink 环境采用单实例串行运行。
- 同一时间只能有一个实验真正占用仿真模型。
- 后端默认只监听 `127.0.0.1:8000`；已验证 Dify Docker 可通过 `host.docker.internal:8000` 回调，无需暴露到局域网。
- `/reset` 和 `/step` 是供 Dify 工具调用的兼容接口。
- 原始 Agent 动作和增稳器实际施加动作分别记录，以便提示词回归分析。
- 真实运行产物保存在 `data/runs/<run_id>/`。
