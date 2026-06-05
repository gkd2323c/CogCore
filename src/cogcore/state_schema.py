"""CogCoreState：LangGraph 状态 schema + Reducer 契约。

⚠️ 关键陷阱：嵌套对象的"脑损伤式"数据丢失 + Fluent API 双重累加
====================================================================

陷阱 T1（脑损伤式丢失）：
    LangGraph 节点返回的是**部分更新（patch）**，不是整个新 State。默认合并会
    **覆盖整个嵌套字段**——节点只返回子字段时，其他子字段被默认合并清空。

陷阱 T5（Fluent API 双重累加）：⚠️ 2026-06-05 用户捕获
    Pydantic 模式下的"链式调用"辅助方法（如 `state.append_atoms([a])`）如果返回完整
    State 实例，会触发 LangGraph Reducer 的**双重累加**：

        state.new_atoms = [A]
        patch = state.append_atoms([B])
        # patch.new_atoms = [A, B]  (Pydantic 已做累加)
        return patch  # LangGraph 拿到 [A, B]
        # Reducer: existing [A] + update [A, B] = [A, A, B]  💥

    修复方案：辅助方法**不返回 State**，而是返回 `StateUpdater`——一个累积
    patch dict 的上下文对象。链式调用累积增量，最后 `.to_patch()` 一次性返回 dict。

正确模式：
```python
def stage_node(state: CogCoreState) -> dict:
    return (
        make_updater(state)
        .patch_nt_values(focus=0.5)         # nt_values 整体替换
        .append_atoms([atom_a, atom_b])     # new_atoms 增量（不预先累加）
        .append_stage("stage_3_hdb_lookup") # stages_log 增量
        .to_patch()                          # → 返回 dict，LangGraph 接管 Reducer
    )
```

为什么这样安全：
- `append_atoms` 在 `StateUpdater` 内**只记录"我要加这批"**——不做累加
- `patch_nt_values` 返回**整个新对象**（model_copy 深合并），不会丢字段
- 节点最终返回 dict，LangGraph 自动应用 Reducer：
    - new_atoms: add reducer → existing + update（只累加一次）
    - nt_values: 整体替换（不会被部分 dict 覆盖）
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Any

from pydantic import BaseModel, Field

from cogcore.attention import CurrentAttentionMemory
from cogcore.cfs import FeelingSignal
from cogcore.nt import NTModulations
from cogcore.state_pool import EnergySummary
from cogcore.types import StimulusAtom


# ============================================================
# 快照类型（嵌套对象字段的载体）
# ============================================================


class StatePoolSnapshot(BaseModel):
    """状态池快照。"""

    energy_summary: EnergySummary = Field(default_factory=EnergySummary)
    active_atom_ids: list[str] = Field(default_factory=list)


class HDBSnapshot(BaseModel):
    """HDB 查存结果快照。"""

    matched_structure_ids: list[str] = Field(default_factory=list)
    match_scores: dict[str, float] = Field(default_factory=dict)
    new_structure_ids: list[str] = Field(default_factory=list)
    residual_count: int = 0


# ============================================================
# CogCoreState（Pydantic 模式）
# ============================================================


class CogCoreState(BaseModel):
    """LangGraph StateGraph 状态 schema。

    字段类型规则：
    - 标量（int / str / bool）：默认 replacement
    - 嵌套对象（BaseModel）：默认 replacement（整个对象替换，天然安全）
    - 列表：用 `Annotated[list, add]` 显式声明 add reducer
    """

    # === 基础元数据 ===
    tick: int = 0
    raw_input: str = ""
    modality: str = "text"

    # === 顶层快照（嵌套对象，整体替换）===
    pool_snapshot: StatePoolSnapshot = Field(default_factory=StatePoolSnapshot)
    hdb_snapshot: HDBSnapshot = Field(default_factory=HDBSnapshot)
    nt_values: NTModulations = Field(default_factory=NTModulations)
    cam: CurrentAttentionMemory | None = None

    # === 列表字段（用 Annotated + add Reducer 累加）===
    new_atoms: Annotated[list[StimulusAtom], add] = Field(default_factory=list)
    grown_atoms: Annotated[list[StimulusAtom], add] = Field(default_factory=list)
    feeling_signals: Annotated[list[FeelingSignal], add] = Field(default_factory=list)
    stages_log: Annotated[list[str], add] = Field(default_factory=list)
    error_log: Annotated[list[str], add] = Field(default_factory=list)

    # === 哨兵 ===
    should_continue: bool = True


# ============================================================
# StateUpdater：Fluent API 但不返回 state
# ============================================================


class StateUpdater:
    """累积 patch dict 的上下文对象。

    链式调用 = 累积 patch（不修改 state，不预累加）。
    最后 `.to_patch()` 返回 dict，LangGraph 应用 Reducer。
    """

    def __init__(self, state: CogCoreState) -> None:
        # 读时用 state，写时只累积 patch
        self._state = state
        self._patch: dict[str, Any] = {}

    # ---- 嵌套对象字段（model_copy 深合并，但只返回新对象引用，不预累加）----

    def patch_nt_values(self, **kwargs: Any) -> "StateUpdater":
        """更新 NTModulations 的子字段（不预累加，因为是 replacement 字段）。

        实际行为：把整个新 nt_values 对象记到 patch。
        LangGraph 看到顶层 key 是 `nt_values`，默认整体替换。
        """
        new_nt = self._state.nt_values.model_copy(update=kwargs)
        self._patch["nt_values"] = new_nt
        return self

    def patch_pool_snapshot(self, **kwargs: Any) -> "StateUpdater":
        """更新 StatePoolSnapshot 的子字段。"""
        new_snapshot = self._state.pool_snapshot.model_copy(update=kwargs)
        self._patch["pool_snapshot"] = new_snapshot
        return self

    def patch_hdb_snapshot(self, **kwargs: Any) -> "StateUpdater":
        """更新 HDBSnapshot 的子字段。"""
        new_snapshot = self._state.hdb_snapshot.model_copy(update=kwargs)
        self._patch["hdb_snapshot"] = new_snapshot
        return self

    def set_cam(self, cam: CurrentAttentionMemory | None) -> "StateUpdater":
        """设置 CAM（替换）。"""
        self._patch["cam"] = cam
        return self

    # ---- 列表字段（只记录增量，不预累加）----

    def append_atoms(self, atoms: list[StimulusAtom]) -> "StateUpdater":
        """把 atoms 记到 patch['new_atoms'] 增量。

        ⚠️ 关键：不与现有 atoms 拼接。
        LangGraph 拿到 patch 后，add reducer 会做 `existing + patch` 合并。
        如果我们预先拼接，LangGraph 会再拼一次，导致 [A, A, B] 双重累加。
        """
        # 关键：检查是否已有同 key 的 patch；如果有，拼接（patch 内可累加）
        # 但不与 state 现有值拼接（state 现有值由 LangGraph 接管）
        existing_patch = self._patch.get("new_atoms", [])
        self._patch["new_atoms"] = existing_patch + list(atoms)
        return self

    def append_grown(self, atoms: list[StimulusAtom]) -> "StateUpdater":
        existing_patch = self._patch.get("grown_atoms", [])
        self._patch["grown_atoms"] = existing_patch + list(atoms)
        return self

    def append_feelings(self, signals: list[FeelingSignal]) -> "StateUpdater":
        existing_patch = self._patch.get("feeling_signals", [])
        self._patch["feeling_signals"] = existing_patch + list(signals)
        return self

    def append_stage(self, name: str) -> "StateUpdater":
        existing_patch = self._patch.get("stages_log", [])
        self._patch["stages_log"] = existing_patch + [name]
        return self

    def append_error(self, message: str) -> "StateUpdater":
        existing_patch = self._patch.get("error_log", [])
        self._patch["error_log"] = existing_patch + [message]
        return self

    # ---- 标量字段（替换）----

    def set_tick(self, tick: int) -> "StateUpdater":
        self._patch["tick"] = tick
        return self

    def set_should_continue(self, value: bool) -> "StateUpdater":
        self._patch["should_continue"] = value
        return self

    # ---- 输出 ----

    def to_patch(self) -> dict:
        """返回累积的 patch dict。节点直接 return 这个。

        ⚠️ 深拷贝：避免外部修改 patch 中的 list 污染内部状态。
        """
        import copy

        return copy.deepcopy(self._patch)

    def __bool__(self) -> bool:
        # 允许 `if updater:` 判断是否有内容
        return bool(self._patch)


def make_updater(state: CogCoreState) -> StateUpdater:
    """节点函数的入口：返回 StateUpdater 供链式调用。"""
    return StateUpdater(state)


# ============================================================
# 自定义 Reducer 示例
# ============================================================


def merge_cam(
    existing: CurrentAttentionMemory | None,
    update: CurrentAttentionMemory | None,
) -> CurrentAttentionMemory | None:
    """CAM 合并：update 总是替换 existing。"""
    if update is None:
        return existing
    return update


def attention_budget_reducer(
    existing: int, update: int | None
) -> int:
    """注意力预算 clamp。"""
    if update is None:
        return max(0, existing)
    return max(0, min(20, update))


# ============================================================
# 节点返回值的 4 种错误模式（必须避免）
# ============================================================

# 错误 1：返回部分嵌套 dict —— 子字段丢失
#     return {"nt_values": {"focus": 0.5}}  # ✗ 整个 nt_values 被替换为 {"focus": 0.5}
#
# 错误 2：返回未声明字段 —— 静默丢失
#     return {"new_atom": some_atom}  # ✗ 拼写错误
#
# 错误 3：返回完整 CogCoreState（陷阱 T5）—— 双重累加
#     return state.append_atoms([atom_b])  # ✗ patch.new_atoms=[A,B] + Reducer + existing=[A] = [A,A,B]
#
# 错误 4：跨节点修改全局 —— 破坏可重入
#     import cogcore.global_state; global_state.x = 1  # ✗


# ============================================================
# 节点返回值的 4 种正确模式
# ============================================================

# 正确 1：直接返回 patch dict
#     def node(state):
#         return {"nt_values": new_nt_modulations}
#
# 正确 2：嵌套对象用 StateUpdater.patch_*（model_copy + 不预累加）
#     def node(state):
#         return make_updater(state).patch_nt_values(focus=0.5).to_patch()
#
# 正确 3：列表 append（patch 内可拼接，但绝不与 state 现有值拼接）
#     def node(state):
#         return {"new_atoms": [atom1, atom2]}  # add reducer 接管累加
#
# 正确 4：链式 StateUpdater（推荐）
#     def node(state):
#         return (
#             make_updater(state)
#             .patch_nt_values(focus=0.5)
#             .append_atoms([atom_a])
#             .append_stage("stage_3")
#             .to_patch()
#         )
