# CogCore — 通用认知内核

LLM-agent 持续认知层. AP 论文工程复现. Python 3.10+ / LangGraph / SQLite / Pydantic.

## §G — 全局

**G1**: CogCore = 认知内核, not 应用. 承担 4 事: 长期状态, 记忆, 感受调制, 行动反馈学习.
上层 (LLM, 工具链, 对话) 负责语义解释 & 语言表达.

**G2**: 设计原则
- 白箱优先: ∀ 认知对象记录来源/能量/匹配路径/处置事件 → 可追溯
- 闭环: 行动后果, 残差, 感应目标回写状态池
- 能量货币: 实能量=现实证据, 虚能量=内源预测, 认知压=|实-虚|
- 可衰减/可竞争/可召回: 状态池=动态场

**G3**: 零 Docker / 零外部服务.
`pip install cogcore` → `python -m cogcore serve` → 完事.
依赖: LangGraph + openai + SQLite + Pydantic.

**G4**: 实验准入 4 条件 (§0.2)
1. 受控设计清晰: 输入/起点/参数/对照变量声明
2. 基线可比: 共享冷启动输入 + 相同主线口径
3. 方向一致: 结果沿机制预测方向稳定 (sign test)
4. 结论可独立复查: 文件链 + SHA-256 + 复现脚本

**G5**: Nord star = 自迭代 (L12).
4 层: 自检 → 自改 → 自部署 → 自学. 安全约束:
  1. 测试闸门: 自改前必过 pytest
  2. 版本回滚: 改前 git commit, 失败 revert
  3. 沙箱: 只改 `src/cogcore/` + `tests/`
  4. commit message 必含 `[auto-iterate]`

**G6**: 不引入 Docker / Postgres / Prom / Grafana / Langfuse.

## §C — 架构

```
上层 Agent (LLM / 工具链 / 对话)
    ↓ 外源刺激          ↑ 行动结果/教师反馈
┌─────────────────────────────────────────────┐
│ CogCore                                    │
│ Sensors → StatePool → Attention(↓CAM)      │
│            ↕              ↕                 │
│    HDB ← InductionGrowth  CFS              │
│            ↕              ↕                 │
│    EpisodicMemory ← ActionSystem → NT      │
│            AdaptiveTuner (横切)             │
└─────────────────────────────────────────────┘
```

## §I — 接口

### 数据类型
```
types: StimulusAtom { id, source, content, modality, energy:{real,virtual}, age_ticks, birth_tick, trace:{origin,matched_structures,attention_count,action_events}, attributes }
  AttributeAtom { anchor_id, attr_name, attr_value, binding_score }
  Structure { id, index_key, residuals, local_db, energy_stats:{hit_count,last_hit_tick,avg_activation}, episodic_anchors, created_tick, depth }
  EpisodicMemory { id, tick_range, stimuli_snapshot, action_taken, outcome, feeling_snapshot, structure_refs }
  ActionNode { id, name, drive, threshold, source, last_executed_tick, execution_count, reward_history, punishment_history, tool_mapping, in_pool }
  NTModulations { focus[-1,1], arousal[-1,1], caution[0,1], exploration[0,1], fatigue[0,1], stability[0,1] }
  CurrentAttentionMemory { selected_ids, scores, config_used }
  TickReportDC { tick, timestamp, stages_completed, error_log }
```

### 模块接口
```
SensorLayer:
  ingest(raw, modality, metadata) → list[StimulusAtom]
  register_sensor(modality, parser)
  get_supported_modalities() → list[str]

StatePool:
  add(atom)
  get_all() → list[StimulusAtom]
  get_by_energy(min_energy) → list[StimulusAtom]
  decay()
  cleanup(min_energy, max_age) → list[StimulusAtom]
  get_energy_summary() → EnergySummary
  apply_attention_boost(atom_ids, factor)
  apply_inhibition(atom_ids, factor)
  get_state_report() → dict

HDB:
  lookup(stimuli) → LookupResult
  store(stimuli, residual) → Structure
  get_structure(id) → Structure
  get_local_db(id) → dict
  get_episodic(anchor_id) → EpisodicMemory
  write_episodic(memory)
  decay_unused(max_age_ticks, min_hit_count) → int
  get_hdb_report() → dict

InductionGrowth:
  expand(source_atoms, hdb) → list[StimulusAtom]
  get_expansion_report() → dict

Attention:
  select(pool, config) → CurrentAttentionMemory
  get_selection_report() → dict

CognitiveFeelingSystem:
  evaluate(pool_state, hdb_result, action_result) → list[StimulusAtom]
  get_feeling_report() → dict

NeurotransmitterSystem:
  update(feelings, action_feedback)
  get_modulations() → NTModulations
  get_baseline() → dict
  reset_to_baseline()

ActionSystem:
  register_node(node)
  evaluate_drives(pool, nt) → list[ActionCandidate]
  execute(candidate, executor) → ActionResult
  process_feedback(result)
  get_action_report() → dict

AdaptiveTuner:
  assess(pool_stats, nt, cfs) → TunerAction
  apply(action) → dict
  get_tuner_report() → dict
```

### 应用层接口
```
cmd: python -m cogcore.main "<text>" → stdout tick report
cmd: python -m cogcore.run "<text>" → LangGraph pipeline
api: POST /v1/chat → {response, thread_id}
api: WS /v1/ws/{thread_id} → stream
api: GET /v1/status → {tick, modules, uptime}
api: GET/POST /v1/diary → diary entries
```

### 自迭代接口
```
cmd: python -m cogcore.self_modify_safety --check <path> → {allowed, reason}
SelfIterateLoop:
  observe() → {tick, test_results, git_status}
  detect_gap() → list[Gap]
  plan_fix(gap) → Plan
  read_source(paths) → str
  propose_change(plan) → Proposal
  test(proposal) → {passed, report}
  commit(proposal) → {sha, message}
  reload(module_names) → {success, errors}
  log(gap, proposal) → None
```

### 配置
```
env: OPENAI_API_KEY ! set
env: DEEPSEEK_API_KEY ? set
config.toml:
  [llm]
  providers = [{name, endpoint, model, priority}]  # circular fallback
  [mcp]
  servers = ["brave", "firecrawl", ...]
  [persistence]
  max_checkpoints=100, auto_vacuum_interval=1000
```

## §V — 不变量

**V1**: ∀ stimulusAtom → id != null & source ∈ enum & birth_tick ≥ 0
**V2**: E_total = E_real + E_virtual, E_real ≥ 0, E_virtual ≥ 0
**V3**: state_pool size ≤ max_atoms (default 200). evicted atoms = lowest energy, episodic-anchored exempt.
**V4**: energy decay: E_real(t+1) = λ_real × E_real(t) + I_external; λ_real=0.85, λ_virtual=0.75
**V5**: cognitive_pressure = Σ|E_real - E_virtual| / N_active. ∈ [0, 1]
**V6**: HDB.lookup → match_score = |key∩S| / |key∪S|. growth_threshold=0.3
**V7**: induction: max_depth ≤ 3, min_energy ≥ 0.05, budget ≤ 50, spread_factor=0.8
**V8**: attention: budget ≤ 10. repeat_penalty=0.5, fatigue_penalty=0.2 after 3 consecutive.
**V9**: NT(t+1) = baseline + inertia×(NT(t)-baseline) + impulse(t). inertia=0.85. magnitudes clamped ∈ [−1,1] or [0,1] per channel.
**V10**: action trigger: drive(t) > threshold × (1 + NT.caution). fatigue_penalty = count_recent × rate.
**V11**: teacher feedback → queue → merge_pending before next attention. never immediate.
**V12**: LangGraph node fn returns dict (patch), not full state.
**V13**: NEVER return CogCoreState instance from a node fn → double accumulation (T5).
**V14**: ALL code edits via self-modify → path ∈ {src/cogcore/, tests/, docs/, scripts/, experiments/}. ⊥ edit config.toml/pyproject.toml/AGENTS.md.
**V15**: commit message self-modify → must contain `[auto-iterate]`.
**V16**: test() fail → skip commit, error log, keep as untracked.
**V17**: reload → 10 tick error_log < 3, else auto git revert.
**V18**: E0X experiment → must pass §G4 4 conditions before claiming "pass".
**V19**: ∀ E0X dataset → SHA-256 in manifest.json.
**V20**: paper/ dir → read-only. never modify.
**V21**: `grep -rn "global " src/cogcore/` → zero results (T2).

## §T — 任务表

|id|status|task|cites|
|---|---|---|---|
|M1|-|M0.x 基础骨架 + 10 阶段调度|passed|
|M2|-|实验 E01-E17 全部复现通过|§G4,V18|
|M3.1|x|FastAPI 5 端点 + 13 测试|§I.api|
|M3.2|x|LLMRegistry + circular fallback (14 测试)|§I|
|M3.3|x|MCP 工具适配器 (15 测试 + DeepSeek e2e)|§I|
|M3.4|x|L1 retry + L2 fallback + L3 gate (20 测试)|§I|
|M3.5|x|代码感知工具: 6 code + 5 git + 2 exec + 闸门 (50 测试)|§V14-17|
|M3.6|x|自迭代元循环 9 步 + 5 重闸门 + CLI (16 测试)|§I.self-iterate|
|M3.7|.|E21 奖惩反事实 + E22 延迟压力测试|G4|
|M4.1|.|嵌入语义层 sqlite-vec/numpy|§I|
|M4.2|.|SQLite 维护 prune/vacuum/backup|§I|
|M4.3|.|JSON trace + sqlite-stats + audit trail|§I|
|M4.4|.|evals/ 评测套件|§I|
|M4.5|.|E23 多粒度感受器|§G4|
|M5.1|.|单进程部署 `python -m cogcore serve`|§I|
|M5.2|.|JWT + slowapi|§I|
|M5.3|.|5 业务场景 sc-01~05|§I|
|M5.4|.|E24 多模态 + E25 叙事盲评|§G4|

## §B — Bug 日志

|id|date|cause|fix|
|---|---|---|---|
|B1|2026-04-20|HDB 2-gram tokenization 不区分子符顺序 |E01 判据需跨原子 n-gram|
|B2|2026-05-30|嵌套 state 字段部分 dict 覆盖丢数据 (T1)|`model_copy(update={...})` 模式|
|B3|2026-06-05|Fluent API 返回完整 State → Reducer 双重累加 (T5)|`StateUpdater.to_patch()` 返回 dict, not State|
|B4|2026-06-05|MCP `_request` 默认 30s 超时 → 大工具超时|↑60s|
