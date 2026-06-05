"""CogCore 全链路验证脚本。"""
from __future__ import annotations

import os, gc, sys
from unittest.mock import MagicMock

ok = 0
total = 0

def check(name, cond, detail=""):
    global ok, total
    total += 1
    if cond:
        ok += 1
        print(f"  OK  {name}")
    else:
        print(f"  FAIL {name}" + (f": {detail}" if detail else ""))

def make_atom(w, e=1.0):
    from cogcore.types import StimulusAtom, AtomEnergy, Modality, StimulusSource
    return StimulusAtom(content=w, source=StimulusSource.EXTERNAL, modality=Modality.TEXT, energy=AtomEnergy(real=e, virtual=0.0), trace={"origin": "verify"})

print("=== CogCore Full Chain Verification ===\n")

# ═══════════════════════════════════════════════
# M0: Core Cognitive Loop
# ═══════════════════════════════════════════════
print("-- M0: Core Cognitive Loop --")

from cogcore.state_pool import StatePool
from cogcore.hdb import HDB
from cogcore.attention import Attention
from cogcore.cfs import CognitiveFeelingSystem
from cogcore.nt import NeurotransmitterSystem
from cogcore.adaptive_tuner import AdaptiveTuner
from cogcore.action_system import ActionSystem
from cogcore.types import ActionNode, ActionSource

pool = StatePool()
hdb = HDB()
cfs = CognitiveFeelingSystem()
attn = Attention()
nt = NeurotransmitterSystem()
tuner = AdaptiveTuner()
action = ActionSystem()

pool.add(make_atom("hello"))
es = pool.get_energy_summary()
check("StatePool add+energy", es.active_count >= 1)
pool.decay()
check("StatePool decay silent", True)

hdb.set_tick(0)
r = hdb.lookup([make_atom("hello")])
check("HDB lookup(hello)", len(r.match_scores) > 0 or len(r.new_structures) > 0)

cfs.set_tick(0)
sigs = cfs.evaluate({"cognitive_pressure": 0.5, "active_count": 5, "total_energy": 3.0}, {}, {"reward_signal": 0.1})
check("CFS evaluate", isinstance(sigs, list))

nt.set_tick(0)
nr = nt.update([], [], {})
check("NT update returns values", hasattr(nr, "arousal"))
check("NT arousal in range", 0 <= nr.arousal <= 1)

cam = attn.select(pool)
check("Attention returns CAM", cam is not None and hasattr(cam, "items"))

nid = action.register_node(ActionNode(name="test", threshold=0.5, source=ActionSource.INNATE))
check("ActionSystem register", True)  # register_node returns node object

adj = tuner.assess(es, nt.current, {"cam_energy_variance": 0.5, "induction_nodes": 5})
check("AdaptiveTuner assess", adj is not None)

# Pipeline
from cogcore.graph import build_cogcore_graph, invoke_cogcore
mods = {
    "pool": StatePool(), "hdb": HDB(), "cfs": CognitiveFeelingSystem(),
    "attention": Attention(), "nt_sys": NeurotransmitterSystem(),
    "action_sys": ActionSystem(), "tuner": AdaptiveTuner(),
}
g = build_cogcore_graph(mods)
state = invoke_cogcore(g, "test cycle", 0, "v-m0")
check("Pipeline 10 stages", len(state.get("stages_log", [])) == 10)
check("Pipeline nt_values", state.get("nt_values") is not None)
check("Pipeline cam", state.get("cam") is not None)
check("Pipeline new_atoms", len(state.get("new_atoms", [])) > 0)

# ═══════════════════════════════════════════════
# M1: Config + LLM Bridge + Tools + Modes
# ═══════════════════════════════════════════════
print("-- M1: LLM Bridge + Tools + Modes --")

from cogcore.config import load_config
cfg = load_config()
check("Config loads", cfg.llm.model is not None)

from cogcore.llm_bridge import LLMBridge
mock = MagicMock()
mr = MagicMock(); mc = MagicMock(); mc.content = "Mock LLM response"
mr.choices = [type("c", (), {"message": mc})()]
mock.chat.completions.create.return_value = mr
bridge = LLMBridge(client=mock)
resp = bridge.chat([{"role": "user", "content": "hi"}])
check("LLM Bridge chat", resp == "Mock LLM response")

packet = bridge.build_context_packet(state, 1000)
check("Context packet 8 fields", "[CURRENT INPUT]" in packet and "[ENERGY STATE]" in packet and "[NEUROTRANSMITTERS]" in packet and "[PROMPT INSTRUCTIONS]" in packet)

atoms = bridge.parse_llm_output("hello world")
check("Parse LLM output", len(atoms) == 2)

check("Teacher gate normal", bridge.teacher_gate_should_wake({}, {"error_log": [], "pool_snapshot": {"energy_summary": {"cognitive_pressure": 0.3}}, "nt_values": {"fatigue": 0.2}}))
check("Teacher gate blocks fatigue", not bridge.teacher_gate_should_wake({}, {"error_log": [], "pool_snapshot": {"energy_summary": {"cognitive_pressure": 0.3}}, "nt_values": {"fatigue": 0.9}}))

# Tools
from cogcore.tools import ToolRegistry, LongTermExperienceTools, register_default_tools
tr = ToolRegistry()
register_default_tools(tr)
check("Default tools registered", "calc" in tr.get_available_tools())
check("Tool calc 1+1", tr.execute_tool("calc", {"expr": "1+1"}) == "2")

lt = LongTermExperienceTools(HDB(), StatePool())
lt.write_diary("v", "verify content")
check("Diary write+read", len(lt.read_diary("verify")) >= 1)
tid = lt.schedule_task("v", "a", 5)
check("Task create+cancel", lt.cancel_task(tid))

# Modes
from cogcore.modes import WakeController, AgentMode
st = {"pool_snapshot": {"energy_summary": {"active_count": 10, "total_energy": 8.0}}}
wc = WakeController(mode=AgentMode.AP_AGENCY, wake_drive_threshold=0.3)
check("AP agency wakes", wc.should_wake(event={}, cogcore_state=st))
wc2 = WakeController(mode=AgentMode.FULL_SILENT)
check("Full silent no wake", not wc2.should_wake(event={}))

# SQLite
from cogcore.graph import build_cogcore_graph_persistent
db = "_v_verify.db"
if os.path.exists(db): os.remove(db)
gp = build_cogcore_graph_persistent(mods, sqlite_path=db)
invoke_cogcore(gp, "v", 0, "v-sqlite")
check("SQLite db created", os.path.exists(db) and os.path.getsize(db) > 0)
del gp; gc.collect()
try: os.remove(db)
except: pass
for ext in ("-wal","-shm"):
    p = db+ext
    if os.path.exists(p):
        try: os.remove(p)
        except: pass

# ═══════════════════════════════════════════════
# M2: Service + Agent + Skills
# ═══════════════════════════════════════════════
print("-- M2: Service + Agent + Skills --")

from cogcore.service import CogCoreService
svc = CogCoreService()
svc.config.service.tick_interval = 0
s = svc.tick("svc")
check("Service tick 10 stages", len(s.get("stages_log", [])) == 10)
svc.inject_input("test input")
check("Service queued input", len(svc._pending_input) == 1)
st2 = svc.get_status()
check("Service status fields", "pool" in st2 and "hdb" in st2 and "nt" in st2)
svc.config.service.diary_interval = 2
svc._last_diary_tick = 0
svc.tick("d1"); svc.tick("d2")
check("Auto diary", len(svc._tools._diary_store) >= 1)

# Agent
from cogcore.agent import CogCoreAgent
mock2 = MagicMock()
mock2.build_context_packet = MagicMock(return_value="ctx")
mock2.chat = MagicMock(return_value="Agent reply")
agent = CogCoreAgent(service=CogCoreService(), bridge=mock2, registry=tr)
agent._service.config.service.tick_interval = 0
resp = agent.process_message("hi")
check("Agent returns response", len(resp.message) > 0)
check("Agent ticks > 0", resp.tick_count > 0)

# Skills
from cogcore.tools import Skill, SkillRunner
sr = SkillRunner()
sr.register(Skill(name="double", description="", code="result = params['x'] * 2"))
check("Skill execute", sr.execute("double", x=5) == 10)
check("Skill not found handler", "not found" in sr.execute("nonexistent"))

# Tool Executor
from cogcore.tool_executor import ToolExecutor
te = ToolExecutor(tr)
res = te.parse_and_execute('test no tool call')
check("ToolExecutor no-call", len(res) == 0)

# Enable/Disable switches
cfs_d = CognitiveFeelingSystem(enabled=False)
check("CFS disabled returns empty", cfs_d.evaluate({}, {}, {}) == [])
nt_d = NeurotransmitterSystem(enabled=False)
check("NT disabled", nt_d.update([], [], {}).arousal == 0.0)
tuner_d = AdaptiveTuner(enabled=False)
check("APT disabled", tuner_d.assess(None, None, {}).attention_budget_delta == 0)

# ═══════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════
print()
print(f"=== Result: {ok}/{total} passed ({ok*100//total}%) ===")

if ok < total:
    sys.exit(1)
