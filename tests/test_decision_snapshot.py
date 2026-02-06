"""
Decision Snapshot Tests.

Tests for the governance and audit trail system.
Verifies:
    - Snapshot creation and serialization
    - Chain integrity verification
    - Registry persistence
    - Snapshot content hashing
"""

import pytest
from datetime import datetime
from pathlib import Path
import tempfile


@pytest.mark.ci
def test_decision_snapshot_creation():
    """DecisionSnapshot can be created with required fields."""
    from septage_model.artifacts.decision_snapshot import (
        DecisionSnapshot,
        SnapshotType,
        DecisionOutcome,
        FrozenDRLStatus,
        FrozenGateStatus,
        FrozenParameters,
    )
    from septage_model.artifacts.versioning import SemanticVersion
    
    snapshot = DecisionSnapshot(
        snapshot_type=SnapshotType.DRL_GATE,
        version=SemanticVersion(1, 0, 0),
        created_at=datetime.now(),
        created_by="test",
        outcome=DecisionOutcome.APPROVED,
        rationale="Test snapshot creation",
    )
    
    assert snapshot.snapshot_type == SnapshotType.DRL_GATE
    assert snapshot.is_approved
    assert snapshot.content_hash  # Hash should be computed


@pytest.mark.ci
def test_snapshot_serialization_roundtrip():
    """Snapshot can be serialized to dict and back."""
    from septage_model.artifacts.decision_snapshot import (
        DecisionSnapshot,
        SnapshotType,
        DecisionOutcome,
        FrozenDRLStatus,
        FrozenGateStatus,
        FrozenParameters,
    )
    from septage_model.artifacts.versioning import SemanticVersion
    
    drl_status = FrozenDRLStatus(
        achieved_level=3,
        criteria_passed=["mass_balance_validated", "energy_balance_validated"],
        criteria_failed=["dewatering_params_validated"],
        blocking_criteria=["dewatering_params_validated"],
    )
    
    gates = [
        FrozenGateStatus(name="Maintenance Budget", passed=True, value=23000, threshold=35000),
        FrozenGateStatus(name="Payback Period", passed=True, value=14.5, threshold=15.0),
    ]
    
    parameters = FrozenParameters(
        max_maintenance_budget=35000,
        max_payback_years=15.0,
        max_callouts_per_week=1.0,
    )
    
    original = DecisionSnapshot(
        snapshot_type=SnapshotType.DRL_GATE,
        version=SemanticVersion(1, 2, 3),
        created_at=datetime.now(),
        created_by="test",
        outcome=DecisionOutcome.CONDITIONAL,
        rationale="Testing roundtrip",
        conditions=["Pending vendor data"],
        drl_status=drl_status,
        gates=gates,
        parameters=parameters,
        previous_hash="abc123",
    )
    
    # Serialize
    data = original.to_dict()
    
    # Deserialize
    restored = DecisionSnapshot.from_dict(data)
    
    assert restored.snapshot_type == original.snapshot_type
    assert restored.version.major == original.version.major
    assert restored.outcome == original.outcome
    assert restored.drl_status.achieved_level == 3
    assert len(restored.gates) == 2
    assert restored.parameters.max_maintenance_budget == 35000


@pytest.mark.ci
def test_snapshot_registry_chain_integrity():
    """Registry validates chain integrity on append."""
    from septage_model.artifacts.decision_snapshot import (
        DecisionSnapshot,
        SnapshotType,
        DecisionOutcome,
        SnapshotRegistry,
    )
    from septage_model.artifacts.versioning import SemanticVersion
    
    registry = SnapshotRegistry()
    
    # First snapshot (genesis)
    snapshot1 = DecisionSnapshot(
        snapshot_type=SnapshotType.DRL_GATE,
        version=SemanticVersion(1, 0, 0),
        created_at=datetime.now(),
        created_by="test",
        outcome=DecisionOutcome.APPROVED,
        rationale="Genesis snapshot",
        previous_hash=None,
    )
    registry.append(snapshot1)
    
    # Second snapshot - must link to first
    snapshot2 = DecisionSnapshot(
        snapshot_type=SnapshotType.DRL_GATE,
        version=SemanticVersion(1, 1, 0),
        created_at=datetime.now(),
        created_by="test",
        outcome=DecisionOutcome.APPROVED,
        rationale="Second snapshot",
        previous_hash=snapshot1.content_hash,
    )
    registry.append(snapshot2)
    
    # Chain should be valid
    assert registry.verify_chain()
    
    # Third snapshot with wrong hash should fail
    snapshot3_bad = DecisionSnapshot(
        snapshot_type=SnapshotType.DRL_GATE,
        version=SemanticVersion(1, 2, 0),
        created_at=datetime.now(),
        created_by="test",
        outcome=DecisionOutcome.APPROVED,
        rationale="Bad snapshot",
        previous_hash="wrong_hash",
    )
    
    with pytest.raises(ValueError, match="Chain integrity violation"):
        registry.append(snapshot3_bad)


@pytest.mark.ci
def test_snapshot_registry_persistence():
    """Registry can be saved and loaded."""
    from septage_model.artifacts.decision_snapshot import (
        DecisionSnapshot,
        SnapshotType,
        DecisionOutcome,
        SnapshotRegistry,
    )
    from septage_model.artifacts.versioning import SemanticVersion
    
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "snapshots.json"
        
        # Create and save registry
        registry = SnapshotRegistry()
        snapshot = DecisionSnapshot(
            snapshot_type=SnapshotType.PARAMETER_LOCK,
            version=SemanticVersion(1, 0, 0),
            created_at=datetime.now(),
            created_by="test",
            outcome=DecisionOutcome.APPROVED,
            rationale="Test persistence",
        )
        registry.append(snapshot)
        registry.save(path)
        
        # Load and verify
        loaded = SnapshotRegistry.load(path)
        assert len(loaded.snapshots) == 1
        assert loaded.snapshots[0].rationale == "Test persistence"
        assert loaded.verify_chain()


@pytest.mark.ci
def test_snapshot_content_hash_deterministic():
    """Same content produces same hash."""
    from septage_model.artifacts.decision_snapshot import (
        DecisionSnapshot,
        SnapshotType,
        DecisionOutcome,
    )
    from septage_model.artifacts.versioning import SemanticVersion
    
    fixed_time = datetime(2024, 1, 15, 12, 0, 0)
    
    snapshot1 = DecisionSnapshot(
        snapshot_type=SnapshotType.DRL_GATE,
        version=SemanticVersion(1, 0, 0),
        created_at=fixed_time,
        created_by="test",
        outcome=DecisionOutcome.APPROVED,
        rationale="Deterministic test",
    )
    
    snapshot2 = DecisionSnapshot(
        snapshot_type=SnapshotType.DRL_GATE,
        version=SemanticVersion(1, 0, 0),
        created_at=fixed_time,
        created_by="test",
        outcome=DecisionOutcome.APPROVED,
        rationale="Deterministic test",
    )
    
    assert snapshot1.content_hash == snapshot2.content_hash


@pytest.mark.ci
def test_snapshot_report_generation():
    """Snapshot report can be generated."""
    from septage_model.artifacts.decision_snapshot import (
        DecisionSnapshot,
        SnapshotType,
        DecisionOutcome,
        FrozenDRLStatus,
        FrozenGateStatus,
        generate_snapshot_report,
    )
    from septage_model.artifacts.versioning import SemanticVersion
    
    snapshot = DecisionSnapshot(
        snapshot_type=SnapshotType.DRL_GATE,
        version=SemanticVersion(1, 0, 0),
        created_at=datetime.now(),
        created_by="test",
        outcome=DecisionOutcome.APPROVED,
        rationale="Report generation test",
        drl_status=FrozenDRLStatus(
            achieved_level=3,
            criteria_passed=["a", "b"],
            criteria_failed=["c"],
            blocking_criteria=["c"],
        ),
        gates=[
            FrozenGateStatus("Test Gate", True, 100, 200),
        ],
    )
    
    report = generate_snapshot_report(snapshot)
    
    assert "DECISION SNAPSHOT" in report
    assert "DRL-3" in report
    assert "Test Gate" in report
    assert "Report generation test" in report


@pytest.mark.ci
def test_registry_get_approved_drl_level():
    """Registry correctly tracks highest approved DRL level."""
    from septage_model.artifacts.decision_snapshot import (
        DecisionSnapshot,
        SnapshotType,
        DecisionOutcome,
        SnapshotRegistry,
        FrozenDRLStatus,
    )
    from septage_model.artifacts.versioning import SemanticVersion
    
    registry = SnapshotRegistry()
    
    # Add DRL-2 approval
    snapshot1 = DecisionSnapshot(
        snapshot_type=SnapshotType.DRL_GATE,
        version=SemanticVersion(1, 0, 0),
        created_at=datetime.now(),
        created_by="test",
        outcome=DecisionOutcome.APPROVED,
        rationale="DRL-2 achieved",
        drl_status=FrozenDRLStatus(
            achieved_level=2,
            criteria_passed=["a"],
            criteria_failed=[],
            blocking_criteria=[],
        ),
    )
    registry.append(snapshot1)
    
    # Add DRL-3 approval
    snapshot2 = DecisionSnapshot(
        snapshot_type=SnapshotType.DRL_GATE,
        version=SemanticVersion(1, 1, 0),
        created_at=datetime.now(),
        created_by="test",
        outcome=DecisionOutcome.APPROVED,
        rationale="DRL-3 achieved",
        drl_status=FrozenDRLStatus(
            achieved_level=3,
            criteria_passed=["a", "b"],
            criteria_failed=[],
            blocking_criteria=[],
        ),
        previous_hash=snapshot1.content_hash,
    )
    registry.append(snapshot2)
    
    assert registry.get_approved_drl_level() == 3


@pytest.mark.ci
def test_frozen_gate_status_serialization():
    """FrozenGateStatus roundtrips correctly."""
    from septage_model.artifacts.decision_snapshot import FrozenGateStatus
    
    original = FrozenGateStatus(
        name="Maintenance Budget",
        passed=True,
        value=23456.78,
        threshold=35000.0,
    )
    
    data = original.to_dict()
    restored = FrozenGateStatus.from_dict(data)
    
    assert restored.name == original.name
    assert restored.passed == original.passed
    assert restored.value == original.value
    assert restored.threshold == original.threshold
