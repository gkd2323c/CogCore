"""状态池（State Pool）：维护当前认知场，管理能量衰减、竞争和生命周期。

接口与 docs/CogCore-通用认知内核架构设计.md §4.2 完全对齐。
论文公式（附录 B）：
    E(t+1) = λ·E(t) + I(t) - D(t)
    P(i,t) = |E_r(i,t) - E_v(i,t)|

M0.2 实现：极简但完整的 StatePool，支持 E01/E02（结构学习）的查存一体基础。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from cogcore.types import StimulusAtom, AttributeAtom, Modality, StimulusSource, AtomEnergy


class EnergySummary(BaseModel):
    """状态池能量摘要。"""

    total_energy: float = 0.0
    real_energy: float = 0.0
    virtual_energy: float = 0.0
    active_count: int = 0
    cognitive_pressure: float = 0.0


class StatePool:
    """当前认知场 + 能量账本。

    关键不变量：
    - `_atoms` 是 dict（UUID → StimulusAtom），不是全局可变对象的间接引用
    - 所有修改方法都是「纯函数式」：返回新对象或就地修改但日志完整
    - `get_state_report()` 的输出必须带 SHA-256 锚点（论文 5.6.1）
    """

    def __init__(
        self,
        lambda_real: float = 0.85,
        lambda_virtual: float = 0.75,
        max_atoms: int = 200,
        min_energy_cleanup: float = 0.01,
    ) -> None:
        self.lambda_real = lambda_real
        self.lambda_virtual = lambda_virtual
        self.max_atoms = max_atoms
        self.min_energy_cleanup = min_energy_cleanup
        self._atoms: dict[UUID, StimulusAtom] = {}
        self._tick: int = 0
        self._attention_boosted: set[UUID] = set()
        self._inhibited: set[UUID] = set()
        self._delayed_tasks: list[dict] = []

    # ============================================================
    # 核心方法
    # ============================================================

    def add(self, atom: StimulusAtom) -> None:
        """添加刺激元到状态池。

        论文 4.7.1：状态池维护阶段调用。
        - 累加器：能量从 I_external 注入
        - 如果超过 max_atoms，按能量从低到高淘汰（情景记忆锚点豁免）

        M0.2 简化版：直接加入，不做容量管理（容量留给 M0.3 实现）。
        """
        self._atoms[atom.id] = atom

    def get_all(self) -> list[StimulusAtom]:
        """返回所有活跃刺激元。"""
        return list(self._atoms.values())

    def get_by_energy(self, min_energy: float) -> list[StimulusAtom]:
        """按能量阈值过滤。"""
        return [
            atom for atom in self._atoms.values()
            if atom.energy.total >= min_energy
        ]

    def decay(self) -> None:
        """按 λ_real / λ_virtual 执行一轮能量衰减。

        公式：E_real(t+1) = λ_real * E_real(t)
              E_virtual(t+1) = λ_virtual * E_virtual(t)
        """
        for atom in self._atoms.values():
            atom.energy.real *= self.lambda_real
            atom.energy.virtual *= self.lambda_virtual
            atom.age_ticks += 1

    def cleanup(
        self, min_energy: float | None = None, max_age: int | None = None
    ) -> list[StimulusAtom]:
        """清理低于阈值或过期的刺激元。

        返回被清理的对象列表（用于审计）。

        M0.2 简化版：使用实例默认 min_energy_cleanup。
        """
        threshold = min_energy if min_energy is not None else self.min_energy_cleanup
        age_limit = max_age if max_age is not None else 200

        evicted: list[StimulusAtom] = []
        to_remove: list[UUID] = []
        for atom_id, atom in self._atoms.items():
            if atom.energy.total < threshold or atom.age_ticks > age_limit:
                to_remove.append(atom_id)
                evicted.append(atom)

        for atom_id in to_remove:
            del self._atoms[atom_id]

        return evicted

    def get_energy_summary(self) -> EnergySummary:
        """返回状态池能量摘要。

        认知压 P = Σ|E_real - E_virtual| / N_active（按对象归一化）。
        """
        if not self._atoms:
            return EnergySummary()

        real_total = sum(atom.energy.real for atom in self._atoms.values())
        virtual_total = sum(atom.energy.virtual for atom in self._atoms.values())
        total = real_total + virtual_total
        cognitive_pressure = sum(
            abs(atom.energy.real - atom.energy.virtual)
            for atom in self._atoms.values()
        ) / len(self._atoms)

        return EnergySummary(
            total_energy=total,
            real_energy=real_total,
            virtual_energy=virtual_total,
            active_count=len(self._atoms),
            cognitive_pressure=cognitive_pressure,
        )

    def apply_attention_boost(
        self, atom_ids: list[UUID], factor: float
    ) -> None:
        """注意力增益：提高指定原子的能量。"""
        for atom_id in atom_ids:
            if atom_id in self._atoms:
                atom = self._atoms[atom_id]
                atom.energy.real *= 1.0 + factor
                atom.energy.virtual *= 1.0 + factor
                self._attention_boosted.add(atom_id)

    def apply_inhibition(
        self, atom_ids: list[UUID], factor: float
    ) -> None:
        """注意力抑制：降低指定原子的能量。"""
        for atom_id in atom_ids:
            if atom_id in self._atoms:
                atom = self._atoms[atom_id]
                atom.energy.real *= max(0.0, 1.0 - factor)
                atom.energy.virtual *= max(0.0, 1.0 - factor)
                self._inhibited.add(atom_id)

    def get_state_report(self) -> dict[str, Any]:
        """返回可审计状态快照（论文 5.6.1 观测台要求）。"""
        summary = self.get_energy_summary()
        return {
            "tick": self._tick,
            "active_count": summary.active_count,
            "total_energy": summary.total_energy,
            "real_energy": summary.real_energy,
            "virtual_energy": summary.virtual_energy,
            "cognitive_pressure": summary.cognitive_pressure,
            "attention_boosted_count": len(self._attention_boosted),
            "inhibited_count": len(self._inhibited),
            "lambda_real": self.lambda_real,
            "lambda_virtual": self.lambda_virtual,
            "max_atoms": self.max_atoms,
        }

    # ============================================================
    # 辅助方法（M0.2 新增）
    # ============================================================

    def set_tick(self, tick: int) -> None:
        """设置当前 tick（用于与 CogCoreState 同步）。"""
        self._tick = tick

    def clear(self) -> None:
        """清空状态池（测试用）。"""
        self._atoms.clear()
        self._attention_boosted.clear()
        self._inhibited.clear()
        self._delayed_tasks.clear()

    # ============================================================
    # 接地入口方法 (M0.7 新增 for E16)
    # ============================================================

    def apply_stimulus_packet(
        self,
        anchor_id: UUID,
        attributes: list[AttributeAtom],
        add_standalone: bool = True,
        modality: Modality = Modality.VISUAL,
        source: StimulusSource = StimulusSource.EXTERNAL,
    ) -> None:
        """从刺激包中应用属性刺激。
        
        对应 E16 实验：将静态属性绑定到目标锚点，并可选地作为独立刺激元注册到状态池。
        """
        host_atom = self._atoms.get(anchor_id)
        if host_atom is None:
            return

        for attr in attributes:
            # 确保 binding_score 为 0.0 (静态属性包注入)
            attr.binding_score = 0.0
            host_atom.attributes.append(attr)

            if add_standalone:
                standalone = StimulusAtom(
                    source=source,
                    modality=modality,
                    content={
                        "attribute_name": attr.attr_name,
                        "attribute_value": attr.attr_value,
                        "parent": anchor_id,
                    },
                    energy=AtomEnergy(
                        real=host_atom.energy.real,
                        virtual=host_atom.energy.virtual,
                    ),
                    trace={"origin": "sensor_grounding"},
                )
                self.add(standalone)

    def bind_attribute_node_to_object(
        self,
        anchor_id: UUID,
        attr_name: str,
        attr_value: Any,
        role: str,
        binding_score: float = 1.0,
        modality: Modality = Modality.TOOL_STATE,
        source: StimulusSource = StimulusSource.INTERNAL,
    ) -> bool:
        """在运行态动态绑定属性到目标对象。
        
        对应 E16 实验：如果 role 不为 "attribute" 则拒绝绑定，否则将动态属性附加到锚点，
        并作为独立刺激元加入状态池。
        """
        if role != "attribute":
            return False

        host_atom = self._atoms.get(anchor_id)
        if host_atom is None:
            return False

        attr = AttributeAtom(
            anchor_id=anchor_id,
            attr_name=attr_name,
            attr_value=attr_value,
            binding_score=binding_score,
        )
        host_atom.attributes.append(attr)

        standalone = StimulusAtom(
            source=source,
            modality=modality,
            content={
                "attribute_name": attr_name,
                "attribute_value": attr_value,
                "parent": anchor_id,
            },
            energy=AtomEnergy(
                real=host_atom.energy.real,
                virtual=host_atom.energy.virtual,
            ),
            trace={"origin": "runtime_binding"},
        )
        self.add(standalone)
        return True

    # ============================================================
    # 延迟任务管理 (M0.9 新增 for E06)
    # ============================================================

    def schedule_task(
        self,
        trigger_tick: int,
        task_type: str,
        target_id: UUID,
        content: Any,
        energy_real: float = 1.0,
        energy_virtual: float = 0.5,
    ) -> None:
        """注册一个定时/延迟任务。"""
        self._delayed_tasks.append({
            "trigger_tick": trigger_tick,
            "task_type": task_type,
            "target_id": target_id,
            "content": content,
            "energy_real": energy_real,
            "energy_virtual": energy_virtual
        })

    def process_delayed_tasks(self, current_tick: int) -> list[StimulusAtom]:
        """处理已到期的延迟任务，将它们作为刺激元回投进状态池。"""
        fired_atoms: list[StimulusAtom] = []
        remaining_tasks: list[dict] = []
        
        for task in self._delayed_tasks:
            if task["trigger_tick"] <= current_tick:
                atom = StimulusAtom(
                    source=StimulusSource.INTERNAL,
                    modality=Modality.TEXT,
                    content=task["content"],
                    energy=AtomEnergy(real=task["energy_real"], virtual=task["energy_virtual"]),
                    trace={"origin": "delayed_task", "attention_count": 0}
                )
                self.add(atom)
                fired_atoms.append(atom)
            else:
                remaining_tasks.append(task)
                
        self._delayed_tasks = remaining_tasks
        return fired_atoms
