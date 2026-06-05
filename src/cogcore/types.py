"""CogCore 基础数据类型。

接口与 docs/CogCore-通用认知内核架构设计.md 第 3 章完全对齐。
Pydantic BaseModel 用于 LangGraph State Schema 兼容性（见 cogcore_framework_research.md）。
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ============================================================
# 枚举
# ============================================================


class StimulusSource(str, Enum):
    """刺激元来源。"""

    EXTERNAL = "external"   # 外源输入（感受器）
    INTERNAL = "internal"   # 内源刺激（CAM 回流、感应生长）
    ACTION = "action"       # 行动节点
    FEELING = "feeling"     # 认知感受


class Modality(str, Enum):
    """输入模态。"""

    TEXT = "text"
    VISUAL = "visual"
    AUDIO = "audio"
    TOOL_STATE = "tool_state"


class ActionSource(str, Enum):
    """行动节点来源。"""

    INNATE = "innate"   # 先天编码（IESM）
    LEARNED = "learned" # 后天习得（教师反馈 + 感应生长）


class FeelingType(str, Enum):
    """认知感受类型。"""

    DISSONANCE = "dissonance"   # 违和感
    CORRECT = "correct"         # 正确感
    ANTICIPATION = "anticipation"  # 期待
    PRESSURE = "pressure"       # 压力
    FATIGUE = "fatigue"         # 疲劳


class Outcome(str, Enum):
    """行动结果。"""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    ERROR = "error"


# ============================================================
# Trace & Energy（子结构）
# ============================================================


class AtomTrace(BaseModel):
    """刺激元可追溯关系。"""

    origin: str
    matched_structures: list[UUID] = Field(default_factory=list)
    attention_count: int = 0
    action_events: list[UUID] = Field(default_factory=list)


class AtomEnergy(BaseModel):
    """刺激元能量。E_total = E_real + E_virtual。"""

    real: float = 0.0       # 现实证据
    virtual: float = 0.0    # 内源预测

    @property
    def total(self) -> float:
        return self.real + self.virtual


class EnergyStats(BaseModel):
    """结构能量统计。"""

    hit_count: int = 0
    last_hit_tick: int = 0
    avg_activation: float = 0.0


# ============================================================
# 5 个核心数据结构（与主文档第 3 章一一对应）
# ============================================================


class StimulusAtom(BaseModel):
    """刺激元：系统最小可参与认知对象。

    对应主文档 §3.1。
    """

    id: UUID = Field(default_factory=uuid4)
    source: StimulusSource
    content: Any
    modality: Modality = Modality.TEXT
    energy: AtomEnergy = Field(default_factory=AtomEnergy)
    age_ticks: int = 0
    birth_tick: int = 0
    trace: AtomTrace
    attributes: list["AttributeAtom"] = Field(default_factory=list)

    @property
    def packet_attribute_by_name(self) -> dict[str, Any]:
        """静态属性视图：从属性包注入的属性（binding_score == 0.0）。"""
        return {
            attr.attr_name: attr.attr_value
            for attr in self.attributes
            if attr.binding_score == 0.0
        }

    @property
    def bound_attribute_by_name(self) -> dict[str, Any]:
        """运行态属性视图：动态绑定的工具属性（binding_score > 0.0）。"""
        return {
            attr.attr_name: attr.attr_value
            for attr in self.attributes
            if attr.binding_score > 0.0
        }


class AttributeAtom(BaseModel):
    """属性刺激元：带锚点的刺激元，用于解决属性绑定问题。

    对应主文档 §3.2。
    """

    id: UUID = Field(default_factory=uuid4)
    anchor_id: UUID
    attr_name: str
    attr_value: Any
    binding_score: float = 0.0


class Structure(BaseModel):
    """结构：HDB 中保存的经验组织单元。

    对应主文档 §3.3。
    """

    id: UUID = Field(default_factory=uuid4)
    index_key: list[str] = Field(default_factory=list)
    residuals: list[Any] = Field(default_factory=list)
    local_db: dict[str, UUID] = Field(default_factory=dict)
    energy_stats: EnergyStats = Field(default_factory=EnergyStats)
    episodic_anchors: list[UUID] = Field(default_factory=list)
    created_tick: int = 0
    depth: int = 0


class EpisodicMemory(BaseModel):
    """情景记忆：具体经历的快照，作为审计锚点。

    对应主文档 §3.4。
    """

    id: UUID = Field(default_factory=uuid4)
    tick_range: tuple[int, int] = (0, 0)
    stimuli_snapshot: list[UUID] = Field(default_factory=list)
    action_taken: str = ""
    outcome: Outcome = Outcome.SUCCESS
    feeling_snapshot: dict[str, float] = Field(default_factory=dict)
    structure_refs: list[UUID] = Field(default_factory=list)


class ActionNode(BaseModel):
    """行动节点：可执行意图，可入池、可记忆、可奖惩塑形。

    对应主文档 §3.5。
    """

    id: UUID = Field(default_factory=uuid4)
    name: str
    drive: float = 0.0
    threshold: float = 1.0
    source: ActionSource = ActionSource.INNATE
    last_executed_tick: int = 0
    execution_count: int = 0
    reward_history: list[float] = Field(default_factory=list)
    punishment_history: list[float] = Field(default_factory=list)
    tool_mapping: str = ""
    in_pool: bool = False


# 解决 StimulusAtom.attributes 前向引用
StimulusAtom.model_rebuild()
