"""情绪递质系统（NT - Neurotransmitter System）：慢变量调制。

接口与 docs/CogCore-通用认知内核架构设计.md §4.7 完全对齐。
论文公式：
    NT(t+1) = NT_baseline + inertia * (NT(t) - NT_baseline) + impulse(t)

M0.4 实现：完整 update + impulse 计算 + clamp 到 [0.0, 1.0]。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class NTModulations(BaseModel):
    """情绪递质多通道调制值。

    各通道值范围 [0.0, 1.0]，影响注意力预算、行动阈值、衰减等参数。
    """

    focus: float = 0.0          # 注意力收窄/发散
    arousal: float = 0.0        # 警觉/激活水平
    caution: float = 0.0        # 谨慎度（提升行动阈值）
    exploration: float = 0.0    # 探索倾向（增加感应生长深度）
    fatigue: float = 0.0        # 累积性疲劳
    stability: float = 0.0      # 降低衰减系数

    # 论文规则（主文档 §4.7）：
    # focus > 0     → Attention.budget 减少
    # arousal > 0   → 所有 E_real 和 E_virtual 乘以 (1 + arousal * 0.3)
    # caution > 0.5 → ActionNode.threshold 乘以 (1 + caution)
    # exploration > 0.5 → InductionGrowth.max_depth 增加 1-2 层
    # fatigue > 0.7 → 所有能量注入乘以 (1 - fatigue * 0.5)
    # stability > 0.5 → λ_real 和 λ_virtual 提高

    inertia: float = Field(
        default=0.85, description="递质惯性系数（论文附录 B 默认值）"
    )
    baseline: dict[str, float] = Field(default_factory=dict)


class NeurotransmitterSystem:
    """NT 调制值维护与更新。

    关联实验：E14, E15
    """

    # NT 通道名常量
    CHANNELS = ("focus", "arousal", "caution", "exploration", "fatigue", "stability")

    def __init__(self, initial: NTModulations | None = None, enabled: bool = True) -> None:
        self.enabled = enabled
        self.current = initial or NTModulations()
        self._impulse_buffer: list[dict[str, float]] = []
        self._tick: int = 0

    def set_tick(self, tick: int) -> None:
        self._tick = tick

    def update(
        self,
        feeling_signals: list[dict] | list[Any],
        reward_signals: list[float],
        rules: dict[str, float],
    ) -> NTModulations:
        """按惯性规则更新调制值。

        论文公式：
            NT(t+1) = NT_baseline + inertia * (NT(t) - NT_baseline) + impulse(t)

        Args:
            feeling_signals: CFS 感受信号列表（dict 或 FeelingSignal）
            reward_signals: 行动反馈奖励列表
            rules: 硬规则（如"疲劳必须随时间增长"）

        Returns:
            更新后的 NTModulations
        """
        if not self.enabled:
            return self.current
        # 计算 impulse
        impulse = self._compute_impulse(feeling_signals, reward_signals, rules)

        # 应用公式：每个通道更新
        for channel in self.CHANNELS:
            baseline = self.current.baseline.get(channel, 0.0)
            current = getattr(self.current, channel)
            new_value = (
                baseline
                + self.current.inertia * (current - baseline)
                + impulse.get(channel, 0.0)
            )
            # Clamp 到 [0.0, 1.0]
            new_value = max(0.0, min(1.0, new_value))
            setattr(self.current, channel, new_value)

        # 记录 impulse（供审计）
        self._impulse_buffer.append(impulse)
        if len(self._impulse_buffer) > 100:
            self._impulse_buffer.pop(0)

        logger.info(
            f"[NT update] tick={self._tick} "
            f"focus={self.current.focus:.3f} "
            f"arousal={self.current.arousal:.3f} "
            f"caution={self.current.caution:.3f} "
            f"exploration={self.current.exploration:.3f} "
            f"fatigue={self.current.fatigue:.3f} "
            f"stability={self.current.stability:.3f}"
        )

        return self.current

    def _compute_impulse(
        self,
        feeling_signals: list,
        reward_signals: list[float],
        rules: dict[str, float],
    ) -> dict[str, float]:
        """根据感受信号、奖励和规则计算 impulse。"""
        impulse: dict[str, float] = {ch: 0.0 for ch in self.CHANNELS}

        # 1. 从感受信号计算 impulse
        for signal in feeling_signals:
            # 支持 dict 和 FeelingSignal 两种
            if isinstance(signal, dict):
                sig_type = signal.get("type", "")
                intensity = float(signal.get("intensity", 0.0))
            else:
                sig_type = getattr(signal.type, "value", str(signal.type))
                intensity = float(signal.intensity)

            # 违和感 → caution ↑, arousal ↑
            if sig_type == "dissonance":
                impulse["caution"] += intensity * 0.4
                impulse["arousal"] += intensity * 0.3
            # 正确感 → focus ↑, stability ↑
            elif sig_type == "correct":
                impulse["focus"] += intensity * 0.3
                impulse["stability"] += intensity * 0.2
            # 期待 → arousal ↑, exploration ↑
            elif sig_type == "anticipation":
                impulse["arousal"] += intensity * 0.4
                impulse["exploration"] += intensity * 0.3
            # 压力 → caution ↑, fatigue ↑
            elif sig_type == "pressure":
                impulse["caution"] += intensity * 0.5
                impulse["fatigue"] += intensity * 0.3
            # 疲劳 → fatigue ↑
            elif sig_type == "fatigue":
                impulse["fatigue"] += intensity * 0.6

        # 2. 从奖励信号计算 impulse
        for r in reward_signals:
            if r > 0:
                impulse["arousal"] += r * 0.3
                impulse["exploration"] += r * 0.2
            elif r < 0:
                impulse["caution"] += abs(r) * 0.4
                impulse["fatigue"] += abs(r) * 0.2

        # 3. 应用硬规则
        if "fatigue_growth" in rules:
            impulse["fatigue"] += rules["fatigue_growth"]
        if "stability_decay" in rules:
            impulse["stability"] -= rules["stability_decay"]

        return impulse

    def get_nt_report(self) -> dict[str, Any]:
        """NT 状态报告。"""
        return {
            "tick": self._tick,
            "focus": self.current.focus,
            "arousal": self.current.arousal,
            "caution": self.current.caution,
            "exploration": self.current.exploration,
            "fatigue": self.current.fatigue,
            "stability": self.current.stability,
            "inertia": self.current.inertia,
            "baseline": dict(self.current.baseline),
            "impulse_buffer_size": len(self._impulse_buffer),
        }
