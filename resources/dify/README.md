# Dify Agent 配置

## 推荐导入顺序

1. 在 Dify 的“工具”中导入 `tool-schema.yml`，工具服务地址保持为
   `http://host.docker.internal:8000`。
2. 导入 `Multi_Flight_Simulation_Demo.yml` 创建新 Agent。
3. 确认 Agent 使用 `deepseek-v4-flash`、Function Calling 和 99 次最大迭代。
4. 确认应用输入中存在 `scene_prompt`。
5. 确认 Agent 已选择 `reset_simulation` 和 `step_simulation` 两个工具。
6. 发布应用，在“访问 API”中创建该应用自己的 API Key。

DSL 中的工具 provider ID 来自当前这台 Dify 实例。若导入后显示工具失效，删除失效工具，选择刚导入的 Multi Flight Simulation Tool 中的同名两个工具即可；这不会影响提示词变量和其他 Agent 配置。

API Key 只写入项目根目录 `.env`：

```env
DIFY_BASE_URL=http://localhost/v1
DIFY_API_KEY=app-xxxxxxxx
```

不要将真实密钥写入 DSL、提交到版本库或发送到聊天中。

