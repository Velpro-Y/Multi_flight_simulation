# 场景三参数化验证交付

日期：2026-11-24。运行方式与参数范围见 `docs/SCENE3_PARAMETERIZATION.md`。

| 文件 | 内容 |
| --- | --- |
| `summary.json` | 三组固定输入的真实模型验证：默认、自定义和非整数时限；Dify调用数0 |
| `dify_validation.json` | 参数化真实Dify运行、初始化失败尝试、文件来源及哈希 |
| `dify_run_summary.json` | 运行参数、7项额外一致性核查、场景评估与末状态 |
| `dify_compiled_prompt.md` | 本轮实际加载的提示词 |
| `dify_records.json` | reset及逐步观测、原始动作、实际施加动作和模型返回值 |
| `dify_decisions.json` | 10次观测、解析动作与决策来源；完整API响应留在本机 |
| `dify_decision_trace.csv` | 按步对照决策输入、动作和末状态 |
| `dify_realtime_trajectory.csv` | 模型原生采样轨迹，含分段编号 |
| `dify_realtime_visualization.png`、`.svg` | 六联结果图 |
| `dify_realtime_visualization_manifest.json` | 绘图来源、变换和视觉核查记录 |

真实Dify运行编号 `run-8deb2c3e180a`：初始5kn、前轮40°、目标右转150°；10次新请求，无复用，4.67s完成，最终150.3436°，7项场景评估通过。模型直连的自定义工况采用另一套固定输入，结果不能与本轮直接作为算法性能对照。

首次 `run-2a92c516e95b` 在MATLAB初始化等待阶段超时，无Dify调用；初始化等待统一为180s后完成上述运行。JSON交付副本将本机项目绝对路径改为相对路径，所有数值保留；原始响应和分段轨迹仍在本机对应 `data/runs/`。

58项代码与API测试通过。0.3.0的参数传递有代码和真实模型验证，本轮真实Dify采用0.2.0；尚未遍历其他参数组合。

后续同日完成0.3.0参数化手动/自动刹车真实闭环，精简交付见 `resources/validation/ground_parameters_brake_20261124/`；当前代码测试59项通过。本目录保留前序0.2.0及模型验证记录。
