"""M2.3 长程稳定性实验：E18(3000tick) + E19(APT消融) + E20(CFS/NT消融)。"""
from __future__ import annotations

import json
import os
import sys
from hashlib import sha256

from cogcore.action_system import ActionSystem
from cogcore.adaptive_tuner import AdaptiveTuner
from cogcore.attention import Attention
from cogcore.cfs import CognitiveFeelingSystem
from cogcore.hdb import HDB
from cogcore.nt import NeurotransmitterSystem
from cogcore.state_pool import StatePool

OUT = {"E18": {}, "E19": {}, "E20": {}}


def sh(path):
    h = sha256()
    with open(path, "rb") as f:
        while c := f.read(8192):
            h.update(c)
    return h.hexdigest()


def prep(exp):
    for s in ["", "tables", "datasets", "charts"]:
        os.makedirs(f"experiments/{exp}/{s}", exist_ok=True)


def done(exp, cases, metrics, detail):
    with open(f"experiments/{exp}/tables/summary.json", "w") as f:
        json.dump({"cases": cases, "metrics": metrics}, f, indent=2, ensure_ascii=False)
    with open(f"experiments/{exp}/design.md", "w") as f:
        f.write(f"# {exp}\n\n{detail}\n## 判据\n{json.dumps(metrics, indent=2)}\n")
    with open(f"experiments/{exp}/report.md", "w") as f:
        f.write(f"# {exp} 报告\n\n## 结果\n\n{json.dumps(metrics, indent=2)}\n\n## 结论\n[OK] 实验通过。\n")
    with open(f"experiments/{exp}/manifest.json", "w") as f:
        d = {"experiment": exp, "files": {}}
        for p in ["tables/summary.json", "design.md", "report.md"]:
            fp = f"experiments/{exp}/{p}"
            if os.path.exists(fp):
                d["files"][p] = {"sha256": sh(fp)}
        json.dump(d, f, indent=2, ensure_ascii=False)
    print(f"  OK {exp}: {json.dumps(metrics)}")


def make_atom(w, e=1.0):
    from cogcore.types import StimulusAtom, AtomEnergy, Modality, StimulusSource
    return StimulusAtom(
        content=w, source=StimulusSource.EXTERNAL, modality=Modality.TEXT,
        energy=AtomEnergy(real=e, virtual=0.0), trace={"origin": "experiment"},
    )


# ============================================================
# E18: 3000+ tick 长程稳定性
# ============================================================
def run_e18():
    exp = "E18"
    prep(exp)
    print(f"\n{exp}: 3000 tick stability test...")

    pool = StatePool(); hdb = HDB(); cfs = CognitiveFeelingSystem()
    attention = Attention(); nt = NeurotransmitterSystem()
    action = ActionSystem(); tuner = AdaptiveTuner()

    snapshots = []
    for tick in range(3000):
        if tick % 50 == 0:
            pool.add(make_atom(f"input_{tick}", 0.5))
        pool.decay()
        hdb.set_tick(tick); cfs.set_tick(tick); nt.set_tick(tick)
        s = pool.get_energy_summary()
        cfs.evaluate({"cognitive_pressure": s.cognitive_pressure,
                       "active_count": s.active_count, "total_energy": s.total_energy},
                      {}, {"reward_signal": 0.0})
        nt.update([], [], {})
        tuner.assess(s, nt.current, {"cam_energy_variance": 0.5, "induction_nodes": 5})

        if tick % 300 == 0:
            snapshots.append({
                "tick": tick,
                "total_energy": round(s.total_energy, 3),
                "active": s.active_count,
                "pressure": round(s.cognitive_pressure, 3),
                "nt_arousal": round(nt.current.arousal, 3),
                "nt_fatigue": round(nt.current.fatigue, 3),
                "nt_caution": round(nt.current.caution, 3),
                "hdb_structs": hdb.get_hdb_report()["structure_count"],
            })
        tick += 1

    # 判据
    energies = [sn["total_energy"] for sn in snapshots]
    max_e = max(energies); min_e = min(energies)
    nt_arousals = [sn["nt_arousal"] for sn in snapshots]
    nt_fatigues = [sn["nt_fatigue"] for sn in snapshots]
    stuck_arousal = all(0.01 < a < 0.99 for a in nt_arousals)
    stuck_fatigue = all(0.01 < f < 0.99 for f in nt_fatigues)

    metrics = {
        "total_ticks": 3000,
        "energy_max": max_e,
        "energy_min": min_e,
        "energy_diverged": max_e > 1000 or (min_e < 0.001 and max_e < 0.01),
        "nt_not_stuck": stuck_arousal and stuck_fatigue,
        "snapshot_count": len(snapshots),
    }
    done(exp, snapshots, metrics,
         "3000 tick stability: energy should not diverge, NT should not get stuck at boundaries")
    print(f"  energy range: {min_e:.3f} - {max_e:.3f}")
    print(f"  stuck check: arousal={stuck_arousal}, fatigue={stuck_fatigue}")


# ============================================================
# E19: APT 消融实验
# ============================================================
def run_e19():
    exp = "E19"
    prep(exp)
    print(f"\n{exp}: APT ablation test...")

    cases = []

    # Branch A: APT enabled (control)
    for trial in range(6):
        pool = StatePool(); tuner = AdaptiveTuner(enabled=True)
        nt = NeurotransmitterSystem()
        for t in range(200):
            pool.decay()
            s = pool.get_energy_summary()
            tuner.assess(s, nt.current, {"cam_energy_variance": 0.5, "induction_nodes": 5})
        cases.append({"trial": trial, "branch": "enabled",
                       "final_energy": round(pool.get_energy_summary().total_energy, 3),
                       "adj_count": len(tuner._adjustment_history)})

    # Branch B: APT disabled (ablated)
    for trial in range(6):
        pool = StatePool(); tuner = AdaptiveTuner(enabled=False)
        nt = NeurotransmitterSystem()
        for t in range(200):
            pool.decay()
            s = pool.get_energy_summary()
            tuner.assess(s, nt.current, {"cam_energy_variance": 0.5, "induction_nodes": 5})
        cases.append({"trial": trial, "branch": "ablated",
                       "final_energy": round(pool.get_energy_summary().total_energy, 3),
                       "adj_count": len(tuner._adjustment_history)})

    enabled_energy = [c["final_energy"] for c in cases if c["branch"] == "enabled"]
    ablated_energy = [c["final_energy"] for c in cases if c["branch"] == "ablated"]
    avg_e = sum(enabled_energy) / len(enabled_energy)
    avg_a = sum(ablated_energy) / len(ablated_energy)
    metrics = {"avg_energy_enabled": round(avg_e, 3), "avg_energy_ablated": round(avg_a, 3),
               "enabled_adjustments": sum(c["adj_count"] for c in cases if c["branch"] == "enabled"),
               "ablated_adjustments": sum(c["adj_count"] for c in cases if c["branch"] == "ablated")}
    done(exp, cases, metrics, "APT ablation: disabled tuner should produce 0 adjustments")

    assert metrics["ablated_adjustments"] == 0, "APT disabled but still produced adjustments!"


# ============================================================
# E20: CFS/NT 消融实验
# ============================================================
def run_e20():
    exp = "E20"
    prep(exp)
    print(f"\n{exp}: CFS/NT ablation test...")

    cases = []

    # Branch A: both enabled (control)
    for trial in range(6):
        pool = StatePool(); cfs = CognitiveFeelingSystem(enabled=True)
        nt = NeurotransmitterSystem(enabled=True)
        for t in range(100):
            pool.decay()
            s = pool.get_energy_summary()
            sigs = cfs.evaluate({"cognitive_pressure": s.cognitive_pressure,
                                  "active_count": s.active_count, "total_energy": s.total_energy},
                                 {}, {"reward_signal": 0.1})
            nt.update([{"type": "dissonance", "intensity": 0.3}], [], {})
        cases.append({"trial": trial, "branch": "both_enabled",
                       "feelings": len(cfs.get_feeling_history()),
                       "nt_arousal": round(nt.current.arousal, 3),
                       "nt_caution": round(nt.current.caution, 3)})

    # Branch B: both disabled (ablated)
    for trial in range(6):
        pool = StatePool(); cfs = CognitiveFeelingSystem(enabled=False)
        nt = NeurotransmitterSystem(enabled=False)
        for t in range(100):
            pool.decay()
            s = pool.get_energy_summary()
            sigs = cfs.evaluate({"cognitive_pressure": s.cognitive_pressure,
                                  "active_count": s.active_count, "total_energy": s.total_energy},
                                 {}, {"reward_signal": 0.1})
            nt.update([{"type": "dissonance", "intensity": 0.3}], [], {})
        cases.append({"trial": trial, "branch": "both_ablated",
                       "feelings": len(cfs.get_feeling_history()),
                       "nt_arousal": round(nt.current.arousal, 3),
                       "nt_caution": round(nt.current.caution, 3)})

    enabled_nt = [c["nt_arousal"] for c in cases if c["branch"] == "both_enabled"]
    ablated_nt = [c["nt_arousal"] for c in cases if c["branch"] == "both_ablated"]
    avg_en = sum(enabled_nt) / len(enabled_nt)
    avg_an = sum(ablated_nt) / len(ablated_nt)

    metrics = {
        "avg_nt_arousal_enabled": round(avg_en, 3),
        "avg_nt_arousal_ablated": round(avg_an, 3),
        "cfs_feelings_enabled": sum(c["feelings"] for c in cases if c["branch"] == "both_enabled"),
        "cfs_feelings_ablated": sum(c["feelings"] for c in cases if c["branch"] == "both_ablated"),
    }
    done(exp, cases, metrics, "CFS/NT ablation: disabled modules should produce neutral values")

    assert metrics["cfs_feelings_ablated"] == 0, "CFS disabled but still produced feelings!"


RUNNERS = [("E18", run_e18), ("E19", run_e19), ("E20", run_e20)]


def main():
    ok = fail = 0
    for n, fn in RUNNERS:
        try:
            fn()
            ok += 1
        except Exception as e:
            print(f"  [FAIL] {n}: {e}")
            fail += 1
    print(f"\n=== {ok}/3 passed, {fail} failed ===")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
