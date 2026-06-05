"""Multi-session persistence test: Alice should be remembered across restarts."""
from __future__ import annotations

import os
import sys
import time
import shutil

sys.stdout.reconfigure(encoding="utf-8")

os.environ["COGCORE_LLM_ENDPOINT"] = "https://api.deepseek.com/v1"
os.environ["COGCORE_LLM_API_KEY"] = "sk-30f3ba9b7c89444ab79145ce2700c34a"
os.environ["COGCORE_LLM_MODEL"] = "deepseek-chat"
os.environ["COGCORE_RUNTIME_MODE"] = "ap_agency"
os.environ["COGCORE_SERVICE_DATA_DIR"] = "cogcore_data_persist_test"

from cogcore.config import load_config
from cogcore.llm_bridge import LLMBridge
from cogcore.service import CogCoreService
from cogcore.tools import (
    LongTermExperienceTools,
    ToolRegistry,
    register_default_tools,
    register_long_term_tools,
)
from cogcore.agent import CogCoreAgent

DATA_DIR = "cogcore_data_persist_test"
DB_FILE = os.path.join(DATA_DIR, "state.db")

# Clean up any previous test data
if os.path.exists(DATA_DIR):
    shutil.rmtree(DATA_DIR)

print("=== Session 1: Tell Alice her name, write diary ===\n")

svc1 = CogCoreService()
svc1.config.service.tick_interval = 0
tr1 = ToolRegistry()
register_default_tools(tr1)
DIARY_DB = os.path.join(DATA_DIR, "diary.db")
lt1 = LongTermExperienceTools(svc1._hdb, svc1._pool, db_path=DIARY_DB)
register_long_term_tools(tr1, lt1)
agent1 = CogCoreAgent(service=svc1, bridge=LLMBridge(), registry=tr1)
agent1._service.config.service.tick_interval = 0

for msg in [
    "你好，记住我叫 Alice。",
    "把上面这些对话总结一下写进日记，标题是 'Alice 首次对话'。",
]:
    print(f"[Session 1] User: {msg}")
    t0 = time.time()
    r = agent1.process_message(msg)
    print(f"[Session 1] Agent ({time.time()-t0:.2f}s): {r.message[:200]}")
    print()

print(f"Diary entries before shutdown: {len(lt1._diary_store)}")
print(f"DB exists: {os.path.exists(DB_FILE)} (size: {os.path.getsize(DB_FILE) if os.path.exists(DB_FILE) else 0} bytes)\n")

# ============================
# Restart: New service, same data dir
# ============================
print("=== Restart: New service instance, same data dir ===\n")

svc2 = CogCoreService()
svc2.config.service.tick_interval = 0
tr2 = ToolRegistry()
register_default_tools(tr2)
lt2 = LongTermExperienceTools(svc2._hdb, svc2._pool, db_path=DIARY_DB)
register_long_term_tools(tr2, lt2)
agent2 = CogCoreAgent(service=svc2, bridge=LLMBridge(), registry=tr2)
agent2._service.config.service.tick_interval = 0

# Note: lt2 is a NEW instance — its in-memory diary store is empty.
# But the HDB and Pool were reloaded from SQLite.
# Let's see what the LLM can recover.

for msg in [
    "我叫什么名字？（查 read_diary 工具看看）",
    "日记里有什么？",
]:
    print(f"[Session 2] User: {msg}")
    t0 = time.time()
    r = agent2.process_message(msg)
    print(f"[Session 2] Agent ({time.time()-t0:.2f}s): {r.message[:300]}")
    print()

# Cleanup
del agent1, agent2, svc1, svc2, lt1, lt2, tr1, tr2
import gc
gc.collect()
time.sleep(0.5)
if os.path.exists(DATA_DIR):
    shutil.rmtree(DATA_DIR, ignore_errors=True)

print("=== Done ===")
