# 试验点2-4差动刹车纠偏

日期：2026-11-24。原生6DOF功能映射，候选协议0.4.0。初始100kn、偏差45ft、向外航向2°，超过50ft后差动刹车，目标回到30ft内；另加工程稳定保持条件。完整依据见 `docs/SCENE3_BRAKE_CORRECTION.md`。

真实Dify运行 `run-e9ca84f93122`：40次新决策，复用0次，20s；峰值58.71ft，最终−6.98ft。原文方向和偏差核心指标达成；横向速度仍−1.638m/s，稳定计时0，综合13项中11项通过。状态为 `completed_with_failures`，不可称为完整通过。

| 文件 | 内容 |
| --- | --- |
| `summary.json` | 运行核对和当前评价审计，单列原文核心指标及工程稳定性 |
| `records.json` | reset和40步状态、原始动作、实际施加动作及模型返回 |
| `decisions.json`、`decision_trace.csv` | 每步真实观测、解析动作、来源和时序 |
| `compiled_prompt.md` | 本轮实际提示词，含受保护契约和参数 |
| `trajectory.csv` | 原生模型分段采样，未平滑 |
| `correction_visualization.png/svg` | 六联结果图，标明综合未通过 |
| `figure_manifest.json`、`provenance.json` | 来源、哈希、导出变换、测试数及视觉核查 |
| `physics_probe.json` | 100kn短时模型检查及左右刹车初始偏航力矩 |
| `model_checks.json` | 无Dify的参考控制和5s零刹车检查 |

参考控制 `brake-correction-reference-41a05a20` 在19.5s满足全部13项检查；零刹车 `brake-correction-coast-71a65b42` 的偏差在5s增至63.08ft。参考控制仅用于模型测试，没有接管Dify；5s对照不用于量化20s算法收益。

JSON副本只归一化本机路径，数值保留。`summary.json` 中的描述性评价字段为当前审计补充，原始任务结果及所有门槛结果未覆盖。完整Dify响应、分段模型输出位于本机对应 `data/runs/`。82项代码/API测试通过。

0.4.0保持候选；下一步改善回收后的对正和反向制动策略，再按同一判据复验。本轮没有追加Dify试验。
