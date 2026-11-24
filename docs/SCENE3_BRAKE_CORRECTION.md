# 场景三差动刹车纠偏试验

日期：2026-11-24。对应《场景规范文档》场景三表8试验点2-4及表15操作程序。交付在 `codex/scene3-ground-direction`，提示词0.4.0为候选，未发布。

## 试验依据和配置

原文要求100kn地面滑跑，偏离跑道中线大于50ft后实施差动刹车，方向变化趋势正确，最终偏差不超过30ft。当前使用原生6DOF飞机，质量约2288.231kg、重心及机轮几何沿用现有模型；不套用原文46.9t及12%重心。因此本例是该试验点在当前模型中的功能映射。

默认从45ft横向偏差、向外2°航向、100kn开始自然滑跑，使模型实际跨越50ft阈值。跑道中线Ye=0，无风。前轮固定0，左右油门相同，自动刹车关闭；纠偏执行量为左右手动刹车差。

原文的方向及30ft指标单独记录在 `document_core_indicators`。为检查“稳定后结束”，本项目另外设置工程检查：偏差回到±30ft，航向误差≤3°、偏航率≤1°/s、横向速度≤0.75m/s，连续保持1s。后四项数值是本次实现的稳定性条件，不是原文给出的量化指标。综合评估同时检查这些条件；本轮仿真时限20s。

## 接口和执行流程

```http
GET /api/scenarios/ground_direction/parameters?experiment=brake_correction
GET /api/ground-direction/action-schemas
POST /api/runs
```

```json
{
  "scene_id": "ground_direction",
  "prompt_version": "0.4.0",
  "parameters": {
    "experiment": "brake_correction",
    "initial_speed_kn": 100,
    "initial_lateral_deviation_ft": 45,
    "initial_heading_deg": 2,
    "max_simulation_time_s": 20
  }
}
```

初始地速固定100kn；初始偏差范围±80ft，航向范围±5°，仿真时限5～20s。只有上述默认工况进行了真实Dify试验。省略版本仍使用已发布0.2.0转向流程，纠偏需显式选择0.4.0。

运行顺序：模型初始化 → 监测偏差 → 实际超过50ft后触发 → Dify每0.5s决定一次左右刹车 → 根据偏差、横向速度、航向和偏航率继续纠偏 → 回收并稳定保持或超时/不安全终止。

0.4动作仍使用七字段JSON。前轮必须0，左右油门必须相同，刹车模式必须手动且不得预位自动刹车。尚未触发时两侧刹车必须0。原始动作、实际刹车输出、状态和连续模型响应全部保存。

## 验证结果

| 验证 | 结果 |
| --- | --- |
| 100kn短时物理检查 | 初始速度和横向位置实际生效，持续接地；左、右单侧0.1刹车的初始偏航力矩分别约−419.62、+419.62N·m |
| 模型参考控制 | `brake-correction-reference-41a05a20`，39步、19.5s，最终偏差−0.80ft，稳定1.077s，13项综合检查通过；Dify调用0 |
| 5s零刹车检查 | `brake-correction-coast-71a65b42`，偏差45→63.08ft，未回收；Dify调用0 |
| 真实Dify闭环 | `run-e9ca84f93122`，40次新决策、0次复用；峰值58.71ft，20s末偏差−6.98ft，13项检查中11项通过，综合未通过 |

Dify本轮正确等待50ft触发并使用差动刹车，前轮0、左右油门一致、自动刹车关闭。状态连续、全程接地且安全，最大绝对滚转0.350°，末速度61.87kn。

约13s时偏差已回到30ft以内，但随后左右刹车交替，未及时将航向对正。结束时航向−2.951°、偏航率−0.095°/s、横向速度−1.638m/s，稳定计时0。原文方向和偏差核心指标达成，但工程稳定保持及完成门槛未通过，状态为 `completed_with_failures`。本轮不称为完整验收通过。

参考控制仅用于模型直连测试，没有接管Dify动作。5s零刹车检查只证明初期偏差仍在扩大，不作为20s算法收益对照。下一步是改善回收阶段的预测与反向制动策略，复验前不发布0.4.0。本轮不再追加模型调用。

## 复验和数据

```powershell
$env:PYTHONPATH="$PWD\src"
# 零Dify的参考控制或零刹车检查
python scripts/verify_brake_correction_model.py
python scripts/verify_brake_correction_model.py --mode coast
# 提交一次新的Dify纠偏试验
python scripts/verify_brake_correction_dify.py
# 只查询/核对已有运行
python scripts/verify_brake_correction_dify.py --run-id run-e9ca84f93122
# 读取已保存数据作图
python scripts/plot_brake_correction.py --run-id run-e9ca84f93122
```

精简数据与结果图在 `resources/validation/ground_correction_20261124/`；完整数据在对应本机 `data/runs/`。0.2转向、0.3刹车覆盖、0.4差动纠偏是不同实验，不混用通过判据。82项代码测试通过，包括旧流程回归、两侧纠偏方向、触发时序及不满足稳定条件时拒绝通过。
