# 场景三低速转向演示

启动后端后，在 `/docs` 调用 `POST /api/ground-direction/demo`。

```powershell
powershell -ExecutionPolicy Bypass -File E:\Multi_flight_simulation\scripts\start.ps1
```

已有后端进程需重启以加载新接口。也可从项目根目录使用命令行直接运行同一任务：

```powershell
& 'C:/Users/velpro/.conda/envs/simulink/python.exe' scripts/run_ground_demo.py --direction left
```

自动决策：

```json
{"direction":"right","initial_speed_kn":5,"duration_s":8}
```

系统自动生成提示词，通过现有 Dify 应用获取一次前轮角度，再启动独立 MATLAB 批处理运行模型。使用现有 `.env` 中的 Dify 配置。MATLAB 默认路径为 `D:/soft/MATLAB/bin/matlab.exe`，可通过 `MATLAB_EXECUTABLE` 覆盖。不要求手工共享 MATLAB 会话。

手动指定角度（跳过 Dify，仅调试模型）：

```json
{"direction":"right","nose_wheel_deg":10,"initial_speed_kn":5,"duration_s":8}
```

返回任务 `id`，通过 `GET /api/runs/{id}` 查询。终态为 `succeeded`、`completed_with_failures` 或 `failed`。结果中 `decision_source` 区分 Dify 与手动输入；`simulation` 包含航向变化、位置、滚转角、接地状态和采样轨迹；完整材料在 `data/runs/{id}/`。

输入范围：速度1～5 kn，时长1～8 s，转向角±10°，正值右转、负值左转。显式指定角度时以角度为准，direction 只用于自动决策。发动机关闭、驻车释放、无风。判据使用完整时序，要求数值有限、滚转小于10°、三轮保持接地，并产生与实际输入角度一致的方向响应。自动任务另需响应与请求方向一致。

默认入口验证一次定角转向，未接入通用 `/api/runs` 的场景三闭环。前轮使用转向输入，两侧主轮内部经零增益固定为零转角。该连接已复核，三轮不会一起转向；轮胎参数仍需真实基准数据标定。

## 实测记录

MATLAB R2022a，初始速度5 kn，时长8 s，关车、释放驻车，结果如下。

| 来源 | 角度 | 航向变化 | 横向位移 | 最大滚转 | 接地 | 判定 |
| --- | --- | --- | --- | --- | --- | --- |
| 手动输入 | +10° | +48.386° | +6.678 m | 0.386° | 三轮保持 | 通过 |
| 现有Dify Agent自动决策 | -10° | -48.406° | -6.682 m | 0.386° | 三轮保持 | 通过 |

手动任务：`ground-6793cceb9d23`；自动任务：`ground-f745f2fbe046`。自动任务保留了真实Dify响应，返回 `{"nose_wheel_deg": -10}`，任务状态为 `succeeded`。完整记录在对应的 `data/runs/` 子目录。

## 从静止加速并掉头

同一接口增加 `maneuver`：

```json
{"maneuver":"uturn","direction":"right"}
```

或使用命令行：

```powershell
& 'C:/Users/velpro/.conda/envs/simulink/python.exe' scripts/run_ground_demo.py --maneuver uturn --direction right
```

此模式固定从0速度开始、目标5 kn、最长120秒，覆盖默认的 `initial_speed_kn` 和 `duration_s`；实际工况保存在 `request.json`。Agent只选择一次转向方向及幅度（不超过10°），后端20 Hz底层控制器完成双发对称油门PI速度控制、1°/s转向变化限制与阶段转换。不实现差动推力，也不要求Agent逐步调用工具。MATLAB脚本仅临时修改内存中的模型接线，结束后不保存SLX。

阶段：静止加速→速度达到5 kn后开始转向→前轮角随剩余航向误差收小→累计航向达到177°且沿初始方向的速度分量为负时结束。177°是本次Demo的近180°判据；结束即停止仿真，未验证掉头后的稳定直线保持或刹停。全过程要求有限值、滚转小于10°、三轮保持接地。

2026年11月10日真实Dify任务 `ground-6a4fc8b7fe7f`：Agent返回+10°，30.45秒结束，累计航向177.138°，前进方向已反转，末速度5.008 kn，最大速度6.176 kn，最大滚转0.273°，三轮保持接地，通过Demo判据。速度存在启动超调，尚不能宣称全过程严格保持5 kn。轨迹、控制指令与阶段序列均在 `data/runs/{id}/result.json` 和 `simulation.json`，Agent原始响应在 `decision.json`。

该结果验证低速掉头的基础流程，不代表原文75°最大转角、正副驾驶独立控制及最大能力原地掉头要求全部通过。

## 前轮转向与差动油门组合对照

`differential_throttle` 取值0～0.1，默认0，只允许在 `uturn` 模式使用。转弯阶段降低内侧发动机油门（右转降低右油门，左转降低左油门），加速阶段保持对称；油门下限为0。

```json
{"maneuver":"uturn","direction":"right","differential_throttle":0.1}
```

2026年11月10日仅执行一组组合对照，任务 `ground-e58377183157`。为节省模型调用，显式复用基准Agent给出的+10°指令，记录来源为 `manual`，未另行调用Agent。对照基准为 `ground-6a4fc8b7fe7f`，两组均采用5 kn目标速度、1°/s转向变化限制和177°结束阈值。

| 指标 | 对称油门 | 内侧油门降低0.1 |
| --- | --- | --- |
| 总耗时 | 30.45 s | 30.25 s |
| 航向变化 | 177.138° | 177.206° |
| 轨迹前向占用 | 37.27 m | 36.67 m |
| 轨迹横向占用 | 38.46 m | 38.15 m |
| 最大速度 | 6.176 kn | 5.986 kn |
| 末速度 | 5.008 kn | 5.004 kn |
| 最大滚转 | 0.273° | 0.277° |
| 三轮接地 | 全程保持 | 全程保持 |

轨迹占用为各自保存的501个采样点的坐标范围，不是飞机外廓扫掠范围或最大能力转弯半径。组合组转弯期间实际左右油门差为0.1。耗时减少约0.66%，横向占用减少约0.81%，本次单组测试收益很小，默认仍使用对称油门，差动油门作为可选参数。尚未证明左右两侧组合掉头或大角度组合工况均有效。

完整结果及控制序列保存在组合任务目录的 `result.json`；两组比较保存在 `comparison.json`。可在项目根目录执行：

```powershell
& 'C:/Users/velpro/.conda/envs/simulink/python.exe' scripts/run_ground_demo.py --maneuver uturn --angle 10 --differential-throttle 0.1
& 'D:/soft/anaconda/python.exe' scripts/compare_ground_uturn.py --candidate ground-e58377183157
```

## 内侧零油门与外侧速度控制对照

增加 `thrust_policy: "inner_idle"`，仅用于掉头，且不能同时设置非零 `differential_throttle`。达到5 kn前仍使用对称加速；转弯期间内侧油门固定0，外侧沿用PI控制和0.4上限。默认 `thrust_policy: "offset"` 保持原行为。

```json
{"maneuver":"uturn","direction":"right","thrust_policy":"inner_idle"}
```

本模型油门0对应实际推力0；这里的 `inner_idle` 是接口策略名称，表示模型零油门近似，并不是经过标定的真实发动机慢车推力。试验结果不能直接等同真实飞机的慢车操作性能。

2026年11月10日任务 `ground-0a96dc99392c`，显式复用+10°前轮指令，没有再次调用Agent。转弯从3.85秒开始，内侧右发平均推力0 N，外侧左发平均推力320.17 N；发动机合成平均偏航力矩1120.61 N·m。平均左右油门差为0.2713，明显大于前组固定0.1。

| 指标 | 对称油门 | 固定差0.1 | 内侧零油门 |
| --- | --- | --- | --- |
| 总耗时 | 30.45 s | 30.25 s | 30.05 s |
| 采样轨迹横向占用 | 38.46 m | 38.15 m | 38.00 m |
| 航向变化 | 177.138° | 177.206° | 177.156° |
| 最大速度 | 6.176 kn | 5.986 kn | 5.833 kn |
| 末速度 | 5.008 kn | 5.004 kn | 4.997 kn |
| 最大滚转 | 0.273° | 0.277° | 0.284° |
| 三轮接地 | 全程保持 | 全程保持 | 全程保持 |

相对对称基准，内侧零油门的总耗时减少约1.31%，横向占用减少约1.19%。通过相同Demo判据，但改善仍小；当前10°前轮角、5 kn速度目标下，结果不支持“固定0.1的差值过小是效果不明显的主要原因”。没有验证保持总推力恒定的参数扫描，不能从这三组结果推广到其他转角、速度、机型或真实慢车条件。

该任务目录保存 `result.json`、带左右油门和阶段时序的 `simulation.json`、实际推进输出日志及 `comparison.json`。复现命令：

```powershell
& 'C:/Users/velpro/.conda/envs/simulink/python.exe' scripts/run_ground_demo.py --maneuver uturn --angle 10 --thrust-policy inner_idle
```
