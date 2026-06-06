"""M4.1 embedding provider tests."""
from __future__ import annotations

from unittest.mock import MagicMock

from cogcore.embeddings import (
    EmbeddingProvider,
    MockEmbeddingProvider,
    OllamaEmbeddingProvider,
    OpenAIEmbeddingProvider,
)


def test_mock_embedding_provider_is_deterministic():
    provider = MockEmbeddingProvider(dim=8)
    assert provider.embed("hello") == provider.embed("hello")
    assert len(provider.embed("hello")) == 8


def test_mock_embedding_provider_distinguishes_text():
    provider = MockEmbeddingProvider(dim=8)
    assert provider.embed("hello") != provider.embed("world")


def test_openai_embedding_provider_uses_client():
    client = MagicMock()
    item = MagicMock()
    item.embedding = [0.1, 0.2, 0.3]
    response = MagicMock()
    response.data = [item]
    client.embeddings.create.return_value = response

    provider = OpenAIEmbeddingProvider(client=client, model="text-embedding-3-small")
    assert provider.embed("hello") == [0.1, 0.2, 0.3]
    client.embeddings.create.assert_called_once()


def test_ollama_embedding_provider_uses_client():
    client = MagicMock()
    item = MagicMock()
    item.embedding = [0.3, 0.2, 0.1]
    response = MagicMock()
    response.data = [item]
    client.embeddings.create.return_value = response

    provider = OllamaEmbeddingProvider(client=client, model="qwen3-embedding:0.6b")
    assert provider.embed("hello") == [0.3, 0.2, 0.1]


def test_embedding_provider_protocol():
    provider: EmbeddingProvider = MockEmbeddingProvider(dim=4)
    assert len(provider.embed("x")) == 4
