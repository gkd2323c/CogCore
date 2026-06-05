"""注意力与当前注意记忆体（Attention & CAM）。

接口与 docs/CogCore-通用认知内核架构设计.md §4.5 完全对齐。
论文公式（附录 B）：score = f(E, P, R, F, CFS, NT)

M0.4 实现：完整 select + 5 通道加权 + 重复抑制 + budget。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from cogcore.state_pool import StatePool
from cogcore.types import StimulusAtom

logger = logging.getLogger(__name__)


class AttentionConfig(BaseModel):
    """注意力配置。"""

    budget: int = 10
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "energy": 0.3,
            "recency": 0.2,
            "reward_relevance": 0.2,
            "novelty": 0.15,
            "feeling_intensity": 0.15,
        }
    )
    repeat_penalty: float = 0.5
    fatigue_penalty: float = 0.2
    fatigue_consecutive_threshold: int = 3  # 连续选 N 次后开始疲劳
    complexity_modulation: bool = True


class CurrentAttentionMemory(BaseModel):
    """当前注意记忆体：本轮被选中的对象。"""

    items: list[StimulusAtom] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)
    tick: int = 0


class Attention:
    """有预算的能量调制。选中对象形成 CAM，再转化为内源刺激回注。

    关联实验：E07（复杂度到注意力调制）, E15（注意力预算调整）
    """

    def __init__(self, config: AttentionConfig | None = None) -> None:
        self.config = config or AttentionConfig()
        # 重复抑制：记录每个 atom_id 被选中的连续次数
        self._consecutive_selections: dict[str, int] = {}
        # 上一轮的 CAM（用于重复抑制）
        self._last_cam: CurrentAttentionMemory | None = None
        # feeling intensity cache：source=FEELING 的 atom 强度
        self._feeling_cache: dict[str, float] = {}
        # reward relevance cache：source=ACTION 的 atom 强度
        self._reward_cache: dict[str, float] = {}
        self._selection_history: list[CurrentAttentionMemory] = []
        # M0.9 复杂度调制字段 (E07)
        self.effective_top_n: int = 16
        self.current_mode: str = "baseline"

    def select(
        self, pool: StatePool, config: AttentionConfig | None = None
    ) -> CurrentAttentionMemory:
        """注意力选择（CFS/NT 调制）。

        5 通道加权：
            score = w_e*E + w_r*Recency + w_rr*Reward + w_n*Novelty + w_f*Feeling

        重复抑制：
            - 上轮选过的本轮 penalty * 0.5
            - 连续 3 轮都选 → penalty * 0.2
        """
        cfg = config or self.config

        # 复杂度调制 (E07)
        if cfg.complexity_modulation:
            active_count = len(pool.get_all())
            if active_count <= 8:
                self.current_mode = "attention_diverge_mode"
                cfg.budget = 6
                self.effective_top_n = 21
            elif active_count <= 10:
                self.current_mode = "baseline"
                cfg.budget = 8
                self.effective_top_n = 16
            else:
                self.current_mode = "attention_focus_mode"
                cfg.budget = 10
                self.effective_top_n = 11

        # 调整 budget（NT.focus 影响）
        effective_budget = self._effective_budget(cfg)

        # 收集候选
        candidates = pool.get_all()
        if not candidates:
            return CurrentAttentionMemory(tick=0)

        # 更新 feeling/reward cache
        self._update_caches(pool)

        # 给每个候选评分
        scored: list[tuple[float, StimulusAtom]] = []
        for atom in candidates:
            score = self._score(atom, cfg)
            scored.append((score, atom))

        # 降序
        scored.sort(key=lambda x: x[0], reverse=True)

        # 复杂度候选范围截断 (E07)
        top_candidates = scored[:self.effective_top_n]

        # 取 top budget
        top = top_candidates[:effective_budget]

        # 更新连续选择计数
        selected_ids = {str(a.id): a for _, a in top}
        new_consecutive: dict[str, int] = {}
        for atom_id_str in selected_ids:
            if atom_id_str in self._consecutive_selections:
                new_consecutive[atom_id_str] = self._consecutive_selections[atom_id_str] + 1
            else:
                new_consecutive[atom_id_str] = 1
        # 衰减未选中的
        for atom_id_str in self._consecutive_selections:
            if atom_id_str not in selected_ids:
                # 重置为 0
                pass
        self._consecutive_selections = new_consecutive

        cam = CurrentAttentionMemory(
            items=[a for _, a in top],
            scores={str(a.id): s for s, a in top},
            tick=pool._tick,
        )
        self._last_cam = cam
        self._selection_history.append(cam)

        logger.info(
            f"[Attention select] tick={pool._tick} "
            f"candidates={len(candidates)} budget={effective_budget} "
            f"selected={len(top)} top_score={top[0][0]:.3f}"
        )

        return cam

    def _effective_budget(self, cfg: AttentionConfig) -> int:
        """根据 NT 焦点调整有效 budget。"""
        # focus > 0 → budget 减少（更精准）
        # 简版：focus 减少 budget 不超过 50%
        # M0.4 暂未接入 NT；保留接口
        return cfg.budget

    def _score(self, atom: StimulusAtom, cfg: AttentionConfig) -> float:
        """5 通道加权评分。"""
        weights = cfg.weights

        # 通道 1：能量
        energy_score = min(1.0, atom.energy.total / 2.0)  # 归一化到 [0, 1]

        # 通道 2：近因
        recency_score = 1.0 / (1.0 + atom.age_ticks * 0.1)

        # 通道 3：奖惩相关（从 cache 读）
        atom_id_str = str(atom.id)
        if atom.source.value == "action":
            reward_score = self._reward_cache.get(atom_id_str, 0.0)
        else:
            reward_score = 0.0

        # 通道 4：新鲜度（连续选择次数反向）
        consecutive = self._consecutive_selections.get(atom_id_str, 0)
        novelty_score = 1.0 / (1.0 + consecutive * 0.5)

        # 通道 5：认知感受强度（从 cache 读）
        if atom.source.value == "feeling":
            feeling_score = self._feeling_cache.get(atom_id_str, 0.0)
        else:
            feeling_score = 0.0

        score = (
            weights["energy"] * energy_score
            + weights["recency"] * recency_score
            + weights["reward_relevance"] * reward_score
            + weights["novelty"] * novelty_score
            + weights["feeling_intensity"] * feeling_score
        )

        # 重复抑制
        if consecutive >= cfg.fatigue_consecutive_threshold:
            score *= cfg.fatigue_penalty  # 连续疲劳
        elif consecutive > 0:
            score *= cfg.repeat_penalty  # 上一轮选过

        return score

    def _update_caches(self, pool: StatePool) -> None:
        """更新 feeling 和 reward 缓存。"""
        for atom in pool.get_all():
            atom_id_str = str(atom.id)
            if atom.source.value == "feeling":
                # 感受强度从 content 解析（"feeling:dissonance:0.85"）
                parts = atom.content.split(":")
                if len(parts) >= 3:
                    try:
                        self._feeling_cache[atom_id_str] = float(parts[2])
                    except ValueError:
                        pass
            elif atom.source.value == "action":
                # 行动奖励从 energy.real 读
                self._reward_cache[atom_id_str] = atom.energy.real

    def get_selection_report(self) -> dict[str, Any]:
        """选择报告（为什么选中）。"""
        last = self._last_cam
        return {
            "last_cam_size": len(last.items) if last else 0,
            "last_cam_top_score": max(last.scores.values()) if last and last.scores else 0.0,
            "history_size": len(self._selection_history),
            "consecutive_selections": len(self._consecutive_selections),
            "top_n": self.effective_top_n,
            "budget": self.config.budget,
            "attention_mode": self.current_mode,
        }
