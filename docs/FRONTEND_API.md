# 前端 API 交付规范

## 1. 使用原则

- 前端只访问本项目 FastAPI 服务，例如 `http://127.0.0.1:8000`。
- 前端不得直接访问 Dify、MATLAB Engine 或 Simulink。
- Dify API Key 仅保存在后端 `.env`。
- 前端不填写、编辑或保存提示词；后端按 `scene_id` 自动加载已发布版本。
- 所有运行和配平都是异步或可能耗时操作，前端必须展示状态和失败原因。

交互文档地址：`GET /docs`。

## 2. v0.1.0 已实现接口

以下接口当前已经存在，可以用于前端联调基线。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/health` | 服务、Dify 配置和仿真状态 |
| GET | `/api/scenarios` | 查询三个场景及其可用状态 |
| GET | `/api/scenarios/{scene_id}` | 查询单个场景规范 |
| POST | `/api/runs` | 使用固定参数启动实验 |
| GET | `/api/runs?limit=20` | 查询最近实验 |
| GET | `/api/runs/{run_id}` | 查询实验状态和结果 |
| GET | `/api/runs/{run_id}/report` | 查询已完成实验报告 |
| POST | `/api/optimization/jobs` | 启动离线提示词优化任务 |
| GET | `/api/optimization/jobs/{job_id}` | 查询优化任务 |

当前启动实验请求：

```json
{
  "scene_id": "engine_failure",
  "prompt_version": null,
  "query": null
}
```

`prompt_version=null` 表示自动使用已发布版本；`query=null` 表示使用后端内置的一键实验指令。正式前端一般只传 `scene_id`。

任务通用返回结构：

```json
{
  "id": "run-0123456789ab",
  "kind": "run",
  "status": "queued",
  "progress": 0.0,
  "message": "等待执行",
  "payload": {
    "scene_id": "engine_failure",
    "prompt_version": null,
    "query": null
  },
  "result": null,
  "error": null,
  "created_at": "2026-10-30T00:00:00+00:00",
  "updated_at": "2026-10-30T00:00:00+00:00"
}
```

可能出现的运行状态：`queued`、`running`、`succeeded`、`completed_with_failures`、`failed`。

## 3. v0.2.0 参数化接口

本节接口已在 `feature/parameterized-simulation` 分支实现，合并到 `develop` 后作为第二版前端联调接口。字段调整必须同步修改本文档和后端测试。

### 3.1 查询场景参数 Schema

```http
GET /api/scenarios/{scene_id}/parameters
```

前端根据返回内容生成表单，不要在页面中硬编码不同场景的字段。

示例响应：

```json
{
  "scene_id": "engine_failure",
  "schema_version": "0.2.0-draft.1",
  "runnable": true,
  "groups": [
    {
      "id": "initial_state",
      "label": "初始状态",
      "fields": [
        {
          "name": "initial_altitude_ft",
          "label": "初始高度",
          "type": "number",
          "unit": "ft",
          "default": 500.0,
          "minimum": 400.0,
          "maximum": 1000.0,
          "required": true,
          "capability": "supported"
        }
      ]
    }
  ],
  "constraints": [
    "initial_altitude_ft > engine_failure_altitude_ft",
    "engine_failure_altitude_ft > go_around_altitude_ft",
    "target_altitude_ft > go_around_altitude_ft"
  ]
}
```

`capability` 取值：

- `supported`：允许编辑并会真实作用于模型。
- `fixed`：显示但不允许编辑。
- `reserved`：接口已预留，但当前模型未实现；前端应禁用并显示原因。

### 3.2 场景一首批参数

建议首批开放范围以现有 45 m/s 配平点附近为主，不把接口范围误当成飞机完整飞行包线。

| 字段 | 单位 | 默认值 | v0.2.0 初始范围 | 说明 |
| --- | --- | ---: | ---: | --- |
| `initial_altitude_ft` | ft | 500 | 400–1000 | 初始状态和配平高度 |
| `initial_airspeed_ft_s` | ft/s | 148.91 | 135–165 | 初始真空速，参与配平 |
| `engine_failure_altitude_ft` | ft | 300 | 250–800 | 左发失效触发高度 |
| `go_around_altitude_ft` | ft | 200 | 100–700 | 复飞触发高度 |
| `target_altitude_ft` | ft | 500 | 400–1500 | 完成判据高度 |
| `wind_speed_ft_s` | ft/s | 0 | 0–30 | 仅在模型提供真实风场端口后标记 `supported` |
| `wind_direction_deg` | deg | 0 | 0–360 | 气象风向；0 表示北风，需由后端转换为模型坐标 |
| `max_simulation_time_s` | s | 300 | 60–600 | 仿真保护上限，不参与配平 |

参数关系：

```text
initial_altitude_ft > engine_failure_altitude_ft
engine_failure_altitude_ft > go_around_altitude_ft > 0
target_altitude_ft > go_around_altitude_ft
```

只有初始飞行条件和会改变稳态气动工况的环境参数参与初始配平。失效高度、复飞高度、目标高度和最长仿真时间属于事件或终止条件，不分别配平。

若真实风场端口尚未交付，后端只能接受 `wind_speed_ft_s=0`，不得接收非零风速后静默忽略。

### 3.3 校验并配平

```http
POST /api/simulations/prepare
```

请求：

```json
{
  "scene_id": "engine_failure",
  "parameters": {
    "initial_altitude_ft": 600.0,
    "initial_airspeed_ft_s": 150.0,
    "engine_failure_altitude_ft": 350.0,
    "go_around_altitude_ft": 220.0,
    "target_altitude_ft": 600.0,
    "wind_speed_ft_s": 0.0,
    "wind_direction_deg": 0.0,
    "max_simulation_time_s": 300.0
  }
}
```

成功响应：

```json
{
  "preparation_id": "prep-0123456789ab",
  "scene_id": "engine_failure",
  "status": "ready",
  "schema_version": "0.2.0-draft.1",
  "normalized_parameters": {},
  "validation": {
    "valid": true,
    "errors": [],
    "warnings": []
  },
  "trim": {
    "converged": true,
    "solver": "findop",
    "model_version": "beaver_agent_env-runtime-trim-v1",
    "message": "三组配平均满足约束",
    "initial_state": {},
    "profiles": {
      "twin_descent": {},
      "engine_out_descent": {},
      "engine_out_climb": {}
    }
  }
}
```

配平记录可通过以下接口查询：

```http
GET /api/simulations/preparations/{preparation_id}
```

失败响应使用 HTTP `422`（参数非法）或 `409`（参数合法但当前模型能力不支持/配平不收敛）：

```json
{
  "detail": {
    "code": "TRIM_NOT_CONVERGED",
    "message": "给定初始状态无法获得可接受的配平结果",
    "field_errors": [],
    "retryable": false
  }
}
```

### 3.4 使用配平结果启动实验

```http
POST /api/runs
```

第二版请求：

```json
{
  "scene_id": "engine_failure",
  "preparation_id": "prep-0123456789ab",
  "prompt_version": null
}
```

后端必须检查：

- `preparation_id` 存在且状态为 `ready`。
- 配平结果属于同一个 `scene_id`。
- 参数 Schema、模型和配平结果没有过期。
- 当前场景状态为 `enabled`。

响应仍使用现有任务结构，前端取得 `id` 后轮询：

```http
GET /api/runs/{run_id}
```

推荐轮询间隔为 1–2 秒；状态进入 `succeeded`、`completed_with_failures` 或 `failed` 后停止轮询。

### 3.5 场景三参数

场景三至少向前端暴露：

- 初始地速
- 初始横向偏差
- 初始航向偏差
- 跑道方向
- 风速和风向（模型支持后启用）
- 仿真时长

动作参数不由普通前端用户逐步输入，而由离线决策模型通过后端工具接口产生。差动刹车字段保留但必须标记为 `reserved`。

## 4. HTTP 状态和错误处理

| 状态码 | 含义 | 前端处理 |
| --- | --- | --- |
| 200/201/202 | 成功、已创建或已接受 | 展示数据或进入轮询 |
| 404 | 场景、配平或任务不存在 | 返回选择页并提示数据已失效 |
| 409 | 场景不可运行、配平失败或资源冲突 | 展示后端 `code` 和 `message` |
| 422 | 参数格式、范围或关系非法 | 将 `field_errors` 映射到表单 |
| 503 | MATLAB/Simulink/Dify 暂不可用 | 提示检查服务，可允许重试 |

前端不得只显示“请求失败”，必须显示后端返回的 `message`；但不得向最终用户展示 API Key、堆栈或本机敏感路径。

## 5. 前端演示流程

1. 调用 `/health` 检查服务。
2. 调用 `/api/scenarios` 展示三个场景及状态。
3. 选择场景一，读取参数 Schema 并生成表单。
4. 提交 `/api/simulations/prepare`，展示校验和配平结果。
5. 使用 `preparation_id` 调用 `/api/runs`。
6. 轮询任务并展示当前阶段、进度和最终评价。
7. 场景二显示“接口保留，刹车模块暂缓”。
8. 场景三在模型未通过验收前显示“开发中”，不得伪造可运行结果。
