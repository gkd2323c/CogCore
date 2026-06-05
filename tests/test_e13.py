import os
import json
import pytest
from cogcore.types import StimulusAtom, Modality, AtomEnergy, StimulusSource, FeelingType
from cogcore.state_schema import CogCoreState
from cogcore.llm_bridge import LLMBridge
from cogcore.observability import Observatory
from cogcore.hdb import HDB
from cogcore.cfs import FeelingSignal


def test_llm_bridge_build_context_packet():
    """测试 build_context_packet 是否成功输出所有 8 类可审计字段的标题。"""
    # 构造一个模拟 state
    state = CogCoreState(
        tick=5,
        raw_input="天气怎么样",
        modality="text",
    )
    
    # 注入一些 feelings 与 atoms 验证
    state.feeling_signals.append(FeelingSignal(
        type=FeelingType.CORRECT,
        intensity=0.8,
        tick=5
    ))
    
    llm = LLMBridge()
    packet = llm.build_context_packet(state.model_dump(), max_tokens=1000)
    
    assert "=== COGCORE MIND PROJECTION CONTEXT ===" in packet
    assert "[CURRENT INPUT]" in packet
    assert "天气怎么样" in packet
    assert "[ENERGY STATE]" in packet
    assert "[NEUROTRANSMITTERS]" in packet
    assert "[COGNITIVE FEELINGS]" in packet
    assert "- Feeling: correct (Intensity: 0.80)" in packet
    assert "[ATTENTION FOCUS & ACTIVE MEMORIES]" in packet
    assert "[MEMORY ANCHORS & SOURCES]" in packet
    assert "[ACTION CANDIDATES & DRIVES]" in packet
    assert "[PROMPT INSTRUCTIONS]" in packet


def test_observatory_methods():
    """测试 Observatory 方法能够正常记录与快照、哈希状态。"""
    state_1 = CogCoreState(tick=0, raw_input="输入1")
    state_2 = CogCoreState(tick=1, raw_input="输入2")
    
    hdb = HDB()
    obs = Observatory(states=[state_1, state_2], hdb=hdb)
    
    # get_tick_report
    rep_0 = obs.get_tick_report(0)
    assert rep_0["raw_input"] == "输入1"
    assert "hash" in rep_0
    
    rep_1 = obs.get_tick_report(1)
    assert rep_1["raw_input"] == "输入2"
    
    # get_state_snapshot
    snap = obs.get_state_snapshot()
    assert snap["tick"] == 1
    assert snap["raw_input"] == "输入2"
    assert "hash" in snap
    
    # get_structure_graph
    graph_rep = obs.get_structure_graph()
    assert "structure_count" in graph_rep
    
    # get_energy_timeline
    timeline = obs.get_energy_timeline(2)
    assert len(timeline) == 2
    assert timeline[0]["tick"] == 0
    assert timeline[1]["tick"] == 1
    
    # export_experiment_data
    temp_path = "experiments/E13/tables/_temp_test_obs.json"
    obs.export_experiment_data(temp_path)
    assert os.path.exists(temp_path)
    with open(temp_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 2
    assert data[0]["tick"] == 0
    # 清理
    os.remove(temp_path)


def test_e13_experiment_metrics():
    """通过读取 E13 实验生成的 JSON 文件验证指标是否达标。"""
    summary_path = "experiments/E13/tables/summary.json"
    assert os.path.exists(summary_path), "E13 summary.json 不存在，请先运行实验脚本"
    
    with open(summary_path, "r", encoding="utf-8") as f:
        summary_data = json.load(f)
        
    metrics = summary_data["metrics"]
    assert metrics["total_cases"] == 48
    
    # 校验 AP、Summary 和 RAG 平均字段数
    assert abs(metrics["avg_ap_fields"] - 7.750) < 1e-5
    assert abs(metrics["avg_summary_fields"] - 0.750) < 1e-5
    assert abs(metrics["avg_rag_fields"] - 1.250) < 1e-5
    
    # 优势值校验
    assert abs(metrics["ap_vs_summary_advantage"] - 7.000) < 1e-5
    assert abs(metrics["ap_vs_rag_advantage"] - 6.500) < 1e-5
    
    # 命中率校验
    assert abs(metrics["ap_hit_rate"] - 1.000) < 1e-5
    assert abs(metrics["rag_hit_rate"] - 0.500) < 1e-5
    assert abs(metrics["rag_mis_rate"] - 0.250) < 1e-5
