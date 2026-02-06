"""
Artifacts Module - Design documentation and versioning.

Provides:
    - FMEA (Failure Mode and Effects Analysis)
    - Artifact versioning and registry
    - Vendor validation task tracking
    - Facility design (equipment lists, operating modes, site concept gates)
    - Facility geometry (XYZ bounding box layout, validation gates)
    
These artifacts support the productization engineering phase
and provide audit trails for regulatory review.
"""

from .fmea import (
    # Data classes
    FailureMode,
    Subsystem,
    Severity,
    MitigationStatus,
    FMEAAnalysis,
    # Constants
    DEFAULT_FAILURE_MODES,
    # Functions
    load_fmea,
    analyze_fmea,
    generate_fmea_markdown,
    fmea_criticality_gate,
)

from .versioning import (
    # Data classes
    SemanticVersion,
    ArtifactVersion,
    ArtifactType,
    VersionRegistry,
    # Functions
    compute_content_hash,
    verify_content_hash,
    create_artifact_version,
    diff_artifacts,
    # Convenience functions
    version_gate_report,
    version_fmea,
    version_drl_assessment,
    version_parameters,
    # Registry management
    get_default_registry_path,
    get_or_create_registry,
    save_registry,
)

from .validation_tasks import (
    # Enums
    ValidationDataType,
    ValidationStatus,
    # Data classes
    AcceptanceCriterion,
    ValidationTask,
    ValidationRegistry,
    # Constants
    DEFAULT_VALIDATION_TASKS,
    # Functions
    get_validation_registry,
    get_drl4_blockers,
    print_validation_status,
)

from .vendor_packet import (
    VendorPacket,
    generate_vendor_packet,
    print_packet_summary,
)

from .vendor_registry import (
    # Enums
    VendorStatus,
    VendorCategory,
    # Data classes
    Vendor,
    VendorRegistry,
    # Functions
    slugify,
    get_vendor_registry,
    register_vendor,
    get_vendor,
    print_vendor_registry,
)

from .vendor_intake import (
    # Enums
    ParameterResult,
    EngineeringDecision,
    # Data classes
    ParameterValidation,
    VendorSubmission,
    ValidationReport,
    # Core validation (PURE)
    validate_vendor_submission,
    validate_parameter,
    parse_vendor_submission,
    # Persistence (append-only)
    persist_submission,
    persist_validation,
    load_all_submissions,
    load_all_validations,
    # Revalidation
    revalidate_all,
    generate_revalidation_diff,
    # Reports
    print_validation_report,
    generate_validation_markdown,
    compare_vendors,
    # Templates
    generate_vendor_request_email,
    generate_response_template,
)

from .decision_snapshot import (
    # Enums
    SnapshotType,
    DecisionOutcome,
    # Data classes
    FrozenGateStatus,
    FrozenDRLStatus,
    FrozenParameters,
    DecisionSnapshot,
    SnapshotRegistry,
    DRLAdvancementCheck,
    # Functions
    get_default_snapshot_path,
    get_or_create_snapshot_registry,
    save_snapshot_registry,
    create_drl_snapshot,
    create_parameter_lock_snapshot,
    freeze_current_state,
    generate_snapshot_report,
    print_snapshot_history,
    # DRL Advancement
    can_advance_to_drl4,
    can_advance_to_drl6,
)

# Facility Design — import with FD_ prefix for colliding enum names
from .facility_design import (
    # Enums (prefixed to avoid collision with fmea.Subsystem)
    DeploymentMode as FD_DeploymentMode,
    Subsystem as FD_Subsystem,
    OperatingPhase,
    NightMode,
    CentrateDisposition,
    # Data classes
    EquipmentItem,
    BestPractice,
    OperatingModeStep,
    OperatingModeSpec,
    SiteConceptGate,
    DesignGap,
    GateCheckResult,
    # Constants — equipment
    PRODUCT_MODE_EQUIPMENT,
    HUB_MODE_EQUIPMENT,
    # Constants — best practices
    BEST_PRACTICES,
    # Constants — operating modes
    PRODUCT_NORMAL_DAY,
    PRODUCT_STARTUP,
    PRODUCT_SHUTDOWN,
    PRODUCT_FAILURE_HANDLING,
    HUB_NORMAL_DAY,
    HUB_END_OF_DAY,
    HUB_OVERNIGHT,
    HUB_MORNING_RESTART,
    HUB_FAILURE_HANDLING,
    # Constants — gates & gaps
    SITE_CONCEPT_GATES,
    KNOWN_DESIGN_GAPS,
    # Functions
    get_equipment_list,
    get_operating_modes,
    get_applicable_gates,
    get_best_practices_by_subsystem,
    check_design_gaps,
    check_gate04_unattended_safety,
    check_site_concept_gates_programmatic,
    generate_equipment_summary,
    generate_operating_mode_summary,
)

# Facility Geometry — import with FG_ prefix for colliding enum names
from .facility_geometry import (
    # Enums (prefixed to avoid collision)
    DeploymentMode as FG_DeploymentMode,
    Subsystem as FG_Subsystem,
    ContainmentType,
    PullOutDirection,
    # Core geometry
    BoundingBox,
    FacilityEnvelope,
    ReactorEnvelopeParams,
    TankGeometry,
    EquipmentPlacement,
    Zone,
    ContainmentArea,
    LayoutGateResult,
    # Vendor cut-sheet pipeline
    VendorCutSheetData,
    CutSheetReconciliation,
    derive_envelope_from_vendor_cut_sheet,
    # Overnight ↔ geometry bridge
    OVERNIGHT_HOT_ZONE_MULTIPLIERS,
    get_overnight_hot_zone_exclusion,
    validate_overnight_geometry,
    # Constants — reactor envelopes
    PRODUCT_REACTOR_ENVELOPE,
    HUB_REACTOR_ENVELOPE,
    # Constants — tanks
    PRODUCT_TANKS,
    HUB_TANKS,
    # Constants — facility envelopes
    PRODUCT_ENVELOPE,
    HUB_ENVELOPE,
    # Constants — zones
    PRODUCT_ZONES,
    HUB_ZONES,
    # Constants — equipment layouts
    PRODUCT_EQUIPMENT,
    HUB_EQUIPMENT,
    # Validation gates
    validate_facility_bounds,
    validate_clearance_overlap,
    validate_hot_zone_exclusion,
    validate_containment_separation,
    run_layout_gates,
)

__all__ = [
    # FMEA
    "FailureMode",
    "Subsystem",
    "Severity",
    "MitigationStatus",
    "FMEAAnalysis",
    "DEFAULT_FAILURE_MODES",
    "load_fmea",
    "analyze_fmea",
    "generate_fmea_markdown",
    "fmea_criticality_gate",
    # Versioning
    "SemanticVersion",
    "ArtifactVersion",
    "ArtifactType",
    "VersionRegistry",
    "compute_content_hash",
    "verify_content_hash",
    "create_artifact_version",
    "diff_artifacts",
    "version_gate_report",
    "version_fmea",
    "version_drl_assessment",
    "version_parameters",
    "get_default_registry_path",
    "get_or_create_registry",
    "save_registry",
    # Validation Tasks
    "ValidationDataType",
    "ValidationStatus",
    "AcceptanceCriterion",
    "ValidationTask",
    "ValidationRegistry",
    "DEFAULT_VALIDATION_TASKS",
    "get_validation_registry",
    "get_drl4_blockers",
    "print_validation_status",
    # Vendor Packet
    "VendorPacket",
    "generate_vendor_packet",
    "print_packet_summary",
    # Vendor Registry
    "VendorStatus",
    "VendorCategory",
    "Vendor",
    "VendorRegistry",
    "slugify",
    "get_vendor_registry",
    "register_vendor",
    "get_vendor",
    "print_vendor_registry",
    # Vendor Intake
    "ParameterResult",
    "EngineeringDecision",
    "ParameterValidation",
    "VendorSubmission",
    "ValidationReport",
    "validate_vendor_submission",
    "validate_parameter",
    "parse_vendor_submission",
    "persist_submission",
    "persist_validation",
    "load_all_submissions",
    "load_all_validations",
    "revalidate_all",
    "generate_revalidation_diff",
    "print_validation_report",
    "generate_validation_markdown",
    "compare_vendors",
    "generate_vendor_request_email",
    "generate_response_template",
    # Decision Snapshots
    "SnapshotType",
    "DecisionOutcome",
    "FrozenGateStatus",
    "FrozenDRLStatus",
    "FrozenParameters",
    "DecisionSnapshot",
    "SnapshotRegistry",
    "DRLAdvancementCheck",
    "get_default_snapshot_path",
    "get_or_create_snapshot_registry",
    "save_snapshot_registry",
    "create_drl_snapshot",
    "create_parameter_lock_snapshot",
    "freeze_current_state",
    "generate_snapshot_report",
    "print_snapshot_history",
    "can_advance_to_drl4",
    "can_advance_to_drl6",
    # Facility Design
    "FD_DeploymentMode",
    "FD_Subsystem",
    "OperatingPhase",
    "NightMode",
    "CentrateDisposition",
    "EquipmentItem",
    "BestPractice",
    "OperatingModeStep",
    "OperatingModeSpec",
    "SiteConceptGate",
    "DesignGap",
    "GateCheckResult",
    "PRODUCT_MODE_EQUIPMENT",
    "HUB_MODE_EQUIPMENT",
    "BEST_PRACTICES",
    "PRODUCT_NORMAL_DAY",
    "PRODUCT_STARTUP",
    "PRODUCT_SHUTDOWN",
    "PRODUCT_FAILURE_HANDLING",
    "HUB_NORMAL_DAY",
    "HUB_END_OF_DAY",
    "HUB_OVERNIGHT",
    "HUB_MORNING_RESTART",
    "HUB_FAILURE_HANDLING",
    "SITE_CONCEPT_GATES",
    "KNOWN_DESIGN_GAPS",
    "get_equipment_list",
    "get_operating_modes",
    "get_applicable_gates",
    "get_best_practices_by_subsystem",
    "check_design_gaps",
    "check_gate04_unattended_safety",
    "check_site_concept_gates_programmatic",
    "generate_equipment_summary",
    "generate_operating_mode_summary",
    # Facility Geometry
    "FG_DeploymentMode",
    "FG_Subsystem",
    "ContainmentType",
    "PullOutDirection",
    "BoundingBox",
    "FacilityEnvelope",
    "ReactorEnvelopeParams",
    "TankGeometry",
    "EquipmentPlacement",
    "Zone",
    "ContainmentArea",
    "LayoutGateResult",
    "VendorCutSheetData",
    "CutSheetReconciliation",
    "derive_envelope_from_vendor_cut_sheet",
    "OVERNIGHT_HOT_ZONE_MULTIPLIERS",
    "get_overnight_hot_zone_exclusion",
    "validate_overnight_geometry",
    "PRODUCT_REACTOR_ENVELOPE",
    "HUB_REACTOR_ENVELOPE",
    "PRODUCT_TANKS",
    "HUB_TANKS",
    "PRODUCT_ENVELOPE",
    "HUB_ENVELOPE",
    "PRODUCT_ZONES",
    "HUB_ZONES",
    "PRODUCT_EQUIPMENT",
    "HUB_EQUIPMENT",
    "validate_facility_bounds",
    "validate_clearance_overlap",
    "validate_hot_zone_exclusion",
    "validate_containment_separation",
    "run_layout_gates",
]
