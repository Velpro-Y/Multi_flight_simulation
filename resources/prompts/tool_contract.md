# 受保护的工具契约

每次调用 `step_simulation` 必须同时提供以下五个控制量：

```json
{
  "aileron": "0.00203",
  "elevator": "-0.01097",
  "rudder": "-0.03744",
  "throttle_left": 0.16863,
  "throttle_right": 0.16863
}
```

- `aileron`、`elevator`、`rudder` 使用可解析为浮点数的字符串；
- 两个油门使用 0 到 1 的数值；
- 舵面范围为 -1 到 1；
- 左发失效后 `throttle_left` 必须保持 0；
- 每次 `step_simulation` 调用推进 2 秒仿真时间；
- 每一步使用配平附近的绝对控制量，不得按百分比累积放大上一时刻控制量。

