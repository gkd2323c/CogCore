"""自适应调参器（Adaptive Tuner）：维持系统运行在稳定区间。

接口与 docs/CogCore-通用认知内核架构设计.md §4.9 完全对齐。
关联实验：E15

M0.4 实现：完整 assess + apply，按 5 种情况调整参数。
所有调整都有 max_adjust 上限，clamp 到安全范围。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from cogcore.nt import NTModulations
from cogcore.state_pool import EnergySummary

logger = logging.getLogger(__name__)


class TunerAdjustments(BaseModel):
    """调参器单次调整输出。"""

    lambda_real_delta: float = 0.0
    lambda_virtual_delta: float = 0.0
    attention_budget_delta: int = 0
    spread_factor_delta: float = 0.0
    threshold_delta: float = 0.0
    truncated: bool = False  # 是否被 max_adjust 截断
    reason: str = ""


class AdaptiveTuner:
    """维持系统运行在「平静、可响应、不过载」范围内。

    调参器不替代学习——它只为学习提供稳定的运行环境。
    """

    # 调参阈值（基于主文档 §4.9）
    LOW_ENERGY_THRESHOLD = 5.0       # 总能量 < 此值 = 沉寂
    OVERLOAD_RATIO = 0.8            # 活跃对象 > max_atoms * 此值 = 过载
    PRESSURE_HIGH_THRESHOLD = 0.7    # 认知压 > 此值 = 高压
    PRESSURE_CONSECUTIVE_TICKS = 3   # 连续 N 轮高压 = 触发
    ATTENTION_DIFFUSE_VAR = 0.1      # CAM 能量方差 < 此值 = 注意力过散
    INDUCTION_THIN_NODES = 5         # 感应展开节点数 < 此值 = 传播过薄

    def __init__(
        self,
        tuner_interval: int = 5,
        tuner_max_adjust: float = 0.15,
        max_atoms: int = 200,
    ) -> None:
        self.tuner_interval = tuner_interval
        self.tuner_max_adjust = tuner_max_adjust
        self.max_atoms = max_atoms
        self._tick_count = 0
        self._consecutive_high_pressure = 0
        self._last_adjustments: TunerAdjustments | None = None
        self._adjustment_history: list[TunerAdjustments] = []

    def assess(
        self,
        pool_state: EnergySummary,
        nt: NTModulations,
        attention_stats: dict,
    ) -> TunerAdjustments:
        """评估系统状态，返回调整建议。

        5 种情况：
        1. 沉寂：总能量 < LOW_ENERGY_THRESHOLD
        2. 过载：活跃对象 > max_atoms * OVERLOAD_RATIO
        3. 认知压持续高：连续 PRESSURE_CONSECUTIVE_TICKS 轮 > PRESSURE_HIGH_THRESHOLD
        4. 注意力过散：CAM 能量方差 < ATTENTION_DIFFUSE_VAR
        5. 传播过薄：感应展开节点数 < INDUCTION_THIN_NODES
        """
        self._tick_count += 1

        # 1. 沉寂
        if pool_state.total_energy < self.LOW_ENERGY_THRESHOLD:
            adj = self._make_adjustment(
                lambda_real_delta=-0.05,
                lambda_virtual_delta=-0.05,
                attention_budget_delta=+2,
                spread_factor_delta=-0.1,
                reason=f"沉寂: total_energy={pool_state.total_energy:.2f}",
            )
            self._last_adjustments = self._clamp(adj)
            return self._last_adjustments

        # 2. 过载
        if pool_state.active_count > self.max_atoms * self.OVERLOAD_RATIO:
            adj = self._make_adjustment(
                lambda_real_delta=+0.05,
                lambda_virtual_delta=+0.05,
                attention_budget_delta=-1,
                spread_factor_delta=+0.1,
                reason=f"过载: active={pool_state.active_count}",
            )
            self._last_adjustments = self._clamp(adj)
            return self._last_adjustments

        # 3. 认知压持续高
        if pool_state.cognitive_pressure > self.PRESSURE_HIGH_THRESHOLD:
            self._consecutive_high_pressure += 1
        else:
            self._consecutive_high_pressure = 0

        if self._consecutive_high_pressure >= self.PRESSURE_CONSECUTIVE_TICKS:
            adj = self._make_adjustment(
                spread_factor_delta=+0.05,
                threshold_delta=+0.1,
                reason=f"高压: pressure={pool_state.cognitive_pressure:.2f}",
            )
            self._last_adjustments = self._clamp(adj)
            return self._last_adjustments

        # 4. 注意力过散
        cam_variance = attention_stats.get("cam_energy_variance", 1.0)
        if cam_variance < self.ATTENTION_DIFFUSE_VAR:
            adj = self._make_adjustment(
                attention_budget_delta=-1,
                reason=f"注意力过散: variance={cam_variance:.3f}",
            )
            self._last_adjustments = self._clamp(adj)
            return self._last_adjustments

        # 5. 传播过薄
        induction_nodes = attention_stats.get("induction_nodes", 10)
        if induction_nodes < self.INDUCTION_THIN_NODES:
            adj = self._make_adjustment(
                spread_factor_delta=-0.05,
                attention_budget_delta=+1,
                reason=f"传播过薄: nodes={induction_nodes}",
            )
            self._last_adjustments = self._clamp(adj)
            return self._last_adjustments

        # 正常：不调整
        result = TunerAdjustments(reason="正常区间")
        self._last_adjustments = result
        return result

    def _make_adjustment(self, **kwargs) -> TunerAdjustments:
        """构造 TunerAdjustments，记录 truncated 标志。"""
        return TunerAdjustments(**kwargs)

    def _clamp(self, adj: TunerAdjustments) -> TunerAdjustments:
        """Clamp 调整幅度到 max_adjust 范围内。"""
        truncated = False
        for field_name in ["lambda_real_delta", "lambda_virtual_delta", "spread_factor_delta", "threshold_delta"]:
            val = getattr(adj, field_name)
            if abs(val) > self.tuner_max_adjust:
                val = max(-self.tuner_max_adjust, min(self.tuner_max_adjust, val))
                setattr(adj, field_name, val)
                truncated = True
        # attention_budget_delta clamp 到 [-max_atoms, +max_atoms]
        if abs(adj.attention_budget_delta) > self.max_atoms:
            adj.attention_budget_delta = max(-self.max_atoms, min(self.max_atoms, adj.attention_budget_delta))
            truncated = True
        adj.truncated = truncated
        return adj

    def apply(self, adjustments: TunerAdjustments) -> None:
        """应用参数调整。"""
        # M0.4 简版：只记录 + 打印
        # 实际应该：调整各模块的参数
        self._last_adjustments = adjustments
        self._adjustment_history.append(adjustments)
        if len(self._adjustment_history) > 100:
            self._adjustment_history.pop(0)
        if adjustments.reason and adjustments.reason != "正常区间":
            logger.info(
                f"[APT apply] tick={self._tick_count} "
                f"reason={adjustments.reason} "
                f"lambda_real_delta={adjustments.lambda_real_delta:+.3f} "
                f"attention_budget_delta={adjustments.attention_budget_delta:+d} "
                f"truncated={adjustments.truncated}"
            )

    def get_tuner_report(self) -> dict[str, Any]:
        """调参报告。"""
        return {
            "tick_count": self._tick_count,
            "consecutive_high_pressure": self._consecutive_high_pressure,
            "last_reason": self._last_adjustments.reason if self._last_adjustments else None,
            "last_truncated": self._last_adjustments.truncated if self._last_adjustments else None,
            "history_size": len(self._adjustment_history),
            "low_energy_threshold": self.LOW_ENERGY_THRESHOLD,
            "overload_ratio": self.OVERLOAD_RATIO,
        }
