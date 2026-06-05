"""认知感受系统（CFS - Cognitive Feeling Signals）。

接口与 docs/CogCore-通用认知内核架构设计.md §4.6 完全对齐。

M0.4 实现：完整 evaluate + to_stimulus_atoms。
评估 5 种感受类型（违和/正确/期待/压力/疲劳）并包装为 StimulusAtom。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from cogcore.types import (
    AtomEnergy,
    AtomTrace,
    FeelingType,
    StimulusAtom,
    StimulusSource,
)

logger = logging.getLogger(__name__)


class FeelingSignal(BaseModel):
    """单一认知感受事件。"""

    type: FeelingType
    intensity: float  # [0.0, 1.0]
    related_atom_ids: list[str] = Field(default_factory=list)
    tick: int = 0


class CognitiveFeelingSystem:
    """评估违和感/正确感/期待/压力/疲劳，让系统感知自身处理状态。

    关联实验：E09, E10
    """

    def __init__(
        self,
        pressure_high: float = 0.7,
        pressure_drop: float = 0.3,
        fatigue_threshold: int = 5,
        enabled: bool = True,
    ) -> None:
        self.enabled = enabled
        self.pressure_high = pressure_high
        self.pressure_drop = pressure_drop
        self.fatigue_threshold = fatigue_threshold

        self._history: list[FeelingSignal] = []
        self._last_pressure: float = 0.0
        self._current_tick: int = 0
        self._recent_execution_count: int = 0

    def set_tick(self, tick: int) -> None:
        self._current_tick = tick

    def set_recent_execution_count(self, count: int) -> None:
        """设置最近执行次数（来自 ActionSystem，用于疲劳评估）。"""
        self._recent_execution_count = count

    def evaluate(
        self,
        pool_energy_summary: dict,
        hdb_result: Any,
        previous_feedback: dict,
    ) -> list[FeelingSignal]:
        """评估当前认知状态，生成感受信号。

        Args:
            pool_energy_summary: 状态池能量摘要（含 cognitive_pressure）
            hdb_result: HDB lookup 结果（dict，含 new_structure_ids, residuals 等）
            previous_feedback: 上一轮反馈（含 reward_signal 等）

        Returns:
            list[FeelingSignal]
        """
        if not self.enabled:
            return []
        signals: list[FeelingSignal] = []

        cognitive_pressure = float(pool_energy_summary.get("cognitive_pressure", 0.0))
        active_count = int(pool_energy_summary.get("active_count", 0))

        # 1. 违和感：认知压超过阈值
        if cognitive_pressure > self.pressure_high:
            signals.append(
                FeelingSignal(
                    type=FeelingType.DISSONANCE,
                    intensity=min(1.0, cognitive_pressure),
                    tick=self._current_tick,
                )
            )

        # 2. 正确感：认知压快速下降
        pressure_delta = self._last_pressure - cognitive_pressure
        if pressure_delta > self.pressure_drop:
            signals.append(
                FeelingSignal(
                    type=FeelingType.CORRECT,
                    intensity=min(1.0, pressure_delta),
                    tick=self._current_tick,
                )
            )

        # 3. 期待：奖励信号 > 0
        reward = float(previous_feedback.get("reward_signal", 0.0))
        if reward > 0.3:
            signals.append(
                FeelingSignal(
                    type=FeelingType.ANTICIPATION,
                    intensity=min(1.0, reward),
                    tick=self._current_tick,
                )
            )

        # 4. 压力：惩罚信号
        if reward < -0.3:
            signals.append(
                FeelingSignal(
                    type=FeelingType.PRESSURE,
                    intensity=min(1.0, abs(reward)),
                    tick=self._current_tick,
                )
            )

        # 5. 疲劳：最近执行次数高
        if self._recent_execution_count > self.fatigue_threshold:
            signals.append(
                FeelingSignal(
                    type=FeelingType.FATIGUE,
                    intensity=min(1.0, self._recent_execution_count / 10.0),
                    tick=self._current_tick,
                )
            )

        # 更新 last_pressure（供下一轮比较）
        self._last_pressure = cognitive_pressure

        # 记录历史
        self._history.extend(signals)

        if signals:
            logger.info(
                f"[CFS evaluate] tick={self._current_tick} "
                f"pressure={cognitive_pressure:.2f} "
                f"signals={[(s.type.value, f'{s.intensity:.2f}') for s in signals]}"
            )

        return signals

    def to_stimulus_atoms(self, signals: list[FeelingSignal]) -> list[StimulusAtom]:
        """把感受信号包装为 StimulusAtom（source=FEELING），供状态池入池。"""
        atoms: list[StimulusAtom] = []
        for signal in signals:
            atom = StimulusAtom(
                content=f"feeling:{signal.type.value}:{signal.intensity:.2f}",
                source=StimulusSource.FEELING,
                modality="text",
                energy=AtomEnergy(
                    real=signal.intensity,
                    virtual=0.0,
                ),
                age_ticks=0,
                birth_tick=signal.tick,
                trace=AtomTrace(
                    origin=f"cfs:{signal.type.value}",
                ),
            )
            atoms.append(atom)
        return atoms

    def get_feeling_history(self) -> list[FeelingSignal]:
        return list(self._history)

    def get_cfs_report(self) -> dict[str, Any]:
        """CFS 报告。"""
        type_counts: dict[str, int] = {}
        for s in self._history:
            t = s.type.value
            type_counts[t] = type_counts.get(t, 0) + 1
        return {
            "tick": self._current_tick,
            "history_size": len(self._history),
            "type_counts": type_counts,
            "last_pressure": self._last_pressure,
            "pressure_high": self.pressure_high,
        }
