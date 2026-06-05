"""行动节点与反馈学习（Action System）。

接口与 docs/CogCore-通用认知内核架构设计.md §4.8 完全对齐。
论文公式（附录 B）：drive(a) > threshold(a, NT, CFS)
论文 5.7.1：教师反馈采用延迟合流（queue_teacher_feedback + merge_pending_teacher_feedback）。

M0.3 实现：完整 ActionSystem
- evaluate_drives：基础 + 学习 + 上下文 + 疲劳 + NT 调制
- 反馈处理：写入 history、调整 drive、注入状态池
- 教师延迟合流：queue + merge（不立即塑形）
"""

from __future__ import annotations

import logging
from typing import Any, Callable
from uuid import UUID

from pydantic import BaseModel, Field

from cogcore.nt import NTModulations
from cogcore.state_pool import StatePool
from cogcore.types import (
    ActionNode,
    ActionSource,
    AtomEnergy,
    AtomTrace,
    Outcome,
    StimulusAtom,
    StimulusSource,
)

logger = logging.getLogger(__name__)


# ============================================================
# 数据类
# ============================================================


class ActionCandidate(BaseModel):
    """待执行行动候选（评估阶段的输出）。"""

    node: ActionNode
    final_drive: float
    trigger_reason: str = ""


class ActionResult(BaseModel):
    """行动执行结果。"""

    outcome: Outcome
    reward_signal: float
    feedback_text: str = ""
    teacher_labels: dict[str, Any] = Field(default_factory=dict)


class TeacherFeedback(BaseModel):
    """教师反馈（论文 5.7.1 延迟合流模型）。"""

    reward_signal: float = 0.0
    anchor_note: str = ""
    explanation: str = ""
    target_atom_id: UUID | None = None
    received_tick: int = 0


# ============================================================
# ActionSystem
# ============================================================


class ActionSystem:
    """管理可执行意图，将行动后果和奖惩反馈写回认知系统。

    关联实验：E03, E04, E05, E14
    """

    def __init__(
        self,
        action_fatigue_rate: float = 0.1,
        learned_drive_decay: float = 0.95,
        reward_threshold_significant: float = 0.5,
    ) -> None:
        self.action_fatigue_rate = action_fatigue_rate
        self.learned_drive_decay = learned_drive_decay
        self.reward_threshold_significant = reward_threshold_significant

        self._nodes: dict[UUID, ActionNode] = {}
        self._feedback_queue: list[TeacherFeedback] = []  # 论文 5.7.1 延迟合流缓冲
        self._current_tick: int = 0
        self._executor: Callable | None = None  # 默认执行器（callable(node) -> ActionResult）

    # ============================================================
    # 注册与维护
    # ============================================================

    def register_node(self, node: ActionNode) -> None:
        """注册行动节点。"""
        self._nodes[node.id] = node

    def set_executor(self, executor: Callable) -> None:
        """设置默认执行器（callable(ActionNode) -> ActionResult）。"""
        self._executor = executor

    def set_tick(self, tick: int) -> None:
        self._current_tick = tick

    # ============================================================
    # 评估驱动力（论文 §4.8）
    # ============================================================

    def evaluate_drives(
        self, pool: StatePool, nt: NTModulations
    ) -> list[ActionCandidate]:
        """计算所有注册行动节点的当前驱动力。

        论文公式：
            drive(t) = base + learned + contextual - fatigue
            learned = Σ(reward * decay^(t - t_i)) - Σ(punishment * decay^(t - t_j))
            trigger: drive > threshold * (1 + NT.caution)
        """
        candidates: list[ActionCandidate] = []

        for node in self._nodes.values():
            drive = self._compute_drive(node, pool, nt)

            # 触发条件（论文附录 B 严格 > 改为 >= 以使浮点边界能触发）
            modulated_threshold = node.threshold * (1.0 + nt.caution)
            if drive >= modulated_threshold:
                candidates.append(
                    ActionCandidate(
                        node=node,
                        final_drive=drive,
                        trigger_reason=(
                            f"drive={drive:.3f} > "
                            f"threshold={modulated_threshold:.3f} "
                            f"(base={node.threshold} * (1+caution={nt.caution}))"
                        ),
                    )
                )

        # 按 drive 降序
        candidates.sort(key=lambda c: c.final_drive, reverse=True)
        return candidates

    def _compute_drive(
        self, node: ActionNode, pool: StatePool, nt: NTModulations
    ) -> float:
        """单节点驱动力计算。"""
        # 基础驱动力
        base = self._base_drive_for(node)

        # 学习驱动力：奖励时间衰减 - 惩罚时间衰减
        learned = self._learned_drive(node)

        # 上下文驱动力：来自感应生长（这里简化为 NT 调制）
        # arousal > 0 → 行动阈值降低（即更易触发）
        # 论文 §4.8：contextual_drive 应来自感应生长
        # M0.3 简版：用 NT.arousal 提升 drive
        contextual = nt.arousal * 0.3

        # 疲劳惩罚：短时间内重复执行
        fatigue = self._fatigue_penalty(node)

        return base + learned + contextual - fatigue

    def _base_drive_for(self, node: ActionNode) -> float:
        """基础驱动力。"""
        if node.source == ActionSource.INNATE:
            return 1.0  # 先天规则：基础 drive = 1
        return 0.5  # 后天习得：基础 drive 较低

    def _learned_drive(self, node: ActionNode) -> float:
        """从历史奖励/惩罚学习。

        learned = Σ(reward * decay^(t - t_i)) - Σ(punishment * decay^(t - t_j))
        """
        learned = 0.0
        decay = self.learned_drive_decay
        t = self._current_tick

        # 假设 history 里的每个值都发生在 node.last_executed_tick（粗略近似）
        for r in node.reward_history:
            age = max(0, t - node.last_executed_tick)
            learned += r * (decay ** age)

        for p in node.punishment_history:
            age = max(0, t - node.last_executed_tick)
            learned -= p * (decay ** age)

        return learned

    def _fatigue_penalty(self, node: ActionNode) -> float:
        """疲劳惩罚：短时间内重复执行降低 drive。"""
        # M0.3 简版：用 execution_count 近似
        # 实际应该用「最近 N 轮内的执行次数」
        return node.execution_count * self.action_fatigue_rate * 0.1

    # ============================================================
    # 执行
    # ============================================================

    def execute(
        self, candidate: ActionCandidate, executor: Callable | None = None
    ) -> ActionResult:
        """执行行动候选。

        论文 4.8：行动节点通过 tool_mapping 关联到具体工具。
        M0.3 简版：使用 set_executor 设置的执行器，或接受参数。
        """
        if executor is None:
            executor = self._executor
        if executor is None:
            # 没有执行器时，创建一个占位结果（"未执行"）
            return ActionResult(
                outcome=Outcome.ERROR,
                reward_signal=0.0,
                feedback_text=f"无执行器: {candidate.node.name}",
            )

        result = executor(candidate.node)
        # 更新行动节点
        candidate.node.execution_count += 1
        candidate.node.last_executed_tick = self._current_tick
        candidate.node.drive = candidate.final_drive  # 同步最新 drive
        return result

    # ============================================================
    # 反馈处理（论文 §4.8 + 5.7.1）
    # ============================================================

    def process_feedback(self, result: ActionResult, target_node: ActionNode | None = None) -> None:
        """处理行动反馈：写入历史、调整 learned_drive、生成刺激元。

        论文 §4.8：
        1. 写入 reward_signal 到 history
        2. 调整 learned_drive
        3. 包装为 StimulusAtom 注入状态池（由 stage 内部做）
        4. 如果 |reward| > 0.5 触发 Anticipation/Pressure
        5. 教师标签写入 HDB
        """
        if target_node is None:
            # M0.3 简版：只支持单节点反馈
            return

        target_node.reward_history.append(result.reward_signal)

        # 如果是显著反馈（论文 §4.8 触发条件），增加权重
        if abs(result.reward_signal) > self.reward_threshold_significant:
            if result.reward_signal > 0:
                logger.info(
                    f"[process_feedback] {target_node.name} 收到显著奖励 "
                    f"{result.reward_signal:.2f}"
                )
            else:
                target_node.punishment_history.append(result.reward_signal)
                logger.info(
                    f"[process_feedback] {target_node.name} 收到显著惩罚 "
                    f"{result.reward_signal:.2f}"
                )

    def to_stimulus_atom(
        self, result: ActionResult, node: ActionNode
    ) -> StimulusAtom:
        """把行动结果包装为 StimulusAtom（source=ACTION），用于注入状态池。"""
        return StimulusAtom(
            content=f"action:{node.name}:{result.outcome.value}",
            source=StimulusSource.ACTION,
            modality="text",
            energy=AtomEnergy(
                real=max(0.0, result.reward_signal),
                virtual=max(0.0, -result.reward_signal),
            ),
            age_ticks=0,
            birth_tick=self._current_tick,
            trace=AtomTrace(
                origin=f"action_node:{node.id}",
                action_events=[node.id],
            ),
        )

    # ============================================================
    # 教师反馈延迟合流（论文 5.7.1）
    # ============================================================

    def queue_teacher_feedback(self, labels: dict) -> None:
        """暂存教师信号到 feedback_queue，不立即进入 AP。

        论文 5.7.1：避免在错误的认知快照上塑形。
        """
        fb = TeacherFeedback(
            reward_signal=float(labels.get("reward_signal", 0.0)),
            anchor_note=str(labels.get("anchor_note", "")),
            explanation=str(labels.get("explanation", "")),
            target_atom_id=labels.get("target_atom_id"),
            received_tick=self._current_tick,
        )
        self._feedback_queue.append(fb)

    def merge_pending_teacher_feedback(self) -> list[TeacherFeedback]:
        """在下一轮 tick 开始前调用，与 Expectation Contract 对齐后注入 HDB。

        返回合并后的 TeacherFeedback 列表（清空 queue）。
        """
        merged = self._feedback_queue.copy()
        self._feedback_queue.clear()
        if merged:
            logger.info(
                f"[merge_pending_teacher_feedback] tick={self._current_tick} "
                f"合并 {len(merged)} 条教师反馈"
            )
        return merged

    # ============================================================
    # 报告
    # ============================================================

    def get_action_report(self) -> dict[str, Any]:
        """行动系统报告。"""
        return {
            "tick": self._current_tick,
            "node_count": len(self._nodes),
            "pending_teacher_feedback": len(self._feedback_queue),
            "total_executions": sum(
                n.execution_count for n in self._nodes.values()
            ),
            "nodes": [
                {
                    "id": str(n.id),
                    "name": n.name,
                    "drive": n.drive,
                    "threshold": n.threshold,
                    "execution_count": n.execution_count,
                    "reward_history_size": len(n.reward_history),
                    "punishment_history_size": len(n.punishment_history),
                }
                for n in self._nodes.values()
            ],
        }

    def get_node(self, node_id: UUID) -> ActionNode | None:
        return self._nodes.get(node_id)
