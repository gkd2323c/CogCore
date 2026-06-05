from uuid import uuid4
import pytest

from cogcore.types import StimulusAtom, AttributeAtom, Modality, StimulusSource, AtomEnergy
from cogcore.state_pool import StatePool


def test_stimulus_atom_attribute_views():
    # Setup host atom
    host_id = uuid4()
    attr_static = AttributeAtom(
        anchor_id=host_id,
        attr_name="color",
        attr_value="red",
        binding_score=0.0
    )
    attr_dynamic = AttributeAtom(
        anchor_id=host_id,
        attr_name="speed",
        attr_value="fast",
        binding_score=1.5
    )

    atom = StimulusAtom(
        source=StimulusSource.EXTERNAL,
        content="test_object",
        modality=Modality.VISUAL,
        trace={"origin": "test"},
        attributes=[attr_static, attr_dynamic]
    )

    # Assert views return only attributes matching the respective binding_score threshold
    assert atom.packet_attribute_by_name == {"color": "red"}
    assert atom.bound_attribute_by_name == {"speed": "fast"}


def test_apply_stimulus_packet_success():
    pool = StatePool()
    anchor_id = uuid4()
    host_atom = StimulusAtom(
        id=anchor_id,
        source=StimulusSource.EXTERNAL,
        content="host",
        modality=Modality.VISUAL,
        energy=AtomEnergy(real=1.0, virtual=0.5),
        trace={"origin": "test"}
    )
    pool.add(host_atom)

    attrs = [
        AttributeAtom(anchor_id=anchor_id, attr_name="weight", attr_value="10kg"),
        AttributeAtom(anchor_id=anchor_id, attr_name="shape", attr_value="box")
    ]

    pool.apply_stimulus_packet(
        anchor_id=anchor_id,
        attributes=attrs,
        add_standalone=True,
        modality=Modality.VISUAL,
        source=StimulusSource.EXTERNAL
    )

    # 1. Host attributes bound
    assert len(host_atom.attributes) == 2
    assert host_atom.packet_attribute_by_name == {"weight": "10kg", "shape": "box"}

    # 2. Standalone atoms in pool
    all_atoms = pool.get_all()
    standalone_atoms = [
        a for a in all_atoms
        if isinstance(a.content, dict) and a.content.get("parent") == anchor_id
    ]
    assert len(standalone_atoms) == 2
    
    # Assert properties on standalone atoms
    weight_atom = next(a for a in standalone_atoms if a.content.get("attribute_name") == "weight")
    assert weight_atom.content.get("attribute_value") == "10kg"
    assert weight_atom.modality == Modality.VISUAL
    assert weight_atom.source == StimulusSource.EXTERNAL
    assert weight_atom.energy.real == 1.0
    assert weight_atom.energy.virtual == 0.5


def test_apply_stimulus_packet_folded():
    pool = StatePool()
    anchor_id = uuid4()
    host_atom = StimulusAtom(
        id=anchor_id,
        source=StimulusSource.EXTERNAL,
        content="host",
        modality=Modality.VISUAL,
        energy=AtomEnergy(real=1.0, virtual=0.5),
        trace={"origin": "test"}
    )
    pool.add(host_atom)

    attrs = [
        AttributeAtom(anchor_id=anchor_id, attr_name="weight", attr_value="10kg")
    ]

    pool.apply_stimulus_packet(
        anchor_id=anchor_id,
        attributes=attrs,
        add_standalone=False,  # Folded control
        modality=Modality.VISUAL,
        source=StimulusSource.EXTERNAL
    )

    # Host gets attribute, but no standalone atom added
    assert len(host_atom.attributes) == 1
    assert len(pool.get_all()) == 1  # Only the host atom is in the pool


def test_apply_stimulus_packet_missing_anchor():
    pool = StatePool()
    # Apply to a random anchor id that is not in the pool
    attrs = [
        AttributeAtom(anchor_id=uuid4(), attr_name="weight", attr_value="10kg")
    ]
    pool.apply_stimulus_packet(
        anchor_id=uuid4(),
        attributes=attrs,
        add_standalone=True
    )
    assert len(pool.get_all()) == 0


def test_bind_attribute_node_to_object_success():
    pool = StatePool()
    anchor_id = uuid4()
    host_atom = StimulusAtom(
        id=anchor_id,
        source=StimulusSource.EXTERNAL,
        content="host",
        modality=Modality.VISUAL,
        energy=AtomEnergy(real=1.2, virtual=0.8),
        trace={"origin": "test"}
    )
    pool.add(host_atom)

    success = pool.bind_attribute_node_to_object(
        anchor_id=anchor_id,
        attr_name="temperature",
        attr_value="hot",
        role="attribute",
        binding_score=1.0,
        modality=Modality.TOOL_STATE,
        source=StimulusSource.INTERNAL
    )

    assert success is True
    # Host gets attribute in bound_attribute_by_name view
    assert host_atom.bound_attribute_by_name == {"temperature": "hot"}
    assert host_atom.packet_attribute_by_name == {}

    # Standalone atom created and properties preserved
    standalone_atoms = [
        a for a in pool.get_all()
        if isinstance(a.content, dict) and a.content.get("parent") == anchor_id
    ]
    assert len(standalone_atoms) == 1
    sa = standalone_atoms[0]
    assert sa.content.get("attribute_name") == "temperature"
    assert sa.content.get("attribute_value") == "hot"
    assert sa.modality == Modality.TOOL_STATE
    assert sa.source == StimulusSource.INTERNAL
    assert sa.energy.real == 1.2
    assert sa.energy.virtual == 0.8


def test_bind_attribute_node_to_object_role_validation():
    pool = StatePool()
    anchor_id = uuid4()
    host_atom = StimulusAtom(
        id=anchor_id,
        source=StimulusSource.EXTERNAL,
        content="host",
        modality=Modality.VISUAL,
        trace={"origin": "test"}
    )
    pool.add(host_atom)

    # Invalid role "feature" should be rejected
    success = pool.bind_attribute_node_to_object(
        anchor_id=anchor_id,
        attr_name="temperature",
        attr_value="hot",
        role="feature",  # illegal
    )

    assert success is False
    assert len(host_atom.attributes) == 0
    assert len(pool.get_all()) == 1  # No standalone atom created


def test_bind_attribute_node_to_object_missing_anchor():
    pool = StatePool()
    success = pool.bind_attribute_node_to_object(
        anchor_id=uuid4(),
        attr_name="temperature",
        attr_value="hot",
        role="attribute"
    )
    assert success is False
    assert len(pool.get_all()) == 0
