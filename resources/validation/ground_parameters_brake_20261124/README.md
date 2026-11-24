# 参数化刹车闭环验证

日期：2026-11-24。运行 `run-898e6112d853`，候选提示词0.3.0。初始5kn、前轮目标40°、航向目标150°、时限20s。附加任务为实际覆盖单侧手动及自动刹车，时机和手动大小由Dify决策。

| 验证 | 结果 |
| --- | --- |
| 真实Dify调用 | 11次，复用0次 |
| 手动刹车 | 0～0.5s，左0、右0.35 |
| 自动刹车 | 0.5～1s，已预位并激活，实际左右各0.15 |
| 任务完成 | 5.09s，航向150.3541°，实际前轮40° |
| 状态 | 全程接地、状态安全，最大绝对滚转1.2417°，末速度5.1382kn |
| 自动核查 | 9项场景评估、9项运行一致性和实际刹车覆盖核查通过 |
| 代码测试 | 59项通过，不调用Dify或真实模型 |

`summary.json` 是运行和覆盖报告；`records.json`、`decisions.json`、`decision_trace.csv` 是逐步状态/动作；`compiled_prompt.md` 是实际提示词。`trajectory.csv` 保留模型分段采样，`brake_visualization.png/svg` 是结果图，`figure_manifest.json` 记录绘图来源与视觉检查，`provenance.json` 记录任务要求、文件哈希和代码来源。

本轮左右油门相同。速度变化同时受到油门、刹车和转向影响；本例验证参数化刹车闭环功能，没有对照实验，不单独量化刹车或差动油门收益。0.3.0仍为候选，场景三尚未合入develop。

原始Dify响应和连续模型输出位于本机 `data/runs/run-898e6112d853/`。JSON副本仅将本机项目绝对路径改为相对路径；数值未变。源SVG行末空格已清理，坐标未变。

核对已有实验（不会新增决策）：

```powershell
python scripts/verify_ground_parameterized_dify.py --run-id run-898e6112d853 --require-braking
```

启动同参数的新实验：

```powershell
python scripts/verify_ground_parameterized_dify.py --prompt-version 0.3.0 --require-braking
```
