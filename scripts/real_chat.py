"""Real DeepSeek dialogue test."""
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

os.environ["COGCORE_LLM_ENDPOINT"] = "https://api.deepseek.com/v1"
os.environ["COGCORE_LLM_API_KEY"] = "sk-30f3ba9b7c89444ab79145ce2700c34a"
os.environ["COGCORE_LLM_MODEL"] = "deepseek-chat"
os.environ["COGCORE_RUNTIME_MODE"] = "ap_agency"

from cogcore.agent import CogCoreAgent
from cogcore.config import load_config
from cogcore.llm_bridge import LLMBridge
from cogcore.service import CogCoreService
from cogcore.tools import (
    LongTermExperienceTools,
    ToolRegistry,
    register_default_tools,
    register_long_term_tools,
)

cfg = load_config()
print(f"endpoint: {cfg.llm.endpoint}")
print(f"model:    {cfg.llm.model}")
print(f"mode:     {cfg.runtime.mode}")
print()

svc = CogCoreService()
svc.config.service.tick_interval = 0
svc.config.persistence.backend = "memory"

tr = ToolRegistry()
register_default_tools(tr)
lt_tools = LongTermExperienceTools(svc._hdb, svc._pool)
register_long_term_tools(tr, lt_tools)
print(f"Available tools: {tr.get_available_tools()}")

bridge = LLMBridge()
agent = CogCoreAgent(service=svc, bridge=bridge, registry=tr)
agent._service.config.service.tick_interval = 0
print("Agent ready.\n")

messages = [
    "你好，记住我叫 Alice。",
    "帮我算一下 23 * 47 等于多少？（用 calc 工具）",
    "我叫什么名字？",
    "把上面这些对话总结一下写进日记，标题是 'Alice 首次对话'。",
]

for i, msg in enumerate(messages, 1):
    print(f"[{i}] [User] {msg}")
    sys.stdout.flush()
    t0 = time.time()
    try:
        resp = agent.process_message(msg)
        dt = time.time() - t0
        msg_text = resp.message[:300] if resp.message else "(empty)"
        print(f"[{i}] [Agent] ({dt:.2f}s) {msg_text}")
        if resp.tool_calls > 0:
            print(f"     tool_calls: {resp.tool_calls}")
        print()
    except Exception as e:
        print(f"[{i}] FAIL: {e}")
        import traceback
        traceback.print_exc()
    print()
    sys.stdout.flush()

print("--- Status ---")
status = agent._service.get_status()
print(f"  ticks:    {status['tick_count']}")
print(f"  active:   {status['pool']['active']}")
print(f"  energy:   {status['pool']['total_energy']:.3f}")
print(f"  diary:    {len(status.get('diary', []))}")
print(f"  tasks:    {len(status.get('tasks', []))}")
if 'nt' in status:
    print(f"  NT:       arousal={status['nt']['arousal']:.3f} fatigue={status['nt']['fatigue']:.3f}")

diaries = lt_tools._diary_store
print()
print(f"--- {len(diaries)} Diary entries ---")
for d in diaries:
    print(f"  - {d['title']}: {d['content'][:80]}")
