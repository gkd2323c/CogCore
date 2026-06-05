"""PA 双层运行模式（论文 5.8.1）。

三种模式递进：
- full_silent: 只在明确触发下响应（默认、验证用）
- ap_agency: AP 可基于内部状态主动升起候选
- reinforced_agency: 主动性需经过教师门控
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class AgentMode(str, Enum):
    """CogCore 运行模式。"""

    FULL_SILENT = "full_silent"
    AP_AGENCY = "ap_agency"
    REINFORCED_AGENCY = "reinforced_agency"


# ============================================================
# 唤醒决策
# ============================================================


class WakeDecision:
    """唤醒决策结果。"""

    def __init__(
        self,
        should_wake: bool = False,
        reason: str = "",
        wake_drive: float = 0.0,
    ) -> None:
        self.should_wake = should_wake
        self.reason = reason
        self.wake_drive = wake_drive

    def __bool__(self) -> bool:
        return self.should_wake


class WakeController:
    """控制 CogCore 是否应主动运行 tick。

    决策链：
        has_external_input → YES → wake
        mode == full_silent → NO → 等待
        mode == ap_agency   → 评估 wake_drive → >threshold → wake
        mode == reinforced_agency → wake_drive + teacher_gate → wake
    """

    def __init__(
        self,
        mode: AgentMode | str = AgentMode.FULL_SILENT,
        wake_drive_threshold: float = 0.6,
    ) -> None:
        self.mode = AgentMode(mode) if isinstance(mode, str) else mode
        self.wake_drive_threshold = wake_drive_threshold

    def should_wake(
        self,
        event: dict | None = None,
        cogcore_state: dict | None = None,
        teacher_gate: callable | None = None,
    ) -> WakeDecision:
        """判断当前 tick 是否应被执行。

        Args:
            event: 外部事件（含 raw_input 等）
            cogcore_state: 当前 CogCore 状态
            teacher_gate: 教师门控函数 (event, state) → bool

        Returns:
            WakeDecision
        """
        event = event or {}
        cogcore_state = cogcore_state or {}

        # 1. 有外源输入 → 立即唤醒
        if event.get("raw_input") or event.get("has_external_input"):
            return WakeDecision(True, "external input", wake_drive=1.0)

        if self.mode == AgentMode.FULL_SILENT:
            return WakeDecision(False, "full_silent: waiting for external input")

        # 2. ap_agency: 评估内部唤醒驱动
        wake_drive = self._compute_wake_drive(cogcore_state)
        if wake_drive < self.wake_drive_threshold:
            return WakeDecision(
                False,
                f"ap_agency: wake_drive={wake_drive:.2f} < threshold={self.wake_drive_threshold:.2f}",
                wake_drive=wake_drive,
            )

        # 3. reinforced_agency: 额外教师门控
        if self.mode == AgentMode.REINFORCED_AGENCY:
            if teacher_gate is not None:
                gate_ok = teacher_gate(event, cogcore_state)
                if not gate_ok:
                    return WakeDecision(
                        False,
                        f"reinforced_agency: teacher gate rejected (drive={wake_drive:.2f})",
                        wake_drive=wake_drive,
                    )

        return WakeDecision(
            True,
            f"{self.mode.value}: wake_drive={wake_drive:.2f} >= threshold={self.wake_drive_threshold:.2f}",
            wake_drive=wake_drive,
        )

    def _compute_wake_drive(self, state: dict) -> float:
        """评估内部唤醒驱动——基于状态池活跃度和 NT 觉醒度。

        驱动因素：
        - pool 活跃原子数（有内容在等待处理）
        - NT arousal（觉醒度高更倾向于主动）
        - 行动候选数（有可执行行动时更可能醒来）
        """
        drive = 0.0

        pool = state.get("pool_snapshot", {})
        if pool:
            if hasattr(pool, "energy_summary"):
                es = pool.energy_summary
                active = es.active_count if hasattr(es, "active_count") else 0
                total_e = es.total_energy if hasattr(es, "total_energy") else 0.0
            elif isinstance(pool, dict):
                es = pool.get("energy_summary", {})
                active = es.get("active_count", 0) if isinstance(es, dict) else 0
                total_e = es.get("total_energy", 0.0) if isinstance(es, dict) else 0.0
            else:
                active, total_e = 0, 0.0
            drive += min(active / 10.0, 1.0) * 0.5
            drive += min(total_e / 5.0, 1.0) * 0.3

        nt = state.get("nt_values", {})
        if nt:
            if hasattr(nt, "arousal"):
                arousal = nt.arousal
            elif isinstance(nt, dict):
                arousal = nt.get("arousal", 0.0)
            else:
                arousal = 0.0
            drive += arousal * 0.2

        return min(drive, 1.0)
