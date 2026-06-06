"""M5.4 E25 — 叙事质量评估器。

输入：CogCore 生成的候选链（tick 序列的 CAM 快照）
输出：连贯性评分（0-1）+ 断裂点标记

评分维度：
- 主题一致性：相邻 tick 内容重叠度
- 因果连贯：行动-结果链完整性
- 信息增量：每 tick 是否有新信息

默认用确定性评分（无需 LLM），可选 Ollama judge。
"""
from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass
class NarrativeScore:
    """叙事质量评分结果。"""

    overall: float
    topic_consistency: float
    causal_coherence: float
    information_gain: float
    breakpoints: list[int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": round(self.overall, 3),
            "topic_consistency": round(self.topic_consistency, 3),
            "causal_coherence": round(self.causal_coherence, 3),
            "information_gain": round(self.information_gain, 3),
            "breakpoints": self.breakpoints,
        }


def _token_overlap(a: str, b: str) -> float:
    """两个字符串的 token 重叠率。"""
    if not a or not b:
        return 0.0
    ta = set(a.lower().split())
    tb = set(b.lower().split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def _has_causal_link(prev: dict, curr: dict) -> bool:
    """检查相邻 tick 是否有因果链（行动→结果）。"""
    prev_actions = prev.get("actions", [])
    curr_results = curr.get("results", [])
    if not prev_actions or not curr_results:
        return False
    # 简单启发：如果 curr 提到了 prev action 的关键词
    prev_keywords = set()
    for a in prev_actions:
        if isinstance(a, dict):
            prev_keywords.update(str(a.get("name", "")).lower().split())
        else:
            prev_keywords.update(str(a).lower().split())
    curr_text = " ".join(str(r) for r in curr_results).lower()
    return any(kw in curr_text for kw in prev_keywords if len(kw) > 2)


def _information_gain(prev: dict, curr: dict) -> float:
    """计算信息增量。"""
    prev_text = str(prev.get("cam", prev))
    curr_text = str(curr.get("cam", curr))
    overlap = _token_overlap(prev_text, curr_text)
    # 重叠低 = 信息增量高
    return 1.0 - overlap


def evaluate_narrative(tick_chain: list[dict[str, Any]]) -> NarrativeScore:
    """评估候选链叙事质量。

    Args:
        tick_chain: 每个元素是一个 tick 的快照 dict，至少含 cam/actions/results

    Returns:
        NarrativeScore
    """
    n = len(tick_chain)
    if n < 2:
        return NarrativeScore(
            overall=0.5,
            topic_consistency=0.5,
            causal_coherence=0.5,
            information_gain=0.5,
            breakpoints=[],
        )

    topic_scores = []
    causal_scores = []
    gain_scores = []
    breakpoints = []

    for i in range(1, n):
        prev = tick_chain[i - 1]
        curr = tick_chain[i]

        # 主题一致性
        prev_cam = str(prev.get("cam", prev))
        curr_cam = str(curr.get("cam", curr))
        tc = _token_overlap(prev_cam, curr_cam)
        topic_scores.append(tc)

        # 因果连贯
        cc = 1.0 if _has_causal_link(prev, curr) else 0.0
        causal_scores.append(cc)

        # 信息增量
        ig = _information_gain(prev, curr)
        gain_scores.append(ig)

        # 断裂检测：主题一致性 < 0.2 且 无因果链
        if tc < 0.2 and cc == 0.0:
            breakpoints.append(i)

    overall = round(
        (sum(topic_scores) / len(topic_scores) * 0.4
         + sum(causal_scores) / len(causal_scores) * 0.3
         + sum(gain_scores) / len(gain_scores) * 0.3),
        3,
    )

    return NarrativeScore(
        overall=overall,
        topic_consistency=round(sum(topic_scores) / len(topic_scores), 3),
        causal_coherence=round(sum(causal_scores) / len(causal_scores), 3),
        information_gain=round(sum(gain_scores) / len(gain_scores), 3),
        breakpoints=breakpoints,
    )
