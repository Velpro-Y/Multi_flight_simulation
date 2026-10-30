"""Bounded, explainable prompt candidate generation for the demo."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CandidateDefinition:
    name: str
    description: str
    addendum: str


class CandidateGenerator:
    """Generate only allowed addenda; protected prompt facts are untouched."""

    CONTROL_SIGN_CANDIDATE = CandidateDefinition(
        name="control_sign_guard",
        description="根据控制方向失败强化副翼与方向舵符号检查",
        addendum="""# 控制符号决策检查（候选）

每次调用工具前，先读取当前阶段配平值，再执行以下硬检查：

1. 若 `roll` 高于当前阶段配平值超过 0.04 rad，禁止使用比配平值更负的副翼；不确定时直接使用配平副翼；
2. 若 `roll` 低于当前阶段配平值超过 0.04 rad，禁止使用比配平值更正的副翼；不确定时直接使用配平副翼；
3. 若 `yaw_rate > 0.03 rad/s`，禁止把方向舵调得比当前阶段配平值更负，应回到配平值或减小负值幅度；
4. 在输出动作前，用一句内部检查确认“修正方向会使滚转/偏航误差减小”；无法确认时保持当前阶段配平，不做额外修正。
""",
    )

    DEFAULT_CANDIDATES = (
        CandidateDefinition(
            name="phase_guard",
            description="强化阶段门控，防止300 ft提前复飞",
            addendum="""# 决策检查清单（候选）

每次调用工具前依次确认：

1. 当前 `flight_phase` 是什么；
2. 当前阶段允许下降还是爬升；
3. 当前动作使用的是哪一组配平；
4. `ENGINE_OUT_DESCENT` 阶段不得输出正爬升目标；
5. 只有 `GO_AROUND` 阶段才能使用单发复飞配平。
""",
        ),
        CandidateDefinition(
            name="event_first",
            description="要求先检查事件和完成标志，再计算动作",
            addendum="""# 事件优先决策规则（候选）

每轮先检查 `done`、`event` 和 `flight_phase`，再生成动作。阶段发生变化时，立即停止使用上一阶段配平；状态没有越过阶段门限时，禁止提前切换策略。每次只输出一组配平附近的控制量并调用工具。
""",
        ),
    )

    def generate(
        self, count: int, failure_labels: Optional[list[str]] = None
    ) -> list[CandidateDefinition]:
        ordered: list[CandidateDefinition] = []
        if "CONTROL_SIGN_ERROR" in (failure_labels or []):
            ordered.append(self.CONTROL_SIGN_CANDIDATE)
        ordered.extend(self.DEFAULT_CANDIDATES)

        unique: list[CandidateDefinition] = []
        seen: set[str] = set()
        for candidate in ordered:
            if candidate.name not in seen:
                unique.append(candidate)
                seen.add(candidate.name)
        return unique[:count]
