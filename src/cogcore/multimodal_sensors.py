"""M5.4 E24 — 多模态感受器扩展。

ImageSensor / AudioSensor / ToolStateSensor 统一走 StimulusAtom 入池。
属性化入口：不验证实时机器人控制，只验证结构化入池。
"""
from __future__ import annotations

import base64
from typing import Any

from cogcore.types import AtomEnergy, Modality, StimulusAtom, StimulusSource


class ImageSensor:
    """图像感受器：接收 base64 图像 → 提取属性标签入池。

    当前为属性化入口：不跑真实 CV 模型，用启发式标签提取。
    生产环境可替换为 CLIP / 本地 Ollama vision 模型。
    """

    def __init__(self, base_energy: float = 1.0) -> None:
        self.base_energy = base_energy

    def parse(
        self, image_b64: str, metadata: dict, birth_tick: int = 0
    ) -> list[StimulusAtom]:
        """解析 base64 图像为属性标签 atoms。

        启发式策略（可审计）：
        - 从 metadata 读取已知标签（color, object, scene）
        - 无 metadata 时生成通用 "image_unknown"
        """
        atoms: list[StimulusAtom] = []
        tags: list[str] = []

        # 从 metadata 提取已知属性
        if metadata:
            color = metadata.get("color")
            obj = metadata.get("object")
            scene = metadata.get("scene")
            if color:
                tags.append(f"image_color_{color}")
            if obj:
                tags.append(f"image_object_{obj}")
            if scene:
                tags.append(f"image_scene_{scene}")

        if not tags:
            tags.append("image_unknown")

        for tag in tags:
            atoms.append(
                StimulusAtom(
                    content=tag,
                    source=StimulusSource.EXTERNAL,
                    modality=Modality.VISUAL,
                    energy=AtomEnergy(real=self.base_energy, virtual=0.0),
                    age_ticks=0,
                    birth_tick=birth_tick,
                    trace={
                        "origin": "image_sensor",
                        "input_size": len(image_b64),
                        "metadata": metadata,
                    },
                )
            )
        return atoms


class AudioSensor:
    """音频感受器：接收文本转录 → 情绪关键词入池。

    属性化入口：从转录文本提取情绪关键词。
    """

    EMOTION_KEYWORDS = {
        "happy", "sad", "angry", "excited", "calm", "anxious",
        "frustrated", "grateful", "confused", "confident",
    }

    def __init__(self, base_energy: float = 1.0) -> None:
        self.base_energy = base_energy

    def parse(
        self, transcript: str, metadata: dict, birth_tick: int = 0
    ) -> list[StimulusAtom]:
        """从转录文本提取情绪关键词 atoms。"""
        atoms: list[StimulusAtom] = []
        words = set(transcript.lower().split())
        emotions = words & self.EMOTION_KEYWORDS

        for emotion in emotions:
            atoms.append(
                StimulusAtom(
                    content=f"audio_emotion_{emotion}",
                    source=StimulusSource.EXTERNAL,
                    modality=Modality.AUDIO,
                    energy=AtomEnergy(real=self.base_energy, virtual=0.0),
                    age_ticks=0,
                    birth_tick=birth_tick,
                    trace={
                        "origin": "audio_sensor",
                        "transcript": transcript,
                    },
                )
            )

        if not atoms:
            # 无情绪词时入池一个中性标记
            atoms.append(
                StimulusAtom(
                    content="audio_neutral",
                    source=StimulusSource.EXTERNAL,
                    modality=Modality.AUDIO,
                    energy=AtomEnergy(real=self.base_energy * 0.5, virtual=0.0),
                    age_ticks=0,
                    birth_tick=birth_tick,
                    trace={"origin": "audio_sensor", "transcript": transcript},
                )
            )
        return atoms


class ToolStateSensor:
    """工具状态感受器：工具执行结果结构化入池。

    把工具输出转为可追踪的结构化 atom。
    """

    def __init__(self, base_energy: float = 1.0) -> None:
        self.base_energy = base_energy

    def parse(
        self, tool_result: dict[str, Any], metadata: dict, birth_tick: int = 0
    ) -> list[StimulusAtom]:
        """解析工具结果为结构化 atoms。"""
        atoms: list[StimulusAtom] = []
        tool_name = tool_result.get("tool", "unknown")
        status = tool_result.get("status", "unknown")
        output = tool_result.get("output", "")

        # 主 atom：工具执行状态
        atoms.append(
            StimulusAtom(
                content=f"tool_{tool_name}_{status}",
                source=StimulusSource.INTERNAL,
                modality=Modality.TOOL_STATE,
                energy=AtomEnergy(real=self.base_energy, virtual=0.0),
                age_ticks=0,
                birth_tick=birth_tick,
                trace={
                    "origin": "tool_state_sensor",
                    "tool": tool_name,
                    "status": status,
                    "output_preview": str(output)[:200],
                },
            )
        )

        # 如果输出含错误，额外入池错误标记
        if status == "error" or "error" in str(output).lower():
            atoms.append(
                StimulusAtom(
                    content=f"tool_{tool_name}_error_signal",
                    source=StimulusSource.INTERNAL,
                    modality=Modality.TOOL_STATE,
                    energy=AtomEnergy(real=self.base_energy * 1.5, virtual=0.0),
                    age_ticks=0,
                    birth_tick=birth_tick,
                    trace={
                        "origin": "tool_state_sensor",
                        "severity": "error",
                    },
                )
            )

        return atoms
