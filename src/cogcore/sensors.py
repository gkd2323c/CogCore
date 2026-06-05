"""感受器层（Sensor Layer）+ 字符级文本感受器。

接口与 docs/CogCore-通用认知内核架构设计.md §4.1 完全对齐。
论文 4.3 节：当前原型采用字符/字符串作为主要起点（可审计、可复现、适合机制验证）。

M0.2 实现：TextSensor 极简可用版（按空格分词）。
"""

from __future__ import annotations

from typing import Any, Callable

from cogcore.types import AtomEnergy, Modality, StimulusAtom, StimulusSource


class SensorLayer:
    """感受器层：每种模态注册一个 parser。

    parser 职责：将原始输入拆分为刺激元并赋予初始实能量。
    """

    def __init__(self) -> None:
        self._parsers: dict[Modality, Callable] = {}
        # 默认注册字符级文本感受器
        self._parsers[Modality.TEXT] = TextSensor().parse

    def register_sensor(self, modality: Modality, parser: Callable) -> None:
        self._parsers[modality] = parser

    def ingest(
        self,
        raw_input: Any,
        modality: str,
        metadata: dict,
        birth_tick: int = 0,
    ) -> list[StimulusAtom]:
        """解析原始输入为刺激元列表。"""
        mod = Modality(modality)
        parser = self._parsers.get(mod)
        if parser is None:
            return []
        return list(parser(raw_input, metadata, birth_tick))

    def get_supported_modalities(self) -> list[str]:
        return [m.value for m in self._parsers]


class TextSensor:
    """字符级文本感受器（论文 4.3 默认实现，极简版）。

    M0.2 极简策略：把文本按空格分词，每个词作为一个 StimulusAtom。
    - 优点：简单、可审计、HDB 查存能匹配
    - 缺点：语义粒度粗（不做分词、不做词性标注）
    """

    DEFAULT_BASE_ENERGY = 1.0

    def __init__(self, base_energy: float = DEFAULT_BASE_ENERGY) -> None:
        self.base_energy = base_energy

    def parse(
        self, text: str, metadata: dict, birth_tick: int = 0
    ) -> list[StimulusAtom]:
        """把文本按空格分词，每个词为一个 StimulusAtom。

        Args:
            text: 原始文本
            metadata: 元数据（可选，含 salience_factor 等）
            birth_tick: 创建时的 tick

        Returns:
            list[StimulusAtom]
        """
        if not text or not text.strip():
            return []

        salience = metadata.get("salience_factor", 1.0) if metadata else 1.0
        initial_real = self.base_energy * salience

        # 按空白分词（保留非空）
        words = [w for w in text.split() if w]
        atoms = []
        for word in words:
            atom = StimulusAtom(
                content=word,
                source=StimulusSource.EXTERNAL,
                modality=Modality.TEXT,
                energy=AtomEnergy(real=initial_real, virtual=0.0),
                age_ticks=0,
                birth_tick=birth_tick,
                trace={"origin": "text_sensor"},
            )
            atoms.append(atom)

        return atoms

