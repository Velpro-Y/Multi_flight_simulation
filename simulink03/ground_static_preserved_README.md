# 保留原布局的地面静止模型

模型：beaver_agent_env_ground_static_preserved.slx

基于用户本次清理后的 D:/Study/shangfei_2/6DOF_Airframe-LLM-Flight-Simulation/simulink/beaver_agent_env_ground_contact_tire_steering.slx 重新生成，未使用旧版模型替代本次源文件。源文件未修改。

## 布局与层次

- 45 个原有顶层模块全部保留原位置，原有顶层连接全部保留。
- 除明确重建的 GroundContactTireSteering 内部外，271 处原有模块的坐标逐项对比一致。没有对原模型及原有子系统执行整体自动布局。
- 顶层仅增加 GroundStaticStateBus 一个带名称的状态总线传递模块。完整状态通过 GStatic_States 标签传入地面系统，方向余弦矩阵通过 6DOF EOM 内的 GStatic_DCM 标签传入，避免新增多条横跨全图的状态连线。两个标签均已在整机更新时解析验证。
- GroundContactTireSteering 的外部 14 入、3 出接口保持不变，内部新计算分为 StateVectors、ThreePointGroundDynamics、GroundDiagnostics。
- ThreePointGroundDynamics 内保留 NoseGear、LeftMainGear、RightMainGear 三轮支撑结构。每轮计算进一步分为 ContactGeometry、NormalReaction、WheelKinematics、TireFrictionCircle、ForceResolution，以及接触力矩计算。
- 原近似地面模型的失效增益和简化状态输入，仅为保留外部接口而保留连接，在内部明确接入终止块；不再参与新的物理接触计算。参数以模型工作区 GroundStatic 为准。
- 新增计算模块矩形无重叠，模型内无悬空线段。
- 新增子系统已关闭内部缩略图预览；每轮计算阶段的端口使用实际物理信号名称，避免大量数字端口和缩略连线叠加。原生导出图见 ground_static_preserved_ground.png、ground_static_preserved_three_point.png、ground_static_preserved_nose_gear.png。

## 必要接口修复

清理后的原模型控制总线仅剩 Aileron、Elevator、Rudder，但原有气动计算仍请求 Flap。为维持原三输入总线及其位置，在 Aerodynamic Model/Actuator Aerodynamic Coefficients 内，将原 Flap 总线选择点替换为零偏角常量，显示标注为 Flap = 0。该位置和其他原有气动模块位置均保留。当前副本没有新增可操纵襟翼功能。

气动零速分母保护、两侧推进关车隔离均封装在原模块对应位置的内部，不增加顶层长线。Visualization 和 State Plots 保持启用，显示用迎角、侧滑角在空速低于 1e-6 m/s 时按零显示。

## 运行

1. 在 MATLAB R2022a 中打开新 SLX，点击运行，默认运行 30 秒。无需修改或运行项目 Python 脚本。
2. 默认无风、关车、起落架接触使能、前轮对中、驻车阻尼开启。
3. 打开 Visualization/State Plots 查看曲线，必要时点击自动缩放。
4. 双击 GroundContactTireSteering 逐层查看新增模块；GroundDiagnostics 中可查看各输出变量对应关系。
5. GroundStatic 已存入模型工作区，无需外部初始化 GroundStatic。原飞机工具箱初始化回调继续使用原有 Aerospace 数据定义。

飞机质量保持 2288.231 kg。默认 CG 的 NED 高度坐标 Ze 为 -1.44 m，跑道平面为 Ze=0，支柱静载压缩约 0.06 m。起落架几何、刚度和阻尼沿用上一版演示假设，不代表真实机型标定。

## 验证

本机 MATLAB R2022a 于 2026-11-05 完成：

| 项目 | 结果 |
|---|---|
| 整机更新 | 通过 |
| 默认静止 30 秒 | 通过，最大速度约 3.61e-16 m/s，Ze 保持 -1.44 m |
| 高度、下沉速度和姿态扰动后运行 30 秒 | 通过，恢复稳定支撑 |
| 离地初始状态短时测试 | 通过，未接触时无支撑力，正常下落 |
| 关闭起落架接触短时测试 | 通过，无支撑力，正常下落 |
| 四组显示输入 | 各测试均有有限值的完整时序数据 |
| 原布局与连接检查 | 通过，原顶层连接无丢失、原模块坐标无变化 |
| 新模块矩形重叠和悬空线检查 | 无 |
| 源 SLX 完整性 | SHA-256 与构建前相同 |

数值及结构验证采用无 JVM 批处理。模型不冻结位置、速度或姿态。

验证记录：ground_static_preserved_verification.json、ground_static_preserved_layout_verification.json。

重建脚本：build_ground_static_preserved.m；验证脚本：verify_ground_static_preserved.m。普通使用直接打开 SLX 即可。
