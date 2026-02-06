"""
Vendor Validation Tasks - Tracked validation requirements for DRL advancement.

These tasks represent the explicit, auditable requirements that must be satisfied
by vendor data before the system can advance beyond DRL-3.

Each task specifies:
    - Required data type (bench test, lab test, vendor spec)
    - Acceptance criteria
    - Expected ranges
    - Validation status

DO NOT mark these as validated without actual vendor/lab data.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum
from pathlib import Path
import json


class ValidationDataType(Enum):
    """Type of data required for validation."""
    BENCH_TEST = "bench_test"       # Small-scale bench testing
    LAB_TEST = "lab_test"           # Laboratory analysis
    VENDOR_SPEC = "vendor_spec"     # Vendor-provided specifications
    PILOT_DATA = "pilot_data"       # Data from pilot system operation
    FIELD_DATA = "field_data"       # Data from production system


class ValidationStatus(Enum):
    """Status of validation task."""
    NOT_STARTED = "not_started"
    DATA_REQUESTED = "data_requested"
    DATA_RECEIVED = "data_received"
    UNDER_REVIEW = "under_review"
    VALIDATED = "validated"
    FAILED = "failed"


@dataclass
class AcceptanceCriterion:
    """A single acceptance criterion for validation."""
    parameter: str
    description: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    expected_value: Optional[float] = None
    tolerance_pct: Optional[float] = None
    unit: str = ""
    criteria_version: str = "v1.0"  # Version for revalidation support
    
    def check(self, actual_value: float) -> bool:
        """Check if actual value meets criterion."""
        if self.min_value is not None and actual_value < self.min_value:
            return False
        if self.max_value is not None and actual_value > self.max_value:
            return False
        if self.expected_value is not None and self.tolerance_pct is not None:
            tolerance = self.expected_value * (self.tolerance_pct / 100)
            if abs(actual_value - self.expected_value) > tolerance:
                return False
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameter": self.parameter,
            "description": self.description,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "expected_value": self.expected_value,
            "tolerance_pct": self.tolerance_pct,
            "unit": self.unit,
            "criteria_version": self.criteria_version,
        }


@dataclass
class ValidationTask:
    """
    A tracked validation requirement for DRL advancement.
    
    Attributes:
        task_id: Unique identifier matching DRL criterion name
        name: Human-readable name
        description: What needs to be validated
        required_for_drl: DRL level this blocks
        data_type: Type of data required
        acceptance_criteria: List of criteria that must be met
        status: Current validation status
        vendor: Vendor name (if applicable)
        data_received_date: When data was received
        validated_date: When validation was completed
        validated_by: Who performed validation
        notes: Additional notes
        evidence_path: Path to supporting documentation
    """
    task_id: str
    name: str
    description: str
    required_for_drl: int
    data_type: ValidationDataType
    acceptance_criteria: List[AcceptanceCriterion]
    status: ValidationStatus = ValidationStatus.NOT_STARTED
    vendor: str = ""
    data_received_date: Optional[datetime] = None
    validated_date: Optional[datetime] = None
    validated_by: str = ""
    notes: str = ""
    evidence_path: Optional[Path] = None
    
    @property
    def is_complete(self) -> bool:
        """True if validation is complete (passed or failed)."""
        return self.status in (ValidationStatus.VALIDATED, ValidationStatus.FAILED)
    
    @property
    def is_blocking(self) -> bool:
        """True if this task is blocking DRL advancement."""
        return not self.is_complete
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "required_for_drl": self.required_for_drl,
            "data_type": self.data_type.value,
            "acceptance_criteria": [c.to_dict() for c in self.acceptance_criteria],
            "status": self.status.value,
            "vendor": self.vendor,
            "data_received_date": self.data_received_date.isoformat() if self.data_received_date else None,
            "validated_date": self.validated_date.isoformat() if self.validated_date else None,
            "validated_by": self.validated_by,
            "notes": self.notes,
            "evidence_path": str(self.evidence_path) if self.evidence_path else None,
        }


# =============================================================================
# Default Validation Tasks - DRL-4 Blockers
# =============================================================================

DEFAULT_VALIDATION_TASKS: List[ValidationTask] = [
    # -------------------------------------------------------------------------
    # DRL-4: Component validation in lab
    # -------------------------------------------------------------------------
    ValidationTask(
        task_id="dewatering_params_validated",
        name="Dewatering Performance Validation",
        description=(
            "Validate dewatering unit performance against model assumptions. "
            "Requires bench-scale testing with representative septage samples."
        ),
        required_for_drl=4,
        data_type=ValidationDataType.BENCH_TEST,
        acceptance_criteria=[
            AcceptanceCriterion(
                parameter="cake_ts_fraction",
                description="Cake total solids fraction (dry basis)",
                min_value=0.18,
                max_value=0.25,
                expected_value=0.20,
                tolerance_pct=15,
                unit="fraction",
            ),
            AcceptanceCriterion(
                parameter="solids_capture",
                description="Solids capture efficiency",
                min_value=0.90,
                max_value=1.0,
                expected_value=0.95,
                tolerance_pct=5,
                unit="fraction",
            ),
            AcceptanceCriterion(
                parameter="polymer_kg_per_tds",
                description="Polymer consumption per tonne dry solids",
                min_value=3.0,
                max_value=8.0,
                expected_value=5.0,
                tolerance_pct=30,
                unit="kg/TDS",
            ),
            AcceptanceCriterion(
                parameter="power_kwh_per_m3",
                description="Power consumption per cubic meter processed",
                min_value=1.0,
                max_value=4.0,
                expected_value=2.0,
                tolerance_pct=50,
                unit="kWh/m³",
            ),
        ],
        status=ValidationStatus.NOT_STARTED,
        notes="Requires 3+ batch tests with septage from target service area.",
    ),
    
    ValidationTask(
        task_id="pyrolysis_yields_validated",
        name="Pyrolysis Yield Validation",
        description=(
            "Validate pyrolysis product yields against model assumptions. "
            "Requires lab-scale pyrolysis testing with dewatered cake samples."
        ),
        required_for_drl=4,
        data_type=ValidationDataType.LAB_TEST,
        acceptance_criteria=[
            AcceptanceCriterion(
                parameter="char_yield_septage",
                description="Char yield from septage (dry basis)",
                min_value=0.35,
                max_value=0.55,
                expected_value=0.467,
                tolerance_pct=15,
                unit="kg char/kg TDS",
            ),
            AcceptanceCriterion(
                parameter="char_yield_cofeed",
                description="Char yield from wood co-feed (dry basis)",
                min_value=0.25,
                max_value=0.45,
                expected_value=0.35,
                tolerance_pct=15,
                unit="kg char/kg TDS",
            ),
            AcceptanceCriterion(
                parameter="syngas_yield_septage",
                description="Syngas energy yield from septage",
                min_value=2.5,
                max_value=4.5,
                expected_value=3.2,
                tolerance_pct=20,
                unit="MJ/kg TDS",
            ),
            AcceptanceCriterion(
                parameter="syngas_yield_cofeed",
                description="Syngas energy yield from wood co-feed",
                min_value=4.0,
                max_value=6.5,
                expected_value=5.4,
                tolerance_pct=15,
                unit="MJ/kg TDS",
            ),
        ],
        status=ValidationStatus.NOT_STARTED,
        notes="Pyrolysis at 500-600°C, residence time 15-30 min. Test both septage-only and co-feed blends.",
    ),
    
    # -------------------------------------------------------------------------
    # DRL-6: Vendor validation
    # -------------------------------------------------------------------------
    ValidationTask(
        task_id="capex_vendor_validated",
        name="CAPEX Vendor Validation",
        description=(
            "Validate CAPEX estimates with actual vendor quotes. "
            "Requires budgetary quotes from equipment vendors."
        ),
        required_for_drl=6,
        data_type=ValidationDataType.VENDOR_SPEC,
        acceptance_criteria=[
            AcceptanceCriterion(
                parameter="total_capex",
                description="Total system CAPEX",
                min_value=800_000,
                max_value=1_600_000,
                expected_value=1_200_000,
                tolerance_pct=25,
                unit="$",
            ),
            AcceptanceCriterion(
                parameter="capex_multiplier_product",
                description="Product mode CAPEX multiplier vs full scale",
                min_value=0.50,
                max_value=0.75,
                expected_value=0.60,
                tolerance_pct=15,
                unit="fraction",
            ),
        ],
        status=ValidationStatus.NOT_STARTED,
        notes="Requires quotes for: dewatering, dryer, pyrolyzer, char handling, controls.",
    ),
    
    ValidationTask(
        task_id="maintenance_model_validated",
        name="Maintenance Model Validation",
        description=(
            "Validate maintenance cost and callout frequency assumptions. "
            "Requires vendor maintenance schedules and spare parts pricing."
        ),
        required_for_drl=6,
        data_type=ValidationDataType.VENDOR_SPEC,
        acceptance_criteria=[
            AcceptanceCriterion(
                parameter="annual_maintenance_cost",
                description="Total annual maintenance cost",
                min_value=15_000,
                max_value=35_000,
                expected_value=23_000,
                tolerance_pct=30,
                unit="$/year",
            ),
            AcceptanceCriterion(
                parameter="callouts_per_year",
                description="Expected contractor callouts per year",
                min_value=10,
                max_value=52,
                expected_value=26,
                tolerance_pct=50,
                unit="callouts/year",
            ),
            AcceptanceCriterion(
                parameter="owner_serviceable_pct",
                description="Percentage of tasks owner can perform",
                min_value=0.70,
                max_value=1.0,
                expected_value=0.85,
                tolerance_pct=10,
                unit="fraction",
            ),
        ],
        status=ValidationStatus.NOT_STARTED,
        notes="Cross-reference with FMEA failure modes and MTTR estimates.",
    ),
    
    # -------------------------------------------------------------------------
    # DRL-4: Design-Grade Physics - Kinetics Validation
    # -------------------------------------------------------------------------
    ValidationTask(
        task_id="kinetics_params_validated",
        name="Pyrolysis Kinetics Parameter Validation",
        description=(
            "Validate Arrhenius kinetic parameters (A, Ea, n) with lab TGA/DSC data. "
            "Required for design-grade conversion predictions. "
            "Literature defaults are acceptable for DRL-3 screening only."
        ),
        required_for_drl=4,
        data_type=ValidationDataType.LAB_TEST,
        acceptance_criteria=[
            AcceptanceCriterion(
                parameter="Ea_septage_kJ_mol",
                description="Activation energy for septage pyrolysis",
                min_value=150,
                max_value=350,
                expected_value=250,
                tolerance_pct=30,
                unit="kJ/mol",
            ),
            AcceptanceCriterion(
                parameter="A_septage_log10",
                description="Log10 of pre-exponential factor for septage",
                min_value=10,
                max_value=22,
                expected_value=18,
                tolerance_pct=20,
                unit="log10(1/s)",
            ),
            AcceptanceCriterion(
                parameter="reaction_order",
                description="Reaction order n",
                min_value=0.5,
                max_value=2.0,
                expected_value=1.0,
                tolerance_pct=50,
                unit="dimensionless",
            ),
            AcceptanceCriterion(
                parameter="fit_r_squared",
                description="R-squared of kinetic model fit",
                min_value=0.90,
                max_value=1.0,
                expected_value=0.95,
                tolerance_pct=5,
                unit="dimensionless",
            ),
        ],
        status=ValidationStatus.NOT_STARTED,
        notes=(
            "Requires TGA analysis at multiple heating rates (5, 10, 20 °C/min). "
            "Use Kissinger or model-fitting method. "
            "Separate parameter sets needed for septage and wood co-feed."
        ),
    ),
    
    # -------------------------------------------------------------------------
    # DRL-5: Tier-2 Kinetics (Parallel Reactions)
    # -------------------------------------------------------------------------
    ValidationTask(
        task_id="tier2_kinetics_validated",
        name="Tier-2 Parallel Reaction Kinetics Validation",
        description=(
            "Validate parallel-reaction kinetic model (char + volatile pathways). "
            "Required for promoting from Tier-1 global to Tier-2 parallel kinetics. "
            "Must provide separate k_char and k_volatile parameters."
        ),
        required_for_drl=5,
        data_type=ValidationDataType.LAB_TEST,
        acceptance_criteria=[
            AcceptanceCriterion(
                parameter="Ea_char_kJ_mol",
                description="Activation energy for char formation pathway",
                min_value=100,
                max_value=250,
                expected_value=180,
                tolerance_pct=25,
                unit="kJ/mol",
            ),
            AcceptanceCriterion(
                parameter="Ea_volatile_kJ_mol",
                description="Activation energy for volatile release pathway",
                min_value=150,
                max_value=350,
                expected_value=220,
                tolerance_pct=25,
                unit="kJ/mol",
            ),
            AcceptanceCriterion(
                parameter="parallel_fit_rmse",
                description="RMSE of parallel-reaction model fit",
                min_value=0.0,
                max_value=0.05,
                expected_value=0.02,
                tolerance_pct=100,
                unit="fraction",
            ),
        ],
        status=ValidationStatus.NOT_STARTED,
        notes=(
            "Tier-2 kinetics cannot be activated until this task is validated. "
            "Requires deconvolution of TGA curves into char/volatile pathways."
        ),
    ),
    
    # -------------------------------------------------------------------------
    # DRL-5: Reactor Heat Transfer Validation
    # -------------------------------------------------------------------------
    ValidationTask(
        task_id="reactor_ua_validated",
        name="Reactor Heat Transfer Coefficient Validation",
        description=(
            "Validate reactor heat transfer parameters (U, A, wall temp) from "
            "vendor specs or pilot measurements. Required for thermal feasibility gate."
        ),
        required_for_drl=5,
        data_type=ValidationDataType.VENDOR_SPEC,
        acceptance_criteria=[
            AcceptanceCriterion(
                parameter="U_w_m2k",
                description="Overall heat transfer coefficient",
                min_value=20,
                max_value=100,
                expected_value=50,
                tolerance_pct=40,
                unit="W/m²K",
            ),
            AcceptanceCriterion(
                parameter="heat_transfer_area_m2",
                description="Effective heat transfer area",
                min_value=2.0,
                max_value=10.0,
                expected_value=4.7,
                tolerance_pct=30,
                unit="m²",
            ),
            AcceptanceCriterion(
                parameter="max_wall_temp_k",
                description="Maximum wall temperature",
                min_value=773,
                max_value=1073,
                expected_value=923,
                tolerance_pct=10,
                unit="K",
            ),
        ],
        status=ValidationStatus.NOT_STARTED,
        notes=(
            "Request from pyrolyzer vendor. "
            "Cross-reference with thermal feasibility gate calculations."
        ),
    ),
]


# =============================================================================
# Validation Registry
# =============================================================================

@dataclass
class ValidationRegistry:
    """Registry of all validation tasks."""
    tasks: Dict[str, ValidationTask] = field(default_factory=dict)
    
    @classmethod
    def from_defaults(cls) -> 'ValidationRegistry':
        """Create registry with default tasks."""
        registry = cls()
        for task in DEFAULT_VALIDATION_TASKS:
            registry.tasks[task.task_id] = task
        return registry
    
    def get(self, task_id: str) -> Optional[ValidationTask]:
        """Get task by ID."""
        return self.tasks.get(task_id)
    
    def get_blocking_for_drl(self, drl_level: int) -> List[ValidationTask]:
        """Get all incomplete tasks blocking a specific DRL level."""
        return [
            t for t in self.tasks.values()
            if t.required_for_drl <= drl_level and t.is_blocking
        ]
    
    def get_by_status(self, status: ValidationStatus) -> List[ValidationTask]:
        """Get all tasks with a specific status."""
        return [t for t in self.tasks.values() if t.status == status]
    
    def update_status(
        self, 
        task_id: str, 
        status: ValidationStatus,
        notes: str = "",
        validated_by: str = ""
    ) -> bool:
        """Update task status. Returns True if successful."""
        task = self.tasks.get(task_id)
        if task is None:
            return False
        
        task.status = status
        if notes:
            task.notes = notes
        if validated_by:
            task.validated_by = validated_by
        if status == ValidationStatus.VALIDATED:
            task.validated_date = datetime.now()
        if status == ValidationStatus.DATA_RECEIVED:
            task.data_received_date = datetime.now()
        
        return True
    
    def apply_validation(
        self,
        report: 'ValidationReport',
        validated_by: str = "",
        evidence_path: Optional[Path] = None,
    ) -> bool:
        """
        Apply a validation report to update task status.
        
        This is an EXPLICIT state mutation - call only after reviewing report.
        
        Args:
            report: ValidationReport from validate_vendor_submission()
            validated_by: Who performed/approved the validation
            evidence_path: Path to supporting documentation
        
        Returns:
            True if successful, False if task not found
        
        Raises:
            ValueError: If report decision doesn't support status update
        """
        from septage_model.artifacts.vendor_intake import EngineeringDecision
        
        task = self.tasks.get(report.task.task_id)
        if task is None:
            return False
        
        # Determine new status based on decision
        decision = report.decision
        if decision == EngineeringDecision.ACCEPT_VENDOR:
            new_status = ValidationStatus.VALIDATED
        elif decision in (EngineeringDecision.REJECT_VENDOR, 
                          EngineeringDecision.REDESIGN_REQUIRED):
            new_status = ValidationStatus.FAILED
        elif decision == EngineeringDecision.PARTIAL_PASS:
            new_status = ValidationStatus.DATA_RECEIVED
        elif decision == EngineeringDecision.CRITERIA_REVISIT:
            new_status = ValidationStatus.UNDER_REVIEW
        else:
            new_status = ValidationStatus.UNDER_REVIEW
        
        # Update task
        task.status = new_status
        task.vendor = report.vendor.vendor_id
        task.validated_by = validated_by
        task.notes = f"Criteria version: {report.criteria_version}. {report.decision_rationale[:200]}"
        
        if new_status == ValidationStatus.VALIDATED:
            task.validated_date = datetime.now()
        if evidence_path:
            task.evidence_path = evidence_path
        
        task.data_received_date = report.submission.submitted_at
        
        return True
    
    def save(self, path: Path) -> None:
        """Save registry to JSON file."""
        data = {
            task_id: task.to_dict() 
            for task_id, task in self.tasks.items()
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, path: Path) -> 'ValidationRegistry':
        """Load registry from JSON file."""
        if not path.exists():
            return cls.from_defaults()
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # For now, return defaults - full deserialization would be added
        # when actual data is received
        return cls.from_defaults()
    
    def to_summary(self) -> str:
        """Generate summary of validation status."""
        lines = [
            "=" * 60,
            "VENDOR VALIDATION TASK STATUS",
            "=" * 60,
            "",
        ]
        
        for drl in sorted(set(t.required_for_drl for t in self.tasks.values())):
            lines.append(f"DRL-{drl} Requirements:")
            tasks = [t for t in self.tasks.values() if t.required_for_drl == drl]
            for task in tasks:
                status_icon = {
                    ValidationStatus.NOT_STARTED: "⬜",
                    ValidationStatus.DATA_REQUESTED: "📨",
                    ValidationStatus.DATA_RECEIVED: "📥",
                    ValidationStatus.UNDER_REVIEW: "🔍",
                    ValidationStatus.VALIDATED: "✅",
                    ValidationStatus.FAILED: "❌",
                }.get(task.status, "?")
                lines.append(f"  {status_icon} {task.name} [{task.status.value}]")
                lines.append(f"      Data required: {task.data_type.value}")
                lines.append(f"      Criteria: {len(task.acceptance_criteria)} parameters")
            lines.append("")
        
        # Summary stats
        total = len(self.tasks)
        validated = len([t for t in self.tasks.values() if t.status == ValidationStatus.VALIDATED])
        not_started = len([t for t in self.tasks.values() if t.status == ValidationStatus.NOT_STARTED])
        
        lines.extend([
            "-" * 60,
            f"Total Tasks: {total}",
            f"Validated: {validated}",
            f"Not Started: {not_started}",
            f"In Progress: {total - validated - not_started}",
            "=" * 60,
        ])
        
        return "\n".join(lines)


# =============================================================================
# Convenience Functions
# =============================================================================

def get_default_validation_registry_path() -> Path:
    """Get default path for validation registry."""
    return Path(__file__).parent.parent.parent / ".validation" / "registry.json"


def get_validation_registry() -> ValidationRegistry:
    """Get or create validation registry."""
    path = get_default_validation_registry_path()
    if path.exists():
        return ValidationRegistry.load(path)
    return ValidationRegistry.from_defaults()


def print_validation_status() -> None:
    """Print current validation status to console."""
    registry = get_validation_registry()
    print(registry.to_summary())


def get_drl4_blockers() -> List[ValidationTask]:
    """Get tasks blocking DRL-4."""
    registry = get_validation_registry()
    return registry.get_blocking_for_drl(4)
