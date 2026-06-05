"""LLM Bridge：与 LLM 解释层的接口契约。

接口与 docs/CogCore-通用认知内核架构设计.md §6.1.5 完全对齐。
论文 5.6.1 PA 双层结构：AP 提供长期状态，LLM 提供语言表达 + 工具编排 + 安全审查。
"""

from __future__ import annotations

import logging
from typing import Any

from cogcore.types import StimulusAtom, Modality, AtomEnergy, StimulusSource

logger = logging.getLogger(__name__)


class LLMBridge:
    """CogCore ↔ LLM 双向桥接。

    - build_context_packet：CogCore 状态 → LLM 可理解的 prompt
    - parse_llm_output：LLM 输出 → 认知输入
    - queue_teacher_feedback / merge_pending_teacher_feedback：教师反馈延迟合流
    - teacher_gate_should_wake：reinforced_agency 模式的主动唤醒门控
    """

    def build_context_packet(self, tick_report: dict, max_tokens: int) -> str:
        """CogCore → LLM：将认知状态翻译为 LLM 可理解的上下文。
        
        包含了 E13 要求的 8 类可审计信息：
        1. 当前输入 (Current Input)
        2. 能量摘要 (Energy Summary)
        3. 记忆目标 (Memory Targets)
        4. 记忆来源 (Memory Sources)
        5. 认知感受 (Cognitive Feelings)
        6. 情绪递质 (Neurotransmitters)
        7. 行动倾向 (Action Drives)
        8. 提示投影 (Prompt Projection)
        """
        raw_input = tick_report.get("raw_input", "")

        # 1. 情绪递质 (Neurotransmitters)
        nt = tick_report.get("nt_values", {})
        def get_val(obj, key, default=0.0):
            if hasattr(obj, key):
                return getattr(obj, key)
            if isinstance(obj, dict):
                return obj.get(key, default)
            return default

        focus = get_val(nt, "focus")
        arousal = get_val(nt, "arousal")
        caution = get_val(nt, "caution")
        exploration = get_val(nt, "exploration")
        fatigue = get_val(nt, "fatigue")
        stability = get_val(nt, "stability")

        # 2. 能量摘要 (Energy Summary)
        pool_snap = tick_report.get("pool_snapshot", {})
        summary = {}
        if pool_snap:
            if hasattr(pool_snap, "energy_summary"):
                es = pool_snap.energy_summary
                if hasattr(es, "model_dump"):
                    summary = es.model_dump()
                else:
                    summary = dict(es)
            elif isinstance(pool_snap, dict):
                summary = pool_snap.get("energy_summary", {})

        active_count = summary.get("active_count", 0)
        total_energy = summary.get("total_energy", 0.0)
        cognitive_pressure = summary.get("cognitive_pressure", 0.0)

        # 3. 记忆目标 (Memory Targets) - 来自 CAM (Current Attention Memory)
        cam = tick_report.get("cam")
        cam_items = []
        if cam:
            items = getattr(cam, "items", []) if hasattr(cam, "items") else cam.get("items", [])
            for item in items:
                content = getattr(item, "content", "") if hasattr(item, "content") else item.get("content", "")
                item_id = getattr(item, "id", "") if hasattr(item, "id") else item.get("id", "")
                source = getattr(item, "source", "") if hasattr(item, "source") else item.get("source", "")
                if hasattr(source, "value"):
                    source = source.value
                val_real = 0.0
                val_virt = 0.0
                energy = getattr(item, "energy", None) if hasattr(item, "energy") else item.get("energy", None)
                if energy:
                    val_real = getattr(energy, "real", 0.0) if hasattr(energy, "real") else energy.get("real", 0.0)
                    val_virt = getattr(energy, "virtual", 0.0) if hasattr(energy, "virtual") else energy.get("virtual", 0.0)
                cam_items.append(
                    f"- [ID: {item_id}] Content: '{content}' (Source: {source}, Real: {val_real:.2f}, Virtual: {val_virt:.2f})"
                )

        # 4. 记忆来源 (Memory Sources) - 来自 HDB 快照与 matching scores
        hdb = tick_report.get("hdb_snapshot", {})
        def get_list(obj, key):
            if hasattr(obj, key):
                return getattr(obj, key)
            if isinstance(obj, dict):
                return obj.get(key, [])
            return []

        matched_structs = get_list(hdb, "matched_structure_ids")
        new_structs = get_list(hdb, "new_structure_ids")
        match_scores = {}
        if hdb:
            if hasattr(hdb, "match_scores"):
                match_scores = hdb.match_scores
            elif isinstance(hdb, dict):
                match_scores = hdb.get("match_scores", {})

        # 5. 认知感受 (Cognitive Feelings)
        feelings = tick_report.get("feeling_signals", [])
        feeling_list = []
        for f in feelings:
            f_type = getattr(f, "type", "") if hasattr(f, "type") else f.get("type", "")
            if hasattr(f_type, "value"):
                f_type = f_type.value
            intensity = getattr(f, "intensity", 0.0) if hasattr(f, "intensity") else f.get("intensity", 0.0)
            feeling_list.append(f"- Feeling: {f_type} (Intensity: {intensity:.2f})")

        # 6. 行动倾向 (Action Drives)
        # 提取 new_atoms 中关于 action 的反馈信息，或从其它字段提取行动倾向
        new_atoms = tick_report.get("new_atoms", [])
        action_atoms = []
        for a in new_atoms:
            source = getattr(a, "source", "") if hasattr(a, "source") else a.get("source", "")
            if hasattr(source, "value"):
                source = source.value
            if source == "action":
                content = getattr(a, "content", "") if hasattr(a, "content") else a.get("content", "")
                val_real = 0.0
                energy = getattr(a, "energy", None) if hasattr(a, "energy") else a.get("energy", None)
                if energy:
                    val_real = getattr(energy, "real", 0.0) if hasattr(energy, "real") else energy.get("real", 0.0)
                action_atoms.append(f"- Action: {content} (Feedback Energy: {val_real:.2f})")

        # 拼装上下文 Prompt
        packet = []
        packet.append("=== COGCORE MIND PROJECTION CONTEXT ===")
        packet.append(f"[CURRENT INPUT]\n{raw_input}\n")

        packet.append("[ENERGY STATE]")
        packet.append(f"Active Atoms Count: {active_count}")
        packet.append(f"Total Cognitive Energy: {total_energy:.3f}")
        packet.append(f"Cognitive Pressure: {cognitive_pressure:.3f}\n")

        packet.append("[NEUROTRANSMITTERS]")
        packet.append(f"Focus: {focus:.3f}, Arousal: {arousal:.3f}, Caution: {caution:.3f}")
        packet.append(f"Exploration: {exploration:.3f}, Fatigue: {fatigue:.3f}, Stability: {stability:.3f}\n")

        packet.append("[COGNITIVE FEELINGS]")
        if feeling_list:
            packet.append("\n".join(feeling_list))
        else:
            packet.append("No active cognitive feelings.")
        packet.append("")

        packet.append("[ATTENTION FOCUS & ACTIVE MEMORIES]")
        if cam_items:
            packet.append("\n".join(cam_items))
        else:
            packet.append("No active attention focus items.")
        packet.append("")

        packet.append("[MEMORY ANCHORS & SOURCES]")
        if matched_structs:
            packet.append(f"Matched Structures: {', '.join(matched_structs)}")
            scores_str = [f"{k}: {v:.2f}" for k, v in match_scores.items()]
            packet.append(f"Match Scores: {', '.join(scores_str)}")
        else:
            packet.append("No matched memory structures in HDB.")
        if new_structs:
            packet.append(f"Newly Written Structures: {', '.join(new_structs)}")
        packet.append("")

        packet.append("[ACTION CANDIDATES & DRIVES]")
        if action_atoms:
            packet.append("\n".join(action_atoms))
        else:
            packet.append("No recent actions triggered in this tick.")
        packet.append("")

        packet.append("[PROMPT INSTRUCTIONS]")
        packet.append(
            "Please respond as the Agent, integrating the above cognitive state, emotional tone, and active memory items to ensure personality continuity and context awareness."
        )

        full_text = "\n".join(packet)

        # 简单 Token 截断 (1 token ≈ 4 字符)
        max_chars = max_tokens * 4
        if len(full_text) > max_chars:
            full_text = full_text[:max_chars] + "\n... [TRUNCATED]"

        return full_text

    def parse_llm_output(self, llm_response: str) -> list[StimulusAtom]:
        """将 LLM 输出解析为认知输入（刺激元）。"""
        words = [w for w in llm_response.split() if w]
        atoms = []
        for word in words:
            atoms.append(
                StimulusAtom(
                    content=word,
                    source=StimulusSource.INTERNAL,
                    modality=Modality.TEXT,
                    energy=AtomEnergy(real=0.5, virtual=0.5),
                    age_ticks=0,
                    birth_tick=0,
                    trace={"origin": "llm_output_parser"},
                )
            )
        return atoms

    def queue_teacher_feedback(self, labels: dict) -> None:
        """暂存教师反馈。"""
        # 在 E13 中，我们直接调用 ActionSystem 的 queue_teacher_feedback，此处提供占位实现
        pass

    def merge_pending_teacher_feedback(self) -> list[dict]:
        """合并教师反馈。"""
        return []

    def teacher_gate_should_wake(self, event: dict) -> bool:
        """教师门控。"""
        return True
