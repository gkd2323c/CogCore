"""M0.1 烟雾测试。

验证：
- 所有核心模块能 import
- 能实例化
- 一次 run_cycle 能跑通 10 阶段
- 每个阶段触发 NotImplementedError 被 _safe_call 捕获，pipeline 不崩溃
"""

from __future__ import annotations

import logging

from cogcore.adaptive_tuner import AdaptiveTuner
from cogcore.attention import Attention, AttentionConfig, CurrentAttentionMemory
from cogcore.cfs import CognitiveFeelingSystem, FeelingSignal
from cogcore.hdb import HDB, LookupResult
from cogcore.induction import InductionGrowth
from cogcore.nt import NTModulations, NeurotransmitterSystem
from cogcore.observability import Observatory
from cogcore.pipeline import run_cycle
from cogcore.sensors import SensorLayer, TextSensor
from cogcore.state_pool import EnergySummary, StatePool
from cogcore.tools import LongTermExperienceTools, ToolRegistry
from cogcore.types import (
    ActionNode,
    ActionSource,
    AttributeAtom,
    EpisodicMemory,
    Modality,
    Outcome,
    StimulusAtom,
    StimulusSource,
    Structure,
)
from cogcore.action_system import (
    ActionCandidate,
    ActionResult,
    ActionSystem,
    TeacherFeedback,
)

logging.basicConfig(level=logging.WARNING)


def test_imports():
    """所有 14 个核心模块都能 import。"""
    # 此函数体内的 import 全部成功即通过
    assert StatePool is not None
    assert HDB is not None
    assert InductionGrowth is not None
    assert Attention is not None
    assert AttentionConfig is not None
    assert CurrentAttentionMemory is not None
    assert NTModulations is not None
    assert NeurotransmitterSystem is not None
    assert CognitiveFeelingSystem is not None
    assert FeelingSignal is not None
    assert ActionNode is not None
    assert ActionCandidate is not None
    assert ActionResult is not None
    assert TeacherFeedback is not None
    assert ActionSystem is not None
    assert AdaptiveTuner is not None
    assert EnergySummary is not None
    assert LookupResult is not None
    assert SensorLayer is not None
    assert TextSensor is not None
    assert ToolRegistry is not None
    assert LongTermExperienceTools is not None
    assert Observatory is not None
    assert StimulusAtom is not None
    assert AttributeAtom is not None
    assert Structure is not None
    assert EpisodicMemory is not None
    # 枚举
    assert StimulusSource.EXTERNAL.value == "external"
    assert Modality.TEXT.value == "text"
    assert ActionSource.INNATE.value == "innate"
    assert Outcome.SUCCESS.value == "success"


def test_instantiate():
    """9 个核心模块都能实例化。"""
    pool = StatePool()
    hdb = HDB()
    induction = InductionGrowth(hdb)
    attention = Attention()
    nt_sys = NeurotransmitterSystem()
    cfs = CognitiveFeelingSystem()
    action_sys = ActionSystem()
    tuner = AdaptiveTuner()
    sensors = SensorLayer()
    assert pool is not None
    assert hdb is not None
    assert induction is not None
    assert attention is not None
    assert nt_sys is not None
    assert cfs is not None
    assert action_sys is not None
    assert tuner is not None
    assert sensors is not None


def test_run_cycle_skeleton():
    """一次 run_cycle 能跑通 10 阶段，每个阶段触发 NotImplementedError 但不崩溃。"""
    report = run_cycle(
        raw_input="明天上海出门，帮我看看要不要带伞",
        modality="text",
        tick=0,
    )

    # 10 阶段全部完成
    assert len(report.stages_completed) == 10, (
        f"期望 10 阶段完成，实际 {len(report.stages_completed)}"
    )

    # 阶段名称符合预期
    expected = [
        "stage_1_sensor_input",
        "stage_2_state_pool_maintenance",
        "stage_3_hdb_lookup",
        "stage_4_induction_growth",
        "stage_5_cfs_evaluate",
        "stage_6_attention_select",
        "stage_7_nt_update",
        "stage_8_action_evaluate_and_execute",
        "stage_9_episodic_write",
        "stage_10_adaptive_tune",
    ]
    assert report.stages_completed == expected


def test_run_cycle_with_explicit_modules():
    """传入已实例化的模块也能跑通。"""
    pool = StatePool()
    hdb = HDB()
    induction = InductionGrowth(hdb)
    attention = Attention()
    cfs = CognitiveFeelingSystem()
    nt_sys = NeurotransmitterSystem()
    action_sys = ActionSystem()
    tuner = AdaptiveTuner()

    report = run_cycle(
        raw_input="测试输入",
        tick=42,
        pool=pool,
        hdb=hdb,
        induction=induction,
        attention=attention,
        cfs=cfs,
        nt_sys=nt_sys,
        action_sys=action_sys,
        tuner=tuner,
    )
    assert report.tick == 42
    assert len(report.stages_completed) == 10


def test_observatory_hash():
    """Observatory 的 SHA-256 哈希工具可用。"""
    report = {"tick": 0, "stages": ["a", "b", "c"]}
    h = Observatory.hash_report(report)
    assert len(h) == 64  # SHA-256 hex
    # 同样的输入产生同样的哈希
    assert h == Observatory.hash_report(report)
