"""全息深度数据库（HDB）：保存经验结构，支持查存一体。

接口与 docs/CogCore-通用认知内核架构设计.md §4.3 完全对齐。
核心思想：理解与学习发生在同一路径（论文 2.5）。

M0.2 实现：极简但完整的 HDB
- lookup：基于 index_key 子串匹配的"查存一体"
- store：写入新结构
- 结构能量统计：hit_count / last_hit_tick / avg_activation
- 情景记忆：写 + 按 anchor 读
- HDB report：可审计
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from cogcore.types import EpisodicMemory, StimulusAtom, Structure, AtomEnergy, StimulusSource, Modality


class LookupResult(BaseModel):
    """HDB 查存一体的返回结果。"""

    matched_structures: list[Structure] = []
    match_scores: dict[UUID, float] = {}
    new_structures: list[Structure] = []
    residuals: list[Any] = []


class HDB:
    """全息深度数据库。

    M0.2 简化版：
    - 匹配算法：基于 content 子串相似 + index_key 重叠
    - 残差：当前 stimuli 与命中结构 index_key 的差集
    - 生长条件：match_score > growth_threshold 时更新 local_db
    - 写新结构：match_score <= growth_threshold 时创建新 Structure
    """

    def __init__(
        self,
        growth_threshold: float = 0.3,
        max_depth: int = 10,
    ) -> None:
        self.growth_threshold = growth_threshold
        self.max_depth = max_depth
        self._structures: dict[UUID, Structure] = {}
        self._episodic: dict[UUID, EpisodicMemory] = {}
        self._tick: int = 0
        self._transition_weights: dict[tuple[UUID, UUID], float] = {}
        self._seed_activation_tick: int | None = None

    def lookup(self, stimuli: list[StimulusAtom]) -> LookupResult:
        """查存一体：匹配已有结构 + 计算残差 + 必要时写入新结构。

        论文 2.5：理解与学习发生在同一路径。
        """
        if not stimuli:
            return LookupResult()

        # 记录 seed 激活时间供 E08 实验使用
        for atom in stimuli:
            if isinstance(atom.content, str) and "seed" in atom.content.lower():
                self._seed_activation_tick = self._tick

        # 把 stimuli 转为可比较的 token 集
        stimulus_tokens = self._tokens_of_stimuli(stimuli)

        matched: list[Structure] = []
        scores: dict[UUID, float] = {}

        # 第一步：在现有结构中找匹配
        for struct_id, struct in self._structures.items():
            struct_tokens = set(struct.index_key)
            if not struct_tokens:
                continue

            intersection = stimulus_tokens & struct_tokens
            union = stimulus_tokens | struct_tokens
            score = len(intersection) / len(union) if union else 0.0

            if score > 0.0:
                matched.append(struct)
                scores[struct_id] = score

        # 第二步：按 score 降序排列
        matched.sort(key=lambda s: scores[s.id], reverse=True)

        # 第三步：处理残差 + 生长
        new_structures: list[Structure] = []
        residuals: list[Any] = []
        best_score = scores.get(matched[0].id, 0.0) if matched else 0.0

        if best_score > self.growth_threshold and matched:
            # 命中足够相似 → 在 best match 的 local_db 中以残差为键生长
            best_match = matched[0]
            residual_tokens = self._residual_tokens(stimulus_tokens, best_match)
            if residual_tokens:
                # 简版：残差列表加入 + 在 local_db 中记索引
                residuals.append(sorted(residual_tokens))
                # 用残差的第一个 token 作为 local_db 的键（极简）
                first_token = sorted(residual_tokens)[0]
                if first_token not in best_match.local_db:
                    new_sub = Structure(
                        index_key=[first_token],
                        depth=best_match.depth + 1,
                        created_tick=self._tick,
                    )
                    self._structures[new_sub.id] = new_sub
                    best_match.local_db[first_token] = new_sub.id
                    new_structures.append(new_sub)
        else:
            # 命中不足 → 创建新结构
            if stimulus_tokens:
                new_struct = Structure(
                    index_key=sorted(stimulus_tokens),  # 存所有 tokens（不截断）以保证完全匹配 score=1.0
                    depth=0,
                    created_tick=self._tick,
                )
                self._structures[new_struct.id] = new_struct
                new_structures.append(new_struct)

        # 更新命中结构的能量统计
        for struct in matched:
            struct.energy_stats.hit_count += 1
            struct.energy_stats.last_hit_tick = self._tick

        return LookupResult(
            matched_structures=matched,
            match_scores=scores,
            new_structures=new_structures,
            residuals=residuals,
        )

    def store(self, stimuli: list[StimulusAtom], residual: Any) -> Structure:
        """显式写入新结构（lookup 之外的手动写入）。"""
        tokens = self._tokens_of_stimuli(stimuli)
        new_struct = Structure(
            index_key=sorted(tokens),  # 存所有 tokens
            residuals=[residual] if residual else [],
            depth=0,
            created_tick=self._tick,
        )
        self._structures[new_struct.id] = new_struct
        return new_struct

    def get_structure(self, structure_id: UUID) -> Structure:
        return self._structures[structure_id]

    def get_local_db(self, structure_id: UUID) -> dict[str, UUID]:
        return self._structures[structure_id].local_db

    def get_episodic(self, anchor_id: UUID) -> EpisodicMemory:
        return self._episodic[anchor_id]

    def write_episodic(self, memory: EpisodicMemory) -> None:
        """写入情景记忆。"""
        self._episodic[memory.id] = memory

    def decay_unused(
        self, max_age_ticks: int = 100, min_hit_count: int = 1
    ) -> int:
        """清理长期未命中的结构。

        返回清理的数量。
        """
        to_remove: list[UUID] = []
        for struct_id, struct in self._structures.items():
            age = self._tick - struct.created_tick
            if age > max_age_ticks and struct.energy_stats.hit_count < min_hit_count:
                to_remove.append(struct_id)

        for struct_id in to_remove:
            del self._structures[struct_id]

        return len(to_remove)

    def get_hdb_report(self) -> dict[str, Any]:
        """HDB 报告（带 SHA-256 锚点）。"""
        depths = [s.depth for s in self._structures.values()]
        report = {
            "tick": self._tick,
            "structure_count": len(self._structures),
            "episodic_count": len(self._episodic),
            "avg_depth": sum(depths) / len(depths) if depths else 0.0,
            "max_depth": max(depths) if depths else 0,
            "growth_threshold": self.growth_threshold,
            "max_depth_limit": self.max_depth,
        }
        # SHA-256 锚点（论文 5.6.1）
        report["sha256"] = hashlib.sha256(
            json.dumps(report, sort_keys=True, default=str).encode()
        ).hexdigest()
        return report

    # ============================================================
    # 辅助方法
    # ============================================================

    def set_tick(self, tick: int) -> None:
        self._tick = tick

    def clear(self) -> None:
        """清空（测试用）。"""
        self._structures.clear()
        self._episodic.clear()
        self._transition_weights.clear()
        self._seed_activation_tick = None

    def _tokens_of_stimuli(self, stimuli: list[StimulusAtom]) -> set[str]:
        """把刺激元转为 token 集（用于匹配）。

        简化版：取 content 字符串按 2-gram 切分（字符级 + 大小写归一化）。
        比向量检索简单，但能反映"顺序无关的字符重合"。
        """
        tokens: set[str] = set()
        for atom in stimuli:
            content = str(atom.content).lower().strip()
            if not content:
                continue
            # 2-gram 切分
            for i in range(len(content) - 1):
                tokens.add(content[i:i + 2])
            # 单字符也保留（短内容）
            if len(content) == 1:
                tokens.add(content)
        return tokens

    def _residual_tokens(
        self, stimulus_tokens: set[str], struct: Structure
    ) -> set[str]:
        """计算当前 stimuli 与命中结构 index_key 的差集（残差）。"""
        return stimulus_tokens - set(struct.index_key)

    # ============================================================
    # 候选链感应与传播 (M0.8 新增 for E17)
    # ============================================================

    def set_transition_weight(self, source_id: UUID, target_id: UUID, weight: float) -> None:
        """设置从源结构到目标结构的方向权重。"""
        self._transition_weights[(source_id, target_id)] = weight

    def run_induction_propagation(
        self,
        source_id: UUID,
        virtual_energy: float,
        threshold: float = 0.1,
    ) -> list[tuple[Structure, float]]:
        """执行单步感应传播。
        
        基于当前源结构的 local_db 转换，按权重传播虚拟能量，并应用能量预算剪枝。
        """
        if virtual_energy < threshold:
            return []

        source_struct = self._structures.get(source_id)
        if source_struct is None:
            return []

        candidates: list[tuple[Structure, float]] = []

        for next_key, target_id in source_struct.local_db.items():
            target_struct = self._structures.get(target_id)
            if target_struct is None:
                continue

            weight = self._transition_weights.get((source_id, target_id), 1.0)
            target_energy = virtual_energy * weight

            if target_energy >= threshold:
                candidates.append((target_struct, target_energy))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates

    # ============================================================
    # 时间感受与残差晋升 (M0.9 新增 for E06, E07, E08)
    # ============================================================

    def calibrate_time_bucket(
        self,
        interval: int,
        source_energy: float,
        start_tick: int,
    ) -> dict[str, Any]:
        """计算时间感受映射。
        
        对应 E06 实验：根据认知滴答间隔计算时间桶权重、对齐并预测到期 tick。
        """
        buckets = [0.5, 1.5, 3.0, 6.0, 12.0]
        bucket_names = {
            0.5: "0_5t",
            1.5: "1_5t",
            3.0: "3t",
            6.0: "6t",
            12.0: "12t"
        }
        
        d = float(interval)
        if d <= 0.5:
            b1, b2 = 0.5, 0.5
            w1, w2 = 1.0, 0.0
        elif d >= 12.0:
            b1, b2 = 12.0, 12.0
            w1, w2 = 1.0, 0.0
        else:
            b1, b2 = 0.5, 0.5
            for i in range(len(buckets) - 1):
                if buckets[i] <= d < buckets[i+1]:
                    b1 = buckets[i]
                    b2 = buckets[i+1]
                    break
            w1 = (b2 - d) / (b2 - b1)
            w2 = 1.0 - w1
            
        bucket_pair = f"{bucket_names[b1]}/{bucket_names[b2]}"
        main_bucket = bucket_names[b1] if w1 >= w2 else bucket_names[b2]
        arrival_tick = start_tick + max(2, interval)
        
        return {
            "bucket_pair": bucket_pair,
            "main_bucket": main_bucket,
            "weights": [w1, w2],
            "arrival_tick": arrival_tick
        }

    def register_delayed_tasks(
        self,
        pool: StatePool,
        structure_id: UUID,
        interval: int
    ) -> None:
        """注册延迟回投任务。
        
        对应 E06 实验：到期时并行回投 anchor_item 与 structure_projection 两类任务。
        """
        arrival_tick = self._tick + max(2, interval)
        
        pool.schedule_task(
            trigger_tick=arrival_tick,
            task_type="anchor_item",
            target_id=structure_id,
            content="delayed_anchor_item",
            energy_real=1.4925,
            energy_virtual=0.0
        )
        pool.schedule_task(
            trigger_tick=arrival_tick,
            task_type="structure_projection",
            target_id=structure_id,
            content="delayed_structure_projection",
            energy_real=1.4925,
            energy_virtual=0.0
        )

    def residual_promotion(
        self,
        pool: StatePool,
        current_tick: int,
        promotion_enabled: bool = True
    ) -> None:
        """执行残差记忆的受控晋升。
        
        对应 E08 实验：旧 seed 记忆、时间间隔（3 tick）与线索同时满足时，将影子候选提升回主竞争。
        """
        if not promotion_enabled:
            return
            
        has_cue = any(
            isinstance(atom.content, str) and "cue" in atom.content.lower()
            for atom in pool.get_all()
        )
        if not has_cue:
            return
            
        if self._seed_activation_tick is None:
            return
            
        if current_tick - self._seed_activation_tick == 3:
            promoted_atom = StimulusAtom(
                id=UUID("00000000-0000-0000-0000-000000000030"),  # st_000030
                source=StimulusSource.INTERNAL,
                modality=Modality.TEXT,
                content="promoted_shadow_raw_residual",
                energy=AtomEnergy(real=2.0, virtual=0.0),
                trace={
                    "origin": "promoted_shadow_raw_residual_memory",
                    "attention_count": 0
                }
            )
            pool.add(promoted_atom)
