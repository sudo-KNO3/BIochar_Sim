"""
Decision Snapshot Module - Freeze and lock design state.

Provides immutable snapshots of the design state for:
    - Governance checkpoints
    - Audit trails
    - Rollback capability
    - DRL gate freeze points

A DecisionSnapshot captures:
    - DRL assessment at freeze time
    - Gate report status
    - Parameter values (frozen constants)
    - FMEA state
    - Vendor validation status
    - Human decision rationale

Snapshots are append-only and cryptographically chained.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
from enum import Enum
import json

from .versioning import (
    compute_content_hash,
    ArtifactType,
    SemanticVersion,
)


class SnapshotType(Enum):
    """Types of decision snapshots."""
    DRL_GATE = "drl_gate"           # DRL level advancement checkpoint
    PARAMETER_LOCK = "param_lock"   # Parameter values frozen
    VENDOR_SELECT = "vendor_select" # Vendor selection decision
    DESIGN_REVIEW = "design_review" # Formal design review
    GO_NO_GO = "go_no_go"           # Major milestone decision
    ROLLBACK = "rollback"           # Intentional rollback to prior state


class DecisionOutcome(Enum):
    """Outcome of a decision."""
    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    CONDITIONAL = "conditional"


@dataclass
class FrozenGateStatus:
    """Frozen gate status at snapshot time."""
    name: str
    passed: bool
    value: float
    threshold: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "value": self.value,
            "threshold": self.threshold,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FrozenGateStatus':
        return cls(
            name=data["name"],
            passed=data["passed"],
            value=data["value"],
            threshold=data["threshold"],
        )


@dataclass
class FrozenDRLStatus:
    """Frozen DRL status at snapshot time."""
    achieved_level: int
    criteria_passed: List[str]
    criteria_failed: List[str]
    blocking_criteria: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "achieved_level": self.achieved_level,
            "criteria_passed": self.criteria_passed,
            "criteria_failed": self.criteria_failed,
            "blocking_criteria": self.blocking_criteria,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FrozenDRLStatus':
        return cls(
            achieved_level=data["achieved_level"],
            criteria_passed=data["criteria_passed"],
            criteria_failed=data["criteria_failed"],
            blocking_criteria=data["blocking_criteria"],
        )


@dataclass
class FrozenParameters:
    """Frozen parameter values at snapshot time."""
    max_maintenance_budget: float
    max_payback_years: float
    max_callouts_per_week: float
    custom_parameters: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_maintenance_budget": self.max_maintenance_budget,
            "max_payback_years": self.max_payback_years,
            "max_callouts_per_week": self.max_callouts_per_week,
            "custom_parameters": self.custom_parameters,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FrozenParameters':
        return cls(
            max_maintenance_budget=data["max_maintenance_budget"],
            max_payback_years=data["max_payback_years"],
            max_callouts_per_week=data["max_callouts_per_week"],
            custom_parameters=data.get("custom_parameters", {}),
        )


@dataclass
class DecisionSnapshot:
    """
    Immutable snapshot of design state at a decision point.
    
    Snapshots form a cryptographic chain:
        - Each snapshot includes the hash of the previous snapshot
        - Tampering with any snapshot breaks the chain
        - Provides audit trail for regulatory review
    
    Attributes:
        snapshot_id: Unique identifier (type_v{version}_{hash})
        snapshot_type: Type of decision being recorded
        version: Semantic version of this snapshot
        created_at: When this snapshot was created
        created_by: Who/what created this snapshot
        
        outcome: Decision outcome (approved/rejected/deferred/conditional)
        rationale: Human-readable explanation of the decision
        conditions: Any conditions attached to the decision
        
        drl_status: Frozen DRL assessment
        gates: Frozen gate status
        parameters: Frozen parameter values
        
        previous_hash: Hash of prior snapshot (chain verification)
        content_hash: Hash of this snapshot's content
    """
    snapshot_type: SnapshotType
    version: SemanticVersion
    created_at: datetime
    created_by: str
    
    outcome: DecisionOutcome
    rationale: str
    conditions: List[str] = field(default_factory=list)
    
    drl_status: Optional[FrozenDRLStatus] = None
    gates: List[FrozenGateStatus] = field(default_factory=list)
    parameters: Optional[FrozenParameters] = None
    
    previous_hash: Optional[str] = None
    content_hash: str = ""
    
    def __post_init__(self):
        """Compute content hash after initialization."""
        if not self.content_hash:
            self.content_hash = self._compute_hash()
    
    def _compute_hash(self) -> str:
        """Compute deterministic hash of snapshot content."""
        content = {
            "snapshot_type": self.snapshot_type.value,
            "version": str(self.version),
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "outcome": self.outcome.value,
            "rationale": self.rationale,
            "conditions": self.conditions,
            "drl_status": self.drl_status.to_dict() if self.drl_status else None,
            "gates": [g.to_dict() for g in self.gates],
            "parameters": self.parameters.to_dict() if self.parameters else None,
            "previous_hash": self.previous_hash,
        }
        return compute_content_hash(content)
    
    @property
    def snapshot_id(self) -> str:
        """Full snapshot identifier."""
        return f"{self.snapshot_type.value}_v{self.version}_{self.content_hash}"
    
    @property
    def short_id(self) -> str:
        """Short snapshot identifier."""
        return f"{self.snapshot_type.value}_v{self.version}"
    
    @property
    def is_approved(self) -> bool:
        """Check if decision was approved."""
        return self.outcome == DecisionOutcome.APPROVED
    
    @property
    def all_gates_passed(self) -> bool:
        """Check if all gates passed at snapshot time."""
        return all(g.passed for g in self.gates)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_type": self.snapshot_type.value,
            "version": str(self.version),
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "outcome": self.outcome.value,
            "rationale": self.rationale,
            "conditions": self.conditions,
            "drl_status": self.drl_status.to_dict() if self.drl_status else None,
            "gates": [g.to_dict() for g in self.gates],
            "parameters": self.parameters.to_dict() if self.parameters else None,
            "previous_hash": self.previous_hash,
            "content_hash": self.content_hash,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DecisionSnapshot':
        """Deserialize from dictionary."""
        drl_status = None
        if data.get("drl_status"):
            drl_status = FrozenDRLStatus.from_dict(data["drl_status"])
        
        parameters = None
        if data.get("parameters"):
            parameters = FrozenParameters.from_dict(data["parameters"])
        
        gates = [FrozenGateStatus.from_dict(g) for g in data.get("gates", [])]
        
        snapshot = cls(
            snapshot_type=SnapshotType(data["snapshot_type"]),
            version=SemanticVersion.parse(data["version"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            created_by=data["created_by"],
            outcome=DecisionOutcome(data["outcome"]),
            rationale=data["rationale"],
            conditions=data.get("conditions", []),
            drl_status=drl_status,
            gates=gates,
            parameters=parameters,
            previous_hash=data.get("previous_hash"),
            content_hash=data.get("content_hash", ""),
        )
        return snapshot


# =============================================================================
# Snapshot Registry (Append-Only Chain)
# =============================================================================

@dataclass
class SnapshotRegistry:
    """
    Append-only registry of decision snapshots.
    
    Maintains cryptographic chain for audit integrity.
    """
    snapshots: List[DecisionSnapshot] = field(default_factory=list)
    
    @property
    def latest(self) -> Optional[DecisionSnapshot]:
        """Get the most recent snapshot."""
        return self.snapshots[-1] if self.snapshots else None
    
    @property
    def latest_hash(self) -> Optional[str]:
        """Get hash of the most recent snapshot."""
        return self.latest.content_hash if self.latest else None
    
    def append(self, snapshot: DecisionSnapshot) -> None:
        """
        Append a new snapshot to the chain.
        
        Validates chain integrity before appending.
        """
        if self.snapshots and snapshot.previous_hash != self.latest_hash:
            raise ValueError(
                f"Chain integrity violation: snapshot.previous_hash "
                f"({snapshot.previous_hash}) != latest_hash ({self.latest_hash})"
            )
        self.snapshots.append(snapshot)
    
    def verify_chain(self) -> bool:
        """
        Verify the entire chain is intact.
        
        Returns:
            True if chain is valid, False if tampered
        """
        for i, snapshot in enumerate(self.snapshots):
            # Verify content hash
            expected_hash = snapshot._compute_hash()
            if snapshot.content_hash != expected_hash:
                return False
            
            # Verify chain link (except first)
            if i > 0:
                if snapshot.previous_hash != self.snapshots[i-1].content_hash:
                    return False
        
        return True
    
    def get_by_type(self, snapshot_type: SnapshotType) -> List[DecisionSnapshot]:
        """Get all snapshots of a specific type."""
        return [s for s in self.snapshots if s.snapshot_type == snapshot_type]
    
    def get_latest_by_type(self, snapshot_type: SnapshotType) -> Optional[DecisionSnapshot]:
        """Get most recent snapshot of a specific type."""
        typed = self.get_by_type(snapshot_type)
        return typed[-1] if typed else None
    
    def get_approved_drl_level(self) -> int:
        """Get the highest approved DRL level."""
        drl_snapshots = [
            s for s in self.get_by_type(SnapshotType.DRL_GATE)
            if s.is_approved and s.drl_status
        ]
        if not drl_snapshots:
            return 0
        return max(s.drl_status.achieved_level for s in drl_snapshots)
    
    def save(self, path: Path) -> None:
        """Save registry to JSON file."""
        data = {
            "snapshots": [s.to_dict() for s in self.snapshots],
            "chain_valid": self.verify_chain(),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, path: Path) -> 'SnapshotRegistry':
        """Load registry from JSON file."""
        if not path.exists():
            return cls()
        
        with open(path, 'r') as f:
            data = json.load(f)
        
        registry = cls()
        for snapshot_data in data.get("snapshots", []):
            snapshot = DecisionSnapshot.from_dict(snapshot_data)
            registry.snapshots.append(snapshot)
        
        return registry


# =============================================================================
# Snapshot Creation Functions
# =============================================================================

def get_default_snapshot_path() -> Path:
    """Get default path for snapshot registry."""
    return Path(__file__).parent.parent.parent / ".versions" / "snapshots.json"


def get_or_create_snapshot_registry() -> SnapshotRegistry:
    """Get existing registry or create new one."""
    path = get_default_snapshot_path()
    return SnapshotRegistry.load(path)


def save_snapshot_registry(registry: SnapshotRegistry) -> None:
    """Save registry to default path."""
    path = get_default_snapshot_path()
    registry.save(path)


def create_drl_snapshot(
    drl_assessment,
    gate_report,
    outcome: DecisionOutcome,
    rationale: str,
    created_by: str = "automated",
    conditions: Optional[List[str]] = None,
    registry: Optional[SnapshotRegistry] = None,
) -> DecisionSnapshot:
    """
    Create a DRL gate snapshot from current system state.
    
    Args:
        drl_assessment: DRLAssessment from evaluate_drl()
        gate_report: GateReport from run_design_gates()
        outcome: Decision outcome
        rationale: Human-readable rationale
        created_by: Who is creating this snapshot
        conditions: Any conditions attached
        registry: Optional registry for chain linking
    
    Returns:
        DecisionSnapshot capturing the current state
    """
    from ..ci.gates import (
        MAX_MAINTENANCE_BUDGET,
        MAX_PAYBACK_YEARS,
        MAX_CALLOUTS_PER_WEEK,
    )
    
    # Freeze DRL status
    drl_status = FrozenDRLStatus(
        achieved_level=drl_assessment.achieved_drl,
        criteria_passed=[c.name for c in drl_assessment.passing_criteria],
        criteria_failed=[c.name for c in drl_assessment.failing_criteria],
        blocking_criteria=[c.name for c in drl_assessment.blocking_criteria],
    )
    
    # Freeze gate status
    gates = [
        FrozenGateStatus(
            name=g.name,
            passed=g.passed,
            value=g.value,
            threshold=g.threshold,
        )
        for g in gate_report.gates
    ]
    
    # Freeze parameters
    parameters = FrozenParameters(
        max_maintenance_budget=MAX_MAINTENANCE_BUDGET,
        max_payback_years=MAX_PAYBACK_YEARS,
        max_callouts_per_week=MAX_CALLOUTS_PER_WEEK,
    )
    
    # Determine version
    if registry:
        existing = registry.get_by_type(SnapshotType.DRL_GATE)
        if existing:
            last_version = existing[-1].version
            version = last_version.increment_minor()
        else:
            version = SemanticVersion(1, 0, 0)
        previous_hash = registry.latest_hash
    else:
        version = SemanticVersion(1, 0, 0)
        previous_hash = None
    
    snapshot = DecisionSnapshot(
        snapshot_type=SnapshotType.DRL_GATE,
        version=version,
        created_at=datetime.now(),
        created_by=created_by,
        outcome=outcome,
        rationale=rationale,
        conditions=conditions or [],
        drl_status=drl_status,
        gates=gates,
        parameters=parameters,
        previous_hash=previous_hash,
    )
    
    if registry:
        registry.append(snapshot)
    
    return snapshot


def create_parameter_lock_snapshot(
    locked_parameters: Dict[str, Any],
    rationale: str,
    created_by: str = "automated",
    registry: Optional[SnapshotRegistry] = None,
) -> DecisionSnapshot:
    """
    Create a parameter lock snapshot.
    
    Use this when freezing specific parameter values.
    
    Args:
        locked_parameters: Dict of parameter name -> value
        rationale: Why these parameters are being locked
        created_by: Who is creating this snapshot
        registry: Optional registry for chain linking
    
    Returns:
        DecisionSnapshot for the parameter lock
    """
    from ..ci.gates import (
        MAX_MAINTENANCE_BUDGET,
        MAX_PAYBACK_YEARS,
        MAX_CALLOUTS_PER_WEEK,
    )
    
    parameters = FrozenParameters(
        max_maintenance_budget=MAX_MAINTENANCE_BUDGET,
        max_payback_years=MAX_PAYBACK_YEARS,
        max_callouts_per_week=MAX_CALLOUTS_PER_WEEK,
        custom_parameters=locked_parameters,
    )
    
    # Determine version
    if registry:
        existing = registry.get_by_type(SnapshotType.PARAMETER_LOCK)
        if existing:
            last_version = existing[-1].version
            version = last_version.increment_minor()
        else:
            version = SemanticVersion(1, 0, 0)
        previous_hash = registry.latest_hash
    else:
        version = SemanticVersion(1, 0, 0)
        previous_hash = None
    
    snapshot = DecisionSnapshot(
        snapshot_type=SnapshotType.PARAMETER_LOCK,
        version=version,
        created_at=datetime.now(),
        created_by=created_by,
        outcome=DecisionOutcome.APPROVED,
        rationale=rationale,
        parameters=parameters,
        previous_hash=previous_hash,
    )
    
    if registry:
        registry.append(snapshot)
    
    return snapshot


def freeze_current_state(
    rationale: str = "Checkpoint snapshot",
    created_by: str = "automated",
) -> DecisionSnapshot:
    """
    Convenience function to freeze current system state.
    
    Runs all assessments and creates a DRL gate snapshot.
    
    Args:
        rationale: Reason for creating this snapshot
        created_by: Who is creating this snapshot
    
    Returns:
        DecisionSnapshot with current state frozen
    """
    from ..ci.design_readiness import evaluate_drl_from_results
    from ..ci.gates import run_design_gates
    from septage_model.simulation.deterministic import run_product_mode
    
    # Run simulation and assessments
    result = run_product_mode()
    gate_report = run_design_gates(result)
    drl_assessment = evaluate_drl_from_results()
    
    # Get or create registry
    registry = get_or_create_snapshot_registry()
    
    # Determine outcome based on gate status
    if gate_report.all_passed:
        outcome = DecisionOutcome.APPROVED
    else:
        outcome = DecisionOutcome.CONDITIONAL
        rationale += f" ({len(gate_report.failed_gates)} gates failing)"
    
    # Create snapshot
    snapshot = create_drl_snapshot(
        drl_assessment=drl_assessment,
        gate_report=gate_report,
        outcome=outcome,
        rationale=rationale,
        created_by=created_by,
        registry=registry,
    )
    
    # Persist
    save_snapshot_registry(registry)
    
    return snapshot


# =============================================================================
# Reporting
# =============================================================================

def generate_snapshot_report(snapshot: DecisionSnapshot) -> str:
    """Generate human-readable report for a snapshot."""
    lines = [
        "=" * 60,
        "DECISION SNAPSHOT",
        "=" * 60,
        "",
        f"ID: {snapshot.snapshot_id}",
        f"Type: {snapshot.snapshot_type.value}",
        f"Created: {snapshot.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Created By: {snapshot.created_by}",
        "",
        f"Outcome: {snapshot.outcome.value.upper()}",
        f"Rationale: {snapshot.rationale}",
    ]
    
    if snapshot.conditions:
        lines.append("")
        lines.append("Conditions:")
        for cond in snapshot.conditions:
            lines.append(f"  - {cond}")
    
    if snapshot.drl_status:
        lines.extend([
            "",
            "-" * 60,
            "DRL STATUS",
            "-" * 60,
            f"Achieved Level: DRL-{snapshot.drl_status.achieved_level}",
            f"Passing Criteria: {len(snapshot.drl_status.criteria_passed)}",
            f"Failing Criteria: {len(snapshot.drl_status.criteria_failed)}",
        ])
        if snapshot.drl_status.blocking_criteria:
            lines.append(f"Blockers: {', '.join(snapshot.drl_status.blocking_criteria)}")
    
    if snapshot.gates:
        lines.extend([
            "",
            "-" * 60,
            "GATE STATUS",
            "-" * 60,
        ])
        for gate in snapshot.gates:
            status = "✓" if gate.passed else "✗"
            lines.append(f"  [{status}] {gate.name}: {gate.value:,.0f} (threshold: {gate.threshold:,.0f})")
    
    if snapshot.parameters:
        lines.extend([
            "",
            "-" * 60,
            "FROZEN PARAMETERS",
            "-" * 60,
            f"Max Maintenance Budget: ${snapshot.parameters.max_maintenance_budget:,.0f}/year",
            f"Max Payback Years: {snapshot.parameters.max_payback_years:.1f}",
            f"Max Callouts/Week: {snapshot.parameters.max_callouts_per_week:.1f}",
        ])
        if snapshot.parameters.custom_parameters:
            lines.append("Custom Parameters:")
            for key, value in snapshot.parameters.custom_parameters.items():
                lines.append(f"  {key}: {value}")
    
    lines.extend([
        "",
        "-" * 60,
        "CHAIN VERIFICATION",
        "-" * 60,
        f"Content Hash: {snapshot.content_hash}",
        f"Previous Hash: {snapshot.previous_hash or 'None (genesis)'}",
        "",
        "=" * 60,
    ])
    
    return "\n".join(lines)


def print_snapshot_history(registry: Optional[SnapshotRegistry] = None) -> None:
    """Print summary of all snapshots in registry."""
    if registry is None:
        registry = get_or_create_snapshot_registry()
    
    print("=" * 70)
    print("DECISION SNAPSHOT HISTORY")
    print("=" * 70)
    print(f"Total Snapshots: {len(registry.snapshots)}")
    print(f"Chain Valid: {'✓' if registry.verify_chain() else '✗ TAMPERING DETECTED'}")
    print()
    
    if not registry.snapshots:
        print("No snapshots recorded.")
        print("=" * 70)
        return
    
    print(f"{'ID':<30} {'Type':<15} {'Outcome':<12} {'DRL':<5} {'Created':<20}")
    print("-" * 70)
    
    for snapshot in registry.snapshots:
        drl = f"DRL-{snapshot.drl_status.achieved_level}" if snapshot.drl_status else "-"
        created = snapshot.created_at.strftime("%Y-%m-%d %H:%M")
        print(f"{snapshot.short_id:<30} {snapshot.snapshot_type.value:<15} "
              f"{snapshot.outcome.value:<12} {drl:<5} {created:<20}")
    
    print("=" * 70)


# =============================================================================
# DRL Advancement Logic
# =============================================================================

@dataclass
class DRLAdvancementCheck:
    """Result of checking if DRL can advance."""
    current_drl: int
    target_drl: int
    can_advance: bool
    blocking_reasons: List[str]
    met_criteria: List[str]
    
    def to_summary(self) -> str:
        lines = [
            "=" * 60,
            f"DRL ADVANCEMENT CHECK: DRL-{self.current_drl} -> DRL-{self.target_drl}",
            "=" * 60,
            "",
            f"STATUS: {'CAN ADVANCE' if self.can_advance else 'BLOCKED'}",
            "",
            "Met Criteria:",
        ]
        for c in self.met_criteria:
            lines.append(f"  [x] {c}")
        
        if self.blocking_reasons:
            lines.append("")
            lines.append("Blocking Reasons:")
            for r in self.blocking_reasons:
                lines.append(f"  [ ] {r}")
        
        lines.extend(["", "=" * 60])
        return "\n".join(lines)


def can_advance_to_drl4() -> DRLAdvancementCheck:
    """
    Check if system can advance to DRL-4.
    
    DRL-4 Requirements (Component validation in lab):
        - dewatering_params_validated == VALIDATED
        - pyrolysis_yields_validated == VALIDATED
        - FMEA critical count == 0
        - All CI gates passing
    
    Returns:
        DRLAdvancementCheck with detailed pass/fail
    """
    from septage_model.simulation.deterministic import run_product_mode
    from septage_model.ci.gates import run_design_gates
    from septage_model.ci.design_readiness import evaluate_drl_from_results
    from septage_model.artifacts.fmea import load_fmea, analyze_fmea
    from septage_model.artifacts.validation_tasks import get_validation_registry, ValidationStatus
    
    blocking_reasons = []
    met_criteria = []
    
    val_registry = get_validation_registry()
    
    # Check dewatering
    dew = val_registry.get("dewatering_params_validated")
    if dew and dew.status == ValidationStatus.VALIDATED:
        met_criteria.append("dewatering_params_validated: VALIDATED")
    else:
        status = dew.status.value if dew else "unknown"
        blocking_reasons.append(f"dewatering_params_validated: {status} (requires VALIDATED)")
    
    # Check pyrolysis
    pyr = val_registry.get("pyrolysis_yields_validated")
    if pyr and pyr.status == ValidationStatus.VALIDATED:
        met_criteria.append("pyrolysis_yields_validated: VALIDATED")
    else:
        status = pyr.status.value if pyr else "unknown"
        blocking_reasons.append(f"pyrolysis_yields_validated: {status} (requires VALIDATED)")
    
    # Check FMEA
    fmea = load_fmea()
    analysis = analyze_fmea(fmea)
    if analysis.critical_count == 0:
        met_criteria.append(f"FMEA: 0 critical modes (avg RPN: {analysis.avg_rpn:.1f})")
    else:
        blocking_reasons.append(f"FMEA: {analysis.critical_count} critical modes (requires 0)")
    
    # Check CI gates
    result = run_product_mode()
    gate_report = run_design_gates(result)
    if gate_report.all_passed:
        met_criteria.append("CI gates: all passing")
    else:
        failing = [g.name for g in gate_report.gates if not g.passed]
        blocking_reasons.append(f"CI gates failing: {', '.join(failing)}")
    
    # Get current DRL
    drl_assessment = evaluate_drl_from_results()
    current_drl = drl_assessment.achieved_drl
    
    return DRLAdvancementCheck(
        current_drl=current_drl,
        target_drl=4,
        can_advance=len(blocking_reasons) == 0,
        blocking_reasons=blocking_reasons,
        met_criteria=met_criteria,
    )


def can_advance_to_drl6() -> DRLAdvancementCheck:
    """
    Check if system can advance to DRL-6.
    
    DRL-6 Requirements (System prototype demo):
        - All DRL-4 requirements
        - capex_vendor_validated == VALIDATED
        - maintenance_model_validated == VALIDATED
    
    Returns:
        DRLAdvancementCheck with detailed pass/fail
    """
    from septage_model.artifacts.validation_tasks import get_validation_registry, ValidationStatus
    
    drl4_check = can_advance_to_drl4()
    
    blocking_reasons = []
    met_criteria = list(drl4_check.met_criteria)
    
    if not drl4_check.can_advance:
        blocking_reasons.append("DRL-4 requirements not met")
    else:
        met_criteria.append("DRL-4: all requirements met")
    
    val_registry = get_validation_registry()
    
    # Check CAPEX validation
    capex = val_registry.get("capex_vendor_validated")
    if capex and capex.status == ValidationStatus.VALIDATED:
        met_criteria.append("capex_vendor_validated: VALIDATED")
    else:
        status = capex.status.value if capex else "unknown"
        blocking_reasons.append(f"capex_vendor_validated: {status} (requires VALIDATED)")
    
    # Check maintenance validation
    maint = val_registry.get("maintenance_model_validated")
    if maint and maint.status == ValidationStatus.VALIDATED:
        met_criteria.append("maintenance_model_validated: VALIDATED")
    else:
        status = maint.status.value if maint else "unknown"
        blocking_reasons.append(f"maintenance_model_validated: {status} (requires VALIDATED)")
    
    return DRLAdvancementCheck(
        current_drl=drl4_check.current_drl,
        target_drl=6,
        can_advance=len(blocking_reasons) == 0,
        blocking_reasons=blocking_reasons,
        met_criteria=met_criteria,
    )
