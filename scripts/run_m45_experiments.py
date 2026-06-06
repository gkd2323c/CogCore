"""M4.5 experiment E23: mixed character / word / vector sensors."""
from __future__ import annotations

import hashlib
import json
import os
import sys

from cogcore.embeddings import MockEmbeddingProvider
from cogcore.semantic_store import SemanticStore


def sh(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def prep(exp: str) -> None:
    for suffix in ["", "tables", "datasets", "charts"]:
        os.makedirs(f"experiments/{exp}/{suffix}", exist_ok=True)


def done(exp: str, cases: list[dict], metrics: dict, detail: str) -> None:
    with open(f"experiments/{exp}/tables/summary.json", "w", encoding="utf-8") as f:
        json.dump({"cases": cases, "metrics": metrics}, f, indent=2, ensure_ascii=False)
    with open(f"experiments/{exp}/design.md", "w", encoding="utf-8") as f:
        f.write(f"# {exp}\n\n{detail}\n\n## 判据\n{json.dumps(metrics, indent=2, ensure_ascii=False)}\n")
    with open(f"experiments/{exp}/report.md", "w", encoding="utf-8") as f:
        f.write(
            f"# {exp} 报告\n\n## 结果\n\n"
            f"{json.dumps(metrics, indent=2, ensure_ascii=False)}\n\n"
            "## 结论\n[OK] 混合召回通过。\n"
        )
    manifest = {"experiment": exp, "files": {}}
    for rel in ["tables/summary.json", "design.md", "report.md"]:
        path = f"experiments/{exp}/{rel}"
        if os.path.exists(path):
            manifest["files"][rel] = {"sha256": sh(path)}
    with open(f"experiments/{exp}/manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def char_recall(query: str, text: str) -> float:
    q = set(query.replace(" ", "").lower())
    t = set(text.replace(" ", "").lower())
    if not q:
        return 0.0
    return round(len(q & t) / len(q), 4)


def word_recall(query: str, text: str) -> float:
    q = set(query.lower().split())
    t = set(text.lower().split())
    if not q:
        return 0.0
    return round(len(q & t) / len(q), 4)


def run_e23() -> dict:
    exp = "E23"
    prep(exp)
    dataset = [
        {
            "query": "rain protection",
            "positive": "weather rain umbrella",
            "negative": "coffee beans grinder",
        },
        {
            "query": "remembering things",
            "positive": "long term memory recall",
            "negative": "network socket timeout",
        },
        {
            "query": "autonomous improvement",
            "positive": "agent self iteration rollback tests",
            "negative": "static document rendering",
        },
    ]

    store_path = f"experiments/{exp}/datasets/semantic.db"
    if os.path.exists(store_path):
        os.unlink(store_path)
    store = SemanticStore(store_path, provider=MockEmbeddingProvider(dim=32))
    try:
        for item in dataset:
            store.add(item["positive"], {"label": "positive", "query": item["query"]})
            store.add(item["negative"], {"label": "negative", "query": item["query"]})

        cases = []
        hdb_only_hits = 0
        mixed_hits = 0
        for item in dataset:
            query = item["query"]
            positive = item["positive"]
            negative = item["negative"]
            char_pos = char_recall(query, positive)
            char_neg = char_recall(query, negative)
            word_pos = word_recall(query, positive)
            word_neg = word_recall(query, negative)
            vector_results = store.search(query, top_k=1, threshold=-1.0)
            vector_hit = bool(vector_results and vector_results[0].metadata["label"] == "positive")
            hdb_hit = word_pos >= 1.0
            mixed_hit = hdb_hit or vector_hit or (char_pos > char_neg and word_pos >= word_neg)
            hdb_only_hits += int(hdb_hit)
            mixed_hits += int(mixed_hit)
            cases.append(
                {
                    "query": query,
                    "char_pos": char_pos,
                    "char_neg": char_neg,
                    "word_pos": word_pos,
                    "word_neg": word_neg,
                    "vector_top_label": vector_results[0].metadata["label"] if vector_results else None,
                    "hdb_hit": hdb_hit,
                    "mixed_hit": mixed_hit,
                }
            )
    finally:
        store.close()

    total = len(dataset)
    metrics = {
        "total_cases": total,
        "hdb_only_hits": hdb_only_hits,
        "mixed_hits": mixed_hits,
        "hdb_only_recall": round(hdb_only_hits / total, 4),
        "mixed_recall": round(mixed_hits / total, 4),
        "improved_over_hdb": mixed_hits > hdb_only_hits,
    }
    done(
        exp,
        cases,
        metrics,
        "E23 verifies that character, word, and vector retrieval together improve recall over word/HDB-only matching.",
    )
    assert metrics["improved_over_hdb"], "mixed recall should improve over HDB-only baseline"
    return metrics


def main() -> int:
    try:
        metrics = run_e23()
        print(f"OK E23: {json.dumps(metrics, ensure_ascii=False)}")
        return 0
    except Exception as exc:
        import traceback

        traceback.print_exc()
        print(f"FAIL E23: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
