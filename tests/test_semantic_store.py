"""M4.1 semantic store tests."""
from __future__ import annotations

import os

from cogcore.embeddings import MockEmbeddingProvider
from cogcore.hdb import HDB
from cogcore.semantic_store import DualStore, SemanticStore, cosine_similarity
from cogcore.types import AtomEnergy, Modality, StimulusAtom, StimulusSource


def test_cosine_similarity():
    assert cosine_similarity([1, 0], [1, 0]) == 1.0
    assert cosine_similarity([1, 0], [0, 1]) == 0.0


def test_semantic_store_add_creates_db(tmp_path):
    db_path = str(tmp_path / "semantic.db")
    store = SemanticStore(db_path, provider=MockEmbeddingProvider(dim=8))
    row_id = store.add("hello world", {"kind": "greeting"})
    store.close()

    assert row_id > 0
    assert os.path.exists(db_path)


def test_semantic_store_search_orders_by_similarity(tmp_path):
    store = SemanticStore(str(tmp_path / "semantic.db"), provider=MockEmbeddingProvider(dim=16))
    store.add("alpha beta", {"id": "a"})
    store.add("weather rain umbrella", {"id": "weather"})
    store.add("coffee beans", {"id": "coffee"})

    results = store.search("weather rain", top_k=2, threshold=-1.0)
    store.close()

    assert len(results) == 2
    assert results[0].score >= results[1].score
    assert any(r.metadata["id"] == "weather" for r in results)


def test_semantic_store_threshold_filters(tmp_path):
    store = SemanticStore(str(tmp_path / "semantic.db"), provider=MockEmbeddingProvider(dim=16))
    store.add("exact phrase", {"id": "exact"})
    assert store.search("exact phrase", threshold=0.99)
    assert store.search("completely different", threshold=1.1) == []
    store.close()


def test_semantic_store_top_k_boundary(tmp_path):
    store = SemanticStore(str(tmp_path / "semantic.db"), provider=MockEmbeddingProvider(dim=8))
    for i in range(5):
        store.add(f"item {i}", {"i": i})
    assert len(store.search("item", top_k=3, threshold=-1.0)) == 3
    assert store.search("item", top_k=0) == []
    store.close()


def test_dual_store_hdb_miss_falls_back_to_semantic(tmp_path):
    hdb = HDB()
    semantic = SemanticStore(str(tmp_path / "semantic.db"), provider=MockEmbeddingProvider(dim=16))
    semantic.add("weather rain umbrella", {"kind": "memory"})
    dual = DualStore(hdb, semantic)

    atom = StimulusAtom(
        content="weather rain",
        source=StimulusSource.EXTERNAL,
        modality=Modality.TEXT,
        energy=AtomEnergy(real=1.0),
        trace={"origin": "test"},
    )
    result = dual.lookup_or_search([atom], top_k=1)
    semantic.close()

    assert result["semantic_results"]
    assert result["semantic_results"][0].metadata["kind"] == "memory"
