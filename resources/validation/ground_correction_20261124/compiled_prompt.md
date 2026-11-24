# 场景三差动刹车纠偏试验 控制契约

任务为试验点2-4的差动刹车纠偏。跑道中线Ye=0，初始100kn、横向偏差45ft、航向偏差2度，最长20秒仿真时间。每轮读取最新真实状态，输出下一0.5秒动作。后端已reset，不调用工具，只输出一个七字段JSON：
{"nose_wheel_deg":0,"throttle_left":0,"throttle_right":0,"brake_left":0,"brake_right":0,"brake_system_mode":0,"auto_brake_armed":false}

本试验固定前轮0、手动刹车模式、自动刹车未预位，左右油门必须相同且在0至0.4。左右刹车各0至1，唯一用于纠偏的差动执行量是左右刹车差。后端不替代你选择刹车。

correction_triggered=false时两侧刹车必须为0；飞机自然滑跑，绝对偏差首次超过50ft后触发。偏差正值表示在跑道右侧，左刹车较大产生负偏航向中线纠偏；负偏差反之。不要进行掉头，不要追求40度或75度前轮角。

目标是绝对横向偏差回到30ft以内。为确认稳定，需同时使航向偏差不超过3度、偏航角速度不超过1度/秒、横向速度不超过0.75m/s，并连续保持至少1秒。状态中的stable_duration_s由真实模型采样计算，后端满足条件后结束。防止过冲：提前松刹车或使用另一侧刹车制止偏航，回到中线方向平稳滑跑。禁止用自动刹车或差动油门代替本试验的差动刹车。

---

# 本次纠偏实验参数
- experiment: brake_correction
- initial_speed_kn: 100
- initial_lateral_deviation_ft: 45
- initial_heading_deg: 2
- max_simulation_time_s: 20

---

# 纠偏决策原则

读取lateral_deviation_ft、lateral_velocity_m_s、heading_deg、yaw_rate_deg_s和correction_triggered。偏差在50ft以内且尚未触发时不刹车。触发后先让航向转向中线：正偏差用左刹车，负偏差用右刹车；根据实际偏航响应调节大小。

100kn车速下不要持续重刹。可先用适度差动刹车观察一轮，随后按航向和偏航率调整。用横向速度估计未来1至2秒偏差，进入30ft范围前提前考虑停止向内偏航。目标是进入范围后沿跑道前进；航向已经朝中线且偏航率仍较大时应松开原侧、按需反侧刹车抑制过冲，而非持续同侧刹车。保持左右油门相同；速度若不需补偿，两侧可同时为0。只输出本轮动作JSON。
