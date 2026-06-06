"""M5.4 E25 — 叙事质量评估测试。"""
from __future__ import annotations

from experiments.E25.narrative_quality import evaluate_narrative


def test_coherent_chain_high_score():
    """连贯链评分 > 0.3（确定性评分，主题词重复度高）。"""
    chain = [
        {"cam": "weather today sunny warm", "actions": [{"name": "search weather"}], "results": []},
        {"cam": "weather today sunny warm 25 degrees", "actions": [], "results": ["search weather result sunny warm"]},
        {"cam": "weather today sunny warm tell user", "actions": [{"name": "respond weather"}], "results": []},
    ]
    score = evaluate_narrative(chain)
    assert score.overall > 0.3
    assert len(score.breakpoints) == 0


def test_broken_chain_low_score():
    """断裂链评分 < 0.4。"""
    chain = [
        {"cam": "user asks about weather", "actions": [{"name": "search_weather"}], "results": []},
        {"cam": "random quantum physics", "actions": [{"name": "compute_tensor"}], "results": []},
        {"cam": "stock market crash news", "actions": [], "results": []},
    ]
    score = evaluate_narrative(chain)
    assert score.overall < 0.4
    assert len(score.breakpoints) >= 1


def test_reproducible():
    """同输入同输出。"""
    chain = [
        {"cam": "hello", "actions": [], "results": []},
        {"cam": "hello world", "actions": [], "results": []},
    ]
    s1 = evaluate_narrative(chain)
    s2 = evaluate_narrative(chain)
    assert s1.overall == s2.overall
    assert s1.breakpoints == s2.breakpoints


def test_short_chain_default():
    """少于 2 个 tick 返回默认评分。"""
    score = evaluate_narrative([{"cam": "only one"}])
    assert score.overall == 0.5
    assert score.topic_consistency == 0.5
