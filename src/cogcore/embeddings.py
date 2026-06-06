"""M4.1 embedding providers.

No native/vector DB dependency. Providers return plain list[float].
"""
from __future__ import annotations

import hashlib
import math
from typing import Protocol


class EmbeddingProvider(Protocol):
    """Protocol for text embedding providers."""

    def embed(self, text: str) -> list[float]:
        ...


class MockEmbeddingProvider:
    """Deterministic hash-based provider for tests and offline evals."""

    def __init__(self, dim: int = 64) -> None:
        if dim < 1:
            raise ValueError("dim must be >= 1")
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        tokens = [t for t in text.lower().split() if t] or [text.lower()]
        vec = [0.0] * self.dim
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for i, byte in enumerate(digest):
                idx = i % self.dim
                vec[idx] += (byte / 255.0) - 0.5
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [round(v / norm, 8) for v in vec]


class OpenAIEmbeddingProvider:
    """OpenAI SDK embedding provider."""

    def __init__(
        self,
        *,
        client=None,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=base_url)
        self.client = client
        self.model = model

    def embed(self, text: str) -> list[float]:
        response = self.client.embeddings.create(model=self.model, input=text)
        return [float(x) for x in response.data[0].embedding]


class OllamaEmbeddingProvider(OpenAIEmbeddingProvider):
    """Ollama provider using its OpenAI-compatible /v1 embeddings endpoint."""

    def __init__(
        self,
        *,
        client=None,
        model: str = "qwen3-embedding:0.6b",
        base_url: str = "http://localhost:11434/v1",
    ) -> None:
        super().__init__(
            client=client,
            model=model,
            api_key="ollama",
            base_url=base_url,
        )
