from uuid import uuid4
import pytest

from cogcore.types import Structure
from cogcore.hdb import HDB


def test_hdb_set_transition_weight():
    hdb = HDB()
    id1 = uuid4()
    id2 = uuid4()
    
    # Defaults to 1.0 when not set
    assert hdb._transition_weights.get((id1, id2), 1.0) == 1.0
    
    # Can set weight
    hdb.set_transition_weight(id1, id2, 2.5)
    assert hdb._transition_weights.get((id1, id2), 1.0) == 2.5


def test_run_induction_propagation_basic():
    hdb = HDB()
    struct_A = Structure(index_key=["a"])
    struct_AB = Structure(index_key=["a", "b"], depth=1)
    
    hdb._structures[struct_A.id] = struct_A
    hdb._structures[struct_AB.id] = struct_AB
    
    # Setup transition A -> AB
    struct_A.local_db["b"] = struct_AB.id
    
    # Run propagation
    candidates = hdb.run_induction_propagation(struct_A.id, virtual_energy=1.5)
    
    assert len(candidates) == 1
    target, energy = candidates[0]
    assert target.id == struct_AB.id
    # propagated energy = input energy * weight (default 1.0)
    assert energy == pytest.approx(1.5)


def test_run_induction_propagation_budget_pruning():
    hdb = HDB()
    struct_A = Structure(index_key=["a"])
    struct_AB = Structure(index_key=["a", "b"], depth=1)
    
    hdb._structures[struct_A.id] = struct_A
    hdb._structures[struct_AB.id] = struct_AB
    struct_A.local_db["b"] = struct_AB.id
    
    # Case 1: Input energy is below threshold -> pruned early
    candidates = hdb.run_induction_propagation(struct_A.id, virtual_energy=0.05, threshold=0.1)
    assert len(candidates) == 0
    
    # Case 2: Propagated energy falls below threshold due to weight
    hdb.set_transition_weight(struct_A.id, struct_AB.id, 0.2)
    candidates = hdb.run_induction_propagation(struct_A.id, virtual_energy=0.4, threshold=0.1)  # 0.4 * 0.2 = 0.08 < 0.1
    assert len(candidates) == 0
    
    # Case 3: Propagated energy meets threshold
    candidates = hdb.run_induction_propagation(struct_A.id, virtual_energy=0.5, threshold=0.1)  # 0.5 * 0.2 = 0.1 >= 0.1
    assert len(candidates) == 1
    assert candidates[0][0].id == struct_AB.id


def test_run_induction_propagation_weight_sorting():
    hdb = HDB()
    struct_A = Structure(index_key=["a"])
    struct_AB = Structure(index_key=["a", "b"], depth=1)
    struct_AC = Structure(index_key=["a", "c"], depth=1)
    
    hdb._structures[struct_A.id] = struct_A
    hdb._structures[struct_AB.id] = struct_AB
    hdb._structures[struct_AC.id] = struct_AC
    
    # Setup transitions
    struct_A.local_db["b"] = struct_AB.id
    struct_A.local_db["c"] = struct_AC.id
    
    # Case 1: AB weight > AC weight
    hdb.set_transition_weight(struct_A.id, struct_AB.id, 1.8)
    hdb.set_transition_weight(struct_A.id, struct_AC.id, 0.9)
    
    candidates = hdb.run_induction_propagation(struct_A.id, virtual_energy=1.0)
    assert len(candidates) == 2
    assert candidates[0][0].id == struct_AB.id
    assert candidates[0][1] == pytest.approx(1.8)
    assert candidates[1][0].id == struct_AC.id
    assert candidates[1][1] == pytest.approx(0.9)
    
    # Case 2: Swap weights so AC weight > AB weight
    hdb.set_transition_weight(struct_A.id, struct_AB.id, 0.9)
    hdb.set_transition_weight(struct_A.id, struct_AC.id, 1.8)
    
    candidates = hdb.run_induction_propagation(struct_A.id, virtual_energy=1.0)
    assert len(candidates) == 2
    assert candidates[0][0].id == struct_AC.id
    assert candidates[0][1] == pytest.approx(1.8)
    assert candidates[1][0].id == struct_AB.id
    assert candidates[1][1] == pytest.approx(0.9)


def test_run_induction_propagation_termination():
    hdb = HDB()
    struct_ABCD = Structure(index_key=["a", "b", "c", "d"], depth=3)
    hdb._structures[struct_ABCD.id] = struct_ABCD
    
    # ABCD is a terminal structure with no transitions in local_db
    candidates = hdb.run_induction_propagation(struct_ABCD.id, virtual_energy=2.0)
    assert len(candidates) == 0


def test_hdb_clear():
    hdb = HDB()
    id1 = uuid4()
    id2 = uuid4()
    hdb.set_transition_weight(id1, id2, 3.0)
    
    assert len(hdb._transition_weights) == 1
    hdb.clear()
    assert len(hdb._transition_weights) == 0
