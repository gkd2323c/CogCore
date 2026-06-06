# CogCore — AGENTS.md

Cognitive kernel ("long-term cognitive runtime") for LLM agents. Engineering rewrite of the AP paper (2026). **M5 complete** — 40 modules, 40 test files, 533 tests (528 passed / 5 skipped in current env).

## Quick start

```bash
cp config.toml.example config.toml   # then edit (gitignored, holds api keys)
pip install -e ".[dev]"              # install package + dev deps
pytest                               # 533 tests (528 passed / 5 skipped in current env)
python scripts/verify_all.py         # full-chain smoke test
```

## Commands

| What | How |
|---|---|
| All tests | `pytest` |
| Stop at first failure | `pytest -x` |
| Single file | `pytest tests/test_pipeline.py` |
| Single test | `pytest tests/test_pipeline.py::test_imports` (no async, no markers) |
| CLI (LangGraph) | `python -m cogcore.run "你的输入"` |
| CLI (skeleton) | `python -m cogcore.main "你的输入"` |
| FastAPI server | `uvicorn app.main:app` or `python -m app.main` |
| Full verification | `python scripts/verify_all.py` |
| Run all experiments | `python scripts/run_all_experiments.py` |
| Run M3.7 (E21/E22) | `python scripts/run_m37_experiments.py` |
| Run M4.2 db_health | `python scripts/db_health.py` (默认 20MB state.db 健康报告) |
| Run M4.3b stats | `python -m cogcore.stats` |
| Run M4.5 (E23) | `python scripts/run_m45_experiments.py` |
| Run self-iteration (with evals) | `python scripts/run_self_iteration.py --with-evals` |
| Run evals suite | `pytest --evals` |

No linter, formatter, typechecker, or CI configured. All tests are sync (no `pytest.mark.asyncio` despite having the dep).

## Package layout

- **`src/cogcore/`** — 40 Python modules (`types.py`, `pipeline.py`, `hdb.py`, `graph.py`, `llm_bridge.py`, `service.py`, `agent.py`, `tools*.py`, `self_iteration.py`, `db_maintenance.py`, `json_tracer.py`, `sqlite_stats.py`, `main.py`, `run.py`, …)
- **`app/`** — FastAPI app (endpoints: chat, diary, status, ws). Depends on `src/cogcore/`.
- **`tests/`** — 40 test files. `test_api.py` uses `cogcore_data_api_test/` as temp data dir (auto cleaned).
- **`scripts/`** — 15+ demo/verification scripts. `verify_all.py` is the main one.
- **`experiments/E01/`…`E22/`** — one dir per experiment. See `docs/CogCore-验证矩阵.md`.
- **`config.toml`** — local config (gitignored). Template: `config.toml.example`.
- **`cogcore_data/`** — runtime data: SQLite state db + diary (gitignored).

## Key docs

| Ask | Read |
|---|---|
| "What/why CogCore?" | `PURPOSE.MD` |
| "Architecture?" | `docs/CogCore-通用认知内核架构设计.md` |
| "Experiments E01-E17?" | `docs/CogCore-验证矩阵.md` §1 |
| "E0X → module mapping?" | `docs/CogCore-验证矩阵.md` §3 |
| "Build a full agent?" | `AGENT_BUILD.MD` |
| "Overall plan (M3-M5)?" | `docs/CogCore-总体计划.md` |
| "M3 sub-stages (FastAPI/LLM/MCP/...)?" | `docs/CogCore-M3-规划.md` |
| "M4 sub-stages (SQLite/trace/evals/...)?" | `docs/CogCore-M4-规划.md` |

## Hard constraints

- **Never modify** `paper/` (original text, 100% read-only).
- **Never skip** E01-E17 for E18+ — all preconditions must clear first.
- **Never** mark status "verified" without running the actual experiment under §0.2 4-condition gate.
- **Never** claim implementation without code + test evidence.
- **Never** remove or restructure `docs/` §10 roadmap or appendix A.
- Experiment data: `experiments/E0X/` with standard subdirs (`design.md`, `report.md`, `tables/`, `charts/`, `datasets/`, `manifest.json`). Sub-threshold data goes in `_archive/`.

## Commit conventions

- One logical unit per commit.
- Message body references M0.x milestone and E0X experiment IDs.
- No commits without `git status` + `git diff` check first.
