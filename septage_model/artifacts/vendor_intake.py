"""
Vendor Data Intake and Validation System.

Provides a complete workflow from vendor response to DRL decision:
    1. Parse vendor submissions (JSON or table format)
    2. Validate against acceptance criteria (tiered: PASS/WARN/FAIL/CRITICAL)
    3. Generate PASS/FAIL reports
    4. Persist submissions and validations (append-only, immutable)
    5. Determine DRL impact
    6. Classify engineering implications
    7. Support revalidation when criteria change

Usage:
    1. Register vendor: register_vendor("dew_001", "Vendor X Corp", VendorCategory.DEWATERING)
    2. Vendor sends data in structured format
    3. User pastes raw data: validate_vendor_submission(raw_data, "dew_001")
    4. System validates objectively and returns decision
    5. User reviews report and calls registry.apply_validation(report) if appropriate

Key Principle: Validation is a pure function. State mutation is explicit and separate.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from enum import Enum
from pathlib import Path
import json
import re

from septage_model.artifacts.validation_tasks import (
    ValidationTask,
    ValidationStatus,
    AcceptanceCriterion,
    ValidationRegistry,
    get_validation_registry,
)
from septage_model.artifacts.vendor_registry import (
    Vendor,
    VendorRegistry,
    get_vendor_registry,
    get_vendor,
)


# =============================================================================
# Enums
# =============================================================================

class ParameterResult(Enum):
    """Result of parameter validation (tiered)."""
    PASS = "pass"           # Within acceptance range
    WARN = "warn"           # Outside range but within tolerance
    FAIL = "fail"           # Outside tolerance but <= 15% beyond
    CRITICAL = "critical"   # > 15% beyond tolerance
    MISSING = "missing"     # Parameter not provided


class EngineeringDecision(Enum):
    """Engineering implication of validation result."""
    ACCEPT_VENDOR = "accept_vendor"           # All criteria met
    REJECT_VENDOR = "reject_vendor"           # Cannot meet envelope
    REDESIGN_REQUIRED = "redesign_required"   # Architecture change needed
    CRITERIA_REVISIT = "criteria_revisit"     # Rare: criteria may need adjustment
    PARTIAL_PASS = "partial_pass"             # Some criteria met, review needed


# Physics-critical parameters - CRITICAL failures here always reject
PHYSICS_PARAMETERS = {
    'syngas_yield_septage',
    'syngas_yield_cofeed', 
    'char_yield_septage',
    'char_yield_cofeed',
    'energy_self_sufficiency',
    'self_sufficiency',
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ParameterValidation:
    """Validation result for a single parameter."""
    parameter: str
    description: str
    expected_value: float
    min_value: float
    max_value: float
    tolerance_pct: float
    unit: str
    criteria_version: str
    measured_value: Optional[float]
    result: ParameterResult
    deviation_pct: Optional[float] = None
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameter": self.parameter,
            "description": self.description,
            "expected": self.expected_value,
            "range": [self.min_value, self.max_value],
            "tolerance_pct": self.tolerance_pct,
            "unit": self.unit,
            "criteria_version": self.criteria_version,
            "measured": self.measured_value,
            "result": self.result.value,
            "deviation_pct": self.deviation_pct,
            "notes": self.notes,
        }


@dataclass
class VendorSubmission:
    """Parsed vendor data submission."""
    vendor_id: str
    packet_hash: str
    validation_task: str
    evidence_type: str
    results: Dict[str, float]
    raw_data: str
    submitted_at: datetime = field(default_factory=datetime.now)
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "vendor_id": self.vendor_id,
            "packet_hash": self.packet_hash,
            "validation_task": self.validation_task,
            "evidence_type": self.evidence_type,
            "results": self.results,
            "submitted_at": self.submitted_at.isoformat(),
            "notes": self.notes,
            # raw_data stored separately for audit
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], raw_data: str = "") -> 'VendorSubmission':
        return cls(
            vendor_id=data["vendor_id"],
            packet_hash=data["packet_hash"],
            validation_task=data["validation_task"],
            evidence_type=data.get("evidence_type", "unknown"),
            results=data["results"],
            raw_data=raw_data,
            submitted_at=datetime.fromisoformat(data["submitted_at"]) 
                if "submitted_at" in data else datetime.now(),
            notes=data.get("notes", ""),
        )


@dataclass
class ValidationReport:
    """Complete validation report for a vendor submission."""
    submission: VendorSubmission
    task: ValidationTask
    vendor: Vendor
    parameter_results: List[ParameterValidation]
    overall_result: ParameterResult
    decision: EngineeringDecision
    decision_rationale: str
    drl_impact: str
    criteria_version: str
    generated_at: datetime = field(default_factory=datetime.now)
    
    @property
    def passed_count(self) -> int:
        return sum(1 for p in self.parameter_results 
                   if p.result in (ParameterResult.PASS, ParameterResult.WARN))
    
    @property
    def failed_count(self) -> int:
        return sum(1 for p in self.parameter_results 
                   if p.result == ParameterResult.FAIL)
    
    @property
    def critical_count(self) -> int:
        return sum(1 for p in self.parameter_results 
                   if p.result == ParameterResult.CRITICAL)
    
    @property
    def missing_count(self) -> int:
        return sum(1 for p in self.parameter_results 
                   if p.result == ParameterResult.MISSING)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "submission": self.submission.to_dict(),
            "task_id": self.task.task_id,
            "task_name": self.task.name,
            "vendor_id": self.vendor.vendor_id,
            "vendor_name": self.vendor.legal_name,
            "parameter_results": [p.to_dict() for p in self.parameter_results],
            "summary": {
                "passed": self.passed_count,
                "failed": self.failed_count,
                "critical": self.critical_count,
                "missing": self.missing_count,
                "total": len(self.parameter_results),
            },
            "overall_result": self.overall_result.value,
            "decision": self.decision.value,
            "decision_rationale": self.decision_rationale,
            "drl_impact": self.drl_impact,
            "criteria_version": self.criteria_version,
            "generated_at": self.generated_at.isoformat(),
        }


# =============================================================================
# Parsing Functions
# =============================================================================

def parse_json_submission(raw_data: str, vendor_id: str) -> VendorSubmission:
    """
    Parse vendor submission in JSON format.
    
    Expected format:
    {
        "packet_hash": "1ee87b8d691d",
        "validation_task": "dewatering_params_validated",
        "evidence_type": "bench_test",
        "results": {
            "cake_ts_fraction": 0.22,
            "solids_capture": 0.93,
            ...
        }
    }
    """
    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format: {e}")
    
    required_fields = ["packet_hash", "validation_task", "results"]
    for fld in required_fields:
        if fld not in data:
            raise ValueError(f"Missing required field: {fld}")
    
    return VendorSubmission(
        vendor_id=vendor_id,
        packet_hash=data["packet_hash"],
        validation_task=data["validation_task"],
        evidence_type=data.get("evidence_type", "unknown"),
        results=data["results"],
        raw_data=raw_data,
        notes=data.get("notes", ""),
    )


def parse_table_submission(raw_data: str, vendor_id: str) -> VendorSubmission:
    """
    Parse vendor submission in table format.
    
    Expected format:
    Validation Task: dewatering_params_validated
    Packet Hash: 1ee87b8d691d
    Evidence Type: Bench Test
    
    Parameter               Measured Value   Units
    cake_ts_fraction        0.22             -
    solids_capture          0.93             -
    ...
    """
    lines = [line.strip() for line in raw_data.strip().split('\n') if line.strip()]
    
    # Parse header fields
    packet_hash = None
    validation_task = None
    evidence_type = "unknown"
    
    data_start = 0
    for i, line in enumerate(lines):
        lower = line.lower()
        if 'validation task:' in lower or 'validation_task:' in lower:
            validation_task = line.split(':', 1)[1].strip()
        elif 'packet hash:' in lower or 'packet_hash:' in lower:
            packet_hash = line.split(':', 1)[1].strip()
        elif 'evidence type:' in lower or 'evidence_type:' in lower:
            evidence_type = line.split(':', 1)[1].strip()
        elif 'parameter' in lower and ('measured' in lower or 'value' in lower):
            data_start = i + 1
            break
    
    if not packet_hash:
        raise ValueError("Missing packet hash in submission")
    if not validation_task:
        raise ValueError("Missing validation task in submission")
    
    # Parse data rows
    results = {}
    for line in lines[data_start:]:
        # Skip separator lines
        if line.startswith('-') or line.startswith('='):
            continue
        
        # Split on whitespace, handling various formats
        parts = line.split()
        if len(parts) >= 2:
            param_name = parts[0]
            try:
                value = float(parts[1])
                results[param_name] = value
            except ValueError:
                continue  # Skip non-numeric rows
    
    if not results:
        raise ValueError("No valid parameter data found in submission")
    
    return VendorSubmission(
        vendor_id=vendor_id,
        packet_hash=packet_hash,
        validation_task=validation_task,
        evidence_type=evidence_type,
        results=results,
        raw_data=raw_data,
    )


def parse_vendor_submission(raw_data: str, vendor_id: str) -> VendorSubmission:
    """
    Auto-detect format and parse vendor submission.
    
    Args:
        raw_data: Raw vendor response (JSON or table format)
        vendor_id: Vendor ID from registry (MUST exist)
    
    Returns:
        Parsed VendorSubmission
    
    Raises:
        KeyError: If vendor_id not in registry
        ValueError: If parsing fails
    """
    # Verify vendor exists in registry
    vendor = get_vendor(vendor_id)  # Raises KeyError if not found
    
    raw_data = raw_data.strip()
    
    # Try JSON first
    if raw_data.startswith('{'):
        return parse_json_submission(raw_data, vendor_id)
    
    # Otherwise try table format
    return parse_table_submission(raw_data, vendor_id)


# =============================================================================
# Validation Functions
# =============================================================================

def validate_parameter(
    criterion: AcceptanceCriterion,
    measured_value: Optional[float]
) -> ParameterValidation:
    """
    Validate a single parameter against its acceptance criterion.
    
    Tiered validation logic:
        - Within [min_value, max_value] -> PASS
        - Outside range but deviation <= tolerance_pct -> WARN
        - Deviation > tolerance but <= tolerance * 1.15 -> FAIL
        - Deviation > tolerance * 1.15 -> CRITICAL
        - Not provided -> MISSING
    
    Args:
        criterion: The acceptance criterion to validate against
        measured_value: The vendor-provided measured value (None if missing)
    
    Returns:
        ParameterValidation with result and details
    """
    if measured_value is None:
        return ParameterValidation(
            parameter=criterion.parameter,
            description=criterion.description,
            expected_value=criterion.expected_value or 0,
            min_value=criterion.min_value or 0,
            max_value=criterion.max_value or 0,
            tolerance_pct=criterion.tolerance_pct or 0,
            unit=criterion.unit,
            criteria_version=criterion.criteria_version,
            measured_value=None,
            result=ParameterResult.MISSING,
            notes="Parameter not provided in submission",
        )
    
    expected = criterion.expected_value or 0
    min_val = criterion.min_value
    max_val = criterion.max_value
    tolerance = criterion.tolerance_pct or 0
    
    # Calculate deviation from expected
    if expected != 0:
        deviation_pct = abs((measured_value - expected) / expected) * 100
    else:
        deviation_pct = 0 if measured_value == 0 else 100
    
    # Check if within acceptance range
    in_range = True
    if min_val is not None and measured_value < min_val:
        in_range = False
    if max_val is not None and measured_value > max_val:
        in_range = False
    
    # Determine result using tiered logic
    if in_range:
        result = ParameterResult.PASS
        notes = "Within acceptable range"
    elif deviation_pct <= tolerance:
        result = ParameterResult.WARN
        notes = f"Outside range but within tolerance ({deviation_pct:.1f}% deviation)"
    elif deviation_pct <= tolerance * 1.15:
        result = ParameterResult.FAIL
        notes = f"Exceeds tolerance ({deviation_pct:.1f}% deviation, tolerance: {tolerance}%)"
    else:
        result = ParameterResult.CRITICAL
        notes = f"CRITICAL: {deviation_pct:.1f}% deviation, >{tolerance * 1.15:.1f}% threshold"
    
    # Add direction info for failures
    if result in (ParameterResult.FAIL, ParameterResult.CRITICAL):
        if min_val is not None and measured_value < min_val:
            notes += f" - Below minimum ({min_val} {criterion.unit})"
        elif max_val is not None and measured_value > max_val:
            notes += f" - Above maximum ({max_val} {criterion.unit})"
    
    return ParameterValidation(
        parameter=criterion.parameter,
        description=criterion.description,
        expected_value=expected,
        min_value=min_val or 0,
        max_value=max_val or 0,
        tolerance_pct=tolerance,
        unit=criterion.unit,
        criteria_version=criterion.criteria_version,
        measured_value=measured_value,
        result=result,
        deviation_pct=round(deviation_pct, 1),
        notes=notes,
    )


def determine_decision(
    parameter_results: List[ParameterValidation],
    task: ValidationTask
) -> Tuple[EngineeringDecision, str]:
    """
    Determine engineering decision based on validation results.
    
    Returns:
        Tuple of (decision, rationale)
    """
    passed = [p for p in parameter_results 
              if p.result in (ParameterResult.PASS, ParameterResult.WARN)]
    failed = [p for p in parameter_results if p.result == ParameterResult.FAIL]
    critical = [p for p in parameter_results if p.result == ParameterResult.CRITICAL]
    missing = [p for p in parameter_results if p.result == ParameterResult.MISSING]
    
    total = len(parameter_results)
    
    # Any missing -> incomplete
    if missing:
        missing_names = [p.parameter for p in missing]
        return (
            EngineeringDecision.PARTIAL_PASS,
            f"Incomplete submission. Missing parameters: {', '.join(missing_names)}. "
            f"Request additional data from vendor."
        )
    
    # All passed (including WARN)
    if len(passed) == total:
        warn_count = sum(1 for p in passed if p.result == ParameterResult.WARN)
        if warn_count > 0:
            return (
                EngineeringDecision.ACCEPT_VENDOR,
                f"All parameters acceptable. {warn_count} parameter(s) with warnings - "
                f"review before final selection."
            )
        return (
            EngineeringDecision.ACCEPT_VENDOR,
            "All parameters within acceptable ranges. Vendor equipment meets requirements."
        )
    
    # Check for CRITICAL failures on physics parameters
    physics_critical = [p for p in critical if p.parameter in PHYSICS_PARAMETERS]
    if physics_critical:
        params = [f"{p.parameter} ({p.deviation_pct:.0f}% deviation)" for p in physics_critical]
        return (
            EngineeringDecision.REJECT_VENDOR,
            f"CRITICAL physics parameters outside envelope: {', '.join(params)}. "
            f"Vendor equipment cannot meet system requirements. "
            f"Do NOT adjust acceptance criteria to accommodate."
        )
    
    # Non-physics CRITICAL
    if critical:
        params = [f"{p.parameter} ({p.deviation_pct:.0f}% deviation)" for p in critical]
        return (
            EngineeringDecision.REDESIGN_REQUIRED,
            f"CRITICAL parameters outside envelope: {', '.join(params)}. "
            f"Evaluate whether system redesign can accommodate, or reject vendor."
        )
    
    # Only FAIL (no CRITICAL)
    if failed:
        if len(failed) == 1:
            p = failed[0]
            # Single marginal failure on non-physics param
            if p.parameter not in PHYSICS_PARAMETERS:
                return (
                    EngineeringDecision.CRITERIA_REVISIT,
                    f"Single marginal failure: {p.parameter} ({p.deviation_pct:.0f}% deviation). "
                    f"Review if acceptance criterion is overly conservative. "
                    f"If criterion is physics-derived, reject vendor instead."
                )
        
        # Multiple failures
        params = [f"{p.parameter} ({p.deviation_pct:.0f}% deviation)" for p in failed]
        return (
            EngineeringDecision.REJECT_VENDOR,
            f"Multiple failures: {', '.join(params)}. "
            f"Combined impact likely violates economic envelope. Reject vendor."
        )
    
    # Shouldn't reach here
    return (EngineeringDecision.PARTIAL_PASS, "Review required.")


def determine_drl_impact(
    decision: EngineeringDecision,
    task: ValidationTask
) -> str:
    """
    Determine DRL impact based on decision.
    
    Returns:
        Human-readable DRL impact statement
    """
    if decision == EngineeringDecision.ACCEPT_VENDOR:
        return (
            f"Task '{task.task_id}' can be marked VALIDATED. "
            f"If all DRL-{task.required_for_drl} tasks are validated, DRL advances."
        )
    
    elif decision == EngineeringDecision.REJECT_VENDOR:
        return (
            f"Task '{task.task_id}' remains NOT VALIDATED. "
            f"DRL-{task.required_for_drl} blocked. Seek alternative vendor."
        )
    
    elif decision == EngineeringDecision.REDESIGN_REQUIRED:
        return (
            f"Task '{task.task_id}' remains NOT VALIDATED. "
            f"DRL-{task.required_for_drl} blocked pending system redesign evaluation. "
            f"Redesign may invalidate other validated tasks."
        )
    
    elif decision == EngineeringDecision.CRITERIA_REVISIT:
        return (
            f"Task '{task.task_id}' under review. "
            f"DRL-{task.required_for_drl} blocked pending criteria review. "
            f"Document rationale if criteria are adjusted."
        )
    
    else:  # PARTIAL_PASS
        return (
            f"Task '{task.task_id}' incomplete. "
            f"DRL-{task.required_for_drl} blocked pending complete data."
        )


def get_criteria_version(task: ValidationTask) -> str:
    """Get the criteria version for a task (uses first criterion's version)."""
    if task.acceptance_criteria:
        return task.acceptance_criteria[0].criteria_version
    return "v1.0"


# =============================================================================
# Main Validation Function (PURE - no side effects)
# =============================================================================

def validate_vendor_submission(
    raw_data: str,
    vendor_id: str,
    expected_packet_hash: Optional[str] = None,
) -> ValidationReport:
    """
    Process and validate a vendor submission.
    
    This is the main entry point. Paste vendor data here.
    
    THIS IS A PURE FUNCTION - it does not:
        - Mutate the validation registry
        - Persist anything to disk
        - Change DRL status
    
    After reviewing the report, call:
        - persist_submission(submission) to save the submission
        - persist_validation(report) to save the validation report
        - registry.apply_validation(report) to update task status
    
    Args:
        raw_data: Raw vendor response (JSON or table format)
        vendor_id: Vendor ID from registry (MUST exist)
        expected_packet_hash: Optional - verify submission matches expected packet
    
    Returns:
        ValidationReport with complete results and decision
    
    Raises:
        KeyError: If vendor_id not in registry
        ValueError: If parsing fails or task not found
    """
    # Parse submission (also validates vendor exists)
    submission = parse_vendor_submission(raw_data, vendor_id)
    
    # Get vendor
    vendor = get_vendor(vendor_id)
    
    # Verify packet hash if specified
    if expected_packet_hash and submission.packet_hash != expected_packet_hash:
        raise ValueError(
            f"Packet hash mismatch. Expected: {expected_packet_hash}, "
            f"Got: {submission.packet_hash}. Vendor may be using outdated packet."
        )
    
    # Get validation task
    registry = get_validation_registry()
    task = registry.get(submission.validation_task)
    
    if task is None:
        raise ValueError(
            f"Unknown validation task: {submission.validation_task}. "
            f"Valid tasks: {list(registry.tasks.keys())}"
        )
    
    # Validate each parameter
    parameter_results = []
    for criterion in task.acceptance_criteria:
        measured = submission.results.get(criterion.parameter)
        result = validate_parameter(criterion, measured)
        parameter_results.append(result)
    
    # Determine overall result
    results = [p.result for p in parameter_results]
    if ParameterResult.CRITICAL in results:
        overall_result = ParameterResult.CRITICAL
    elif ParameterResult.FAIL in results:
        overall_result = ParameterResult.FAIL
    elif ParameterResult.MISSING in results:
        overall_result = ParameterResult.MISSING
    elif ParameterResult.WARN in results:
        overall_result = ParameterResult.WARN
    else:
        overall_result = ParameterResult.PASS
    
    # Determine decision and rationale
    decision, rationale = determine_decision(parameter_results, task)
    
    # Determine DRL impact
    drl_impact = determine_drl_impact(decision, task)
    
    # Get criteria version
    criteria_version = get_criteria_version(task)
    
    return ValidationReport(
        submission=submission,
        task=task,
        vendor=vendor,
        parameter_results=parameter_results,
        overall_result=overall_result,
        decision=decision,
        decision_rationale=rationale,
        drl_impact=drl_impact,
        criteria_version=criteria_version,
    )


# =============================================================================
# Persistence Layer (Append-Only, Immutable)
# =============================================================================

def get_submissions_dir() -> Path:
    """Get submissions directory."""
    return Path(__file__).parent.parent.parent / "docs" / "vendor" / "submissions"


def get_validations_dir() -> Path:
    """Get validations directory."""
    return Path(__file__).parent.parent.parent / "docs" / "vendor" / "validations"


def persist_submission(submission: VendorSubmission) -> Path:
    """
    Persist a vendor submission to disk.
    
    Append-only: never overwrites existing files.
    
    Returns:
        Path to saved file
    """
    submissions_dir = get_submissions_dir()
    submissions_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = submission.submitted_at.strftime("%Y%m%dT%H%M%S")
    filename = f"submission_{submission.vendor_id}_{timestamp}.json"
    filepath = submissions_dir / filename
    
    # Never overwrite
    counter = 1
    while filepath.exists():
        filename = f"submission_{submission.vendor_id}_{timestamp}_{counter}.json"
        filepath = submissions_dir / filename
        counter += 1
    
    data = submission.to_dict()
    data["_raw_data"] = submission.raw_data  # Store raw data for audit
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    return filepath


def persist_validation(report: ValidationReport) -> Path:
    """
    Persist a validation report to disk.
    
    Append-only: never overwrites existing files.
    
    Returns:
        Path to saved file
    """
    validations_dir = get_validations_dir()
    validations_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = report.generated_at.strftime("%Y%m%dT%H%M%S")
    filename = f"validation_{report.task.task_id}_{report.vendor.vendor_id}_{timestamp}.json"
    filepath = validations_dir / filename
    
    # Never overwrite
    counter = 1
    while filepath.exists():
        filename = f"validation_{report.task.task_id}_{report.vendor.vendor_id}_{timestamp}_{counter}.json"
        filepath = validations_dir / filename
        counter += 1
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(report.to_dict(), f, indent=2)
    
    return filepath


def load_all_submissions() -> List[VendorSubmission]:
    """Load all persisted submissions."""
    submissions_dir = get_submissions_dir()
    if not submissions_dir.exists():
        return []
    
    submissions = []
    for filepath in sorted(submissions_dir.glob("submission_*.json")):
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        raw_data = data.pop("_raw_data", "")
        submissions.append(VendorSubmission.from_dict(data, raw_data))
    
    return submissions


def load_all_validations() -> List[Dict[str, Any]]:
    """Load all persisted validation reports (as dicts)."""
    validations_dir = get_validations_dir()
    if not validations_dir.exists():
        return []
    
    validations = []
    for filepath in sorted(validations_dir.glob("validation_*.json")):
        with open(filepath, 'r', encoding='utf-8') as f:
            validations.append(json.load(f))
    
    return validations


# =============================================================================
# Revalidation Support
# =============================================================================

def revalidate_all(
    criteria_version: Optional[str] = None
) -> List[Tuple[Dict[str, Any], ValidationReport]]:
    """
    Revalidate all persisted submissions against current criteria.
    
    This is for when acceptance criteria change and you need to
    re-evaluate existing vendor data.
    
    Does NOT mutate DRL or task status.
    
    Args:
        criteria_version: Optional version label for new criteria
    
    Returns:
        List of (old_validation_dict, new_report) tuples for comparison
    """
    submissions = load_all_submissions()
    old_validations = {
        (v["submission"]["vendor_id"], v["task_id"]): v 
        for v in load_all_validations()
    }
    
    results = []
    for submission in submissions:
        try:
            new_report = validate_vendor_submission(
                raw_data=submission.raw_data,
                vendor_id=submission.vendor_id,
            )
            
            # Find old validation for comparison
            key = (submission.vendor_id, submission.validation_task)
            old_validation = old_validations.get(key, {})
            
            results.append((old_validation, new_report))
        except Exception as e:
            print(f"Error revalidating {submission.vendor_id}/{submission.validation_task}: {e}")
    
    return results


def generate_revalidation_diff(
    results: List[Tuple[Dict[str, Any], ValidationReport]]
) -> str:
    """Generate diff summary for revalidation results."""
    lines = [
        "=" * 70,
        "REVALIDATION SUMMARY",
        "=" * 70,
        "",
    ]
    
    changes = []
    for old, new in results:
        old_result = old.get("overall_result", "unknown")
        new_result = new.overall_result.value
        old_version = old.get("criteria_version", "unknown")
        new_version = new.criteria_version
        
        if old_result != new_result:
            changes.append({
                "vendor": new.vendor.legal_name,
                "task": new.task.name,
                "old_result": old_result,
                "new_result": new_result,
                "old_version": old_version,
                "new_version": new_version,
            })
    
    if not changes:
        lines.append("No status changes detected.")
    else:
        lines.append(f"{len(changes)} status change(s) detected:")
        lines.append("")
        for c in changes:
            lines.append(f"  Vendor: {c['vendor']}")
            lines.append(f"  Task: {c['task']}")
            lines.append(f"  Previous: {c['old_result'].upper()} ({c['old_version']})")
            lines.append(f"  Current: {c['new_result'].upper()} ({c['new_version']})")
            lines.append("")
    
    lines.append("=" * 70)
    return "\n".join(lines)


# =============================================================================
# Report Generation
# =============================================================================

def print_validation_report(report: ValidationReport) -> None:
    """Print validation report to console."""
    print("=" * 70)
    print("VENDOR SUBMISSION VALIDATION REPORT")
    print("=" * 70)
    print()
    print(f"Vendor: {report.vendor.legal_name} ({report.vendor.vendor_id})")
    print(f"Task: {report.task.name}")
    print(f"Packet Hash: {report.submission.packet_hash}")
    print(f"Evidence Type: {report.submission.evidence_type}")
    print(f"Criteria Version: {report.criteria_version}")
    print(f"Submitted: {report.submission.submitted_at.strftime('%Y-%m-%d %H:%M')}")
    print()
    print("-" * 70)
    print("PARAMETER VALIDATION")
    print("-" * 70)
    print()
    print(f"{'Parameter':<25} {'Expected':>10} {'Measured':>10} {'Result':>10}")
    print("-" * 70)
    
    result_icons = {
        ParameterResult.PASS: "PASS",
        ParameterResult.WARN: "WARN",
        ParameterResult.FAIL: "FAIL",
        ParameterResult.CRITICAL: "CRIT",
        ParameterResult.MISSING: "MISS",
    }
    
    for p in report.parameter_results:
        measured_str = f"{p.measured_value:.3f}" if p.measured_value is not None else "---"
        result_str = result_icons[p.result]
        print(f"{p.parameter:<25} {p.expected_value:>10.3f} {measured_str:>10} {result_str:>10}")
        if p.result not in (ParameterResult.PASS,):
            print(f"  -> {p.notes}")
    
    print()
    print("-" * 70)
    print("SUMMARY")
    print("-" * 70)
    print()
    print(f"Passed/Warn: {report.passed_count}/{len(report.parameter_results)}")
    print(f"Failed: {report.failed_count}/{len(report.parameter_results)}")
    print(f"Critical: {report.critical_count}/{len(report.parameter_results)}")
    print(f"Missing: {report.missing_count}/{len(report.parameter_results)}")
    print()
    
    overall_display = {
        ParameterResult.PASS: "PASS",
        ParameterResult.WARN: "PASS (with warnings)",
        ParameterResult.FAIL: "FAIL",
        ParameterResult.CRITICAL: "CRITICAL FAIL",
        ParameterResult.MISSING: "INCOMPLETE",
    }
    print(f"Overall Result: {overall_display[report.overall_result]}")
    print()
    print("-" * 70)
    print("ENGINEERING DECISION")
    print("-" * 70)
    print()
    print(f"Decision: {report.decision.value.upper().replace('_', ' ')}")
    print()
    print(f"Rationale: {report.decision_rationale}")
    print()
    print("-" * 70)
    print("DRL IMPACT")
    print("-" * 70)
    print()
    print(report.drl_impact)
    print()
    print("=" * 70)


def generate_validation_markdown(report: ValidationReport) -> str:
    """Generate markdown report for documentation."""
    result_icons = {
        ParameterResult.PASS: "PASS",
        ParameterResult.WARN: "WARN",
        ParameterResult.FAIL: "FAIL",
        ParameterResult.CRITICAL: "CRIT",
        ParameterResult.MISSING: "MISS",
    }
    
    lines = [
        "# Vendor Submission Validation Report",
        "",
        f"**Generated**: {report.generated_at.strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Submission Details",
        "",
        f"- **Vendor**: {report.vendor.legal_name} (`{report.vendor.vendor_id}`)",
        f"- **Task**: {report.task.name} (`{report.task.task_id}`)",
        f"- **Packet Hash**: `{report.submission.packet_hash}`",
        f"- **Evidence Type**: {report.submission.evidence_type}",
        f"- **Criteria Version**: {report.criteria_version}",
        "",
        "---",
        "",
        "## Parameter Validation",
        "",
        "| Parameter | Expected | Measured | Result | Deviation | Notes |",
        "|-----------|----------|----------|--------|-----------|-------|",
    ]
    
    for p in report.parameter_results:
        measured = f"{p.measured_value:.3f}" if p.measured_value is not None else "---"
        result = result_icons[p.result]
        deviation = f"{p.deviation_pct:+.1f}%" if p.deviation_pct is not None else "---"
        notes = p.notes.replace("|", "/")  # Escape pipe for markdown table
        lines.append(f"| {p.parameter} | {p.expected_value:.3f} | {measured} | {result} | {deviation} | {notes} |")
    
    overall_display = {
        ParameterResult.PASS: "PASS",
        ParameterResult.WARN: "PASS (with warnings)",
        ParameterResult.FAIL: "FAIL",
        ParameterResult.CRITICAL: "CRITICAL FAIL",
        ParameterResult.MISSING: "INCOMPLETE",
    }
    
    lines.extend([
        "",
        "---",
        "",
        "## Summary",
        "",
        f"- **Passed/Warn**: {report.passed_count}/{len(report.parameter_results)}",
        f"- **Failed**: {report.failed_count}/{len(report.parameter_results)}",
        f"- **Critical**: {report.critical_count}/{len(report.parameter_results)}",
        f"- **Missing**: {report.missing_count}/{len(report.parameter_results)}",
        f"- **Overall**: {overall_display[report.overall_result]}",
        "",
        "---",
        "",
        "## Engineering Decision",
        "",
        f"**{report.decision.value.upper().replace('_', ' ')}**",
        "",
        report.decision_rationale,
        "",
        "---",
        "",
        "## DRL Impact",
        "",
        report.drl_impact,
        "",
    ])
    
    return "\n".join(lines)


# =============================================================================
# Vendor Comparison
# =============================================================================

def compare_vendors(reports: List[ValidationReport]) -> str:
    """
    Generate vendor comparison summary.
    
    Ranks vendors by performance score (lower is better).
    Score = sum of absolute deviations + penalties for failures.
    """
    if not reports:
        return "No vendor submissions to compare."
    
    # Group by task
    by_task: Dict[str, List[ValidationReport]] = {}
    for r in reports:
        task_id = r.task.task_id
        if task_id not in by_task:
            by_task[task_id] = []
        by_task[task_id].append(r)
    
    lines = [
        "=" * 70,
        "VENDOR COMPARISON SUMMARY",
        "=" * 70,
        "",
    ]
    
    for task_id, task_reports in by_task.items():
        lines.extend([
            f"Task: {task_id}",
            "-" * 40,
            "",
        ])
        
        # Calculate scores
        scored = []
        for report in task_reports:
            score = 0
            for p in report.parameter_results:
                if p.result == ParameterResult.PASS:
                    score += abs(p.deviation_pct or 0)
                elif p.result == ParameterResult.WARN:
                    score += abs(p.deviation_pct or 0) + 10
                elif p.result == ParameterResult.FAIL:
                    score += 50 + abs(p.deviation_pct or 0)
                elif p.result == ParameterResult.CRITICAL:
                    score += 100 + abs(p.deviation_pct or 0)
                else:  # MISSING
                    score += 75
            scored.append((report, score))
        
        # Sort by score (lower is better)
        scored.sort(key=lambda x: x[1])
        
        result_display = {
            ParameterResult.PASS: "PASS",
            ParameterResult.WARN: "WARN",
            ParameterResult.FAIL: "FAIL",
            ParameterResult.CRITICAL: "CRIT",
            ParameterResult.MISSING: "MISS",
        }
        
        for i, (report, score) in enumerate(scored):
            result_str = result_display[report.overall_result]
            lines.append(
                f"  {i+1}. {report.vendor.legal_name}: "
                f"{result_str} (score: {score:.0f})"
            )
        
        # Find best passing vendor
        passing = [r for r, s in scored 
                   if r.overall_result in (ParameterResult.PASS, ParameterResult.WARN)]
        if passing:
            lines.append(f"\n  Recommended: {passing[0].vendor.legal_name}")
        else:
            lines.append(f"\n  No vendor meets all criteria.")
        
        lines.append("")
    
    lines.append("=" * 70)
    return "\n".join(lines)


# =============================================================================
# Template Generation
# =============================================================================

def generate_vendor_request_email(packet_hash: str) -> str:
    """Generate vendor request email template."""
    return f"""Subject: Data Request - Vendor Engagement Packet {packet_hash}

We are evaluating equipment for a modular septage-to-biochar system.

Please review the attached Vendor Engagement Packet (hash: {packet_hash}).

We are requesting measured data or specifications demonstrating compliance 
with the acceptance criteria in Section 4 - Validation Tasks.

Please provide results in tabular form and reference the packet hash and 
validation task ID in your response.

Required response format:

Validation Task: [task_id from packet]
Packet Hash: {packet_hash}
Evidence Type: [bench_test / lab_test / vendor_spec]

Parameter               Measured Value   Units
[parameter_name]        [value]          [units]
...

OR provide as JSON:

{{
    "packet_hash": "{packet_hash}",
    "validation_task": "[task_id]",
    "evidence_type": "[type]",
    "results": {{
        "[parameter]": [value],
        ...
    }}
}}

IMPORTANT:
- Narrative descriptions without quantitative data will not be evaluated.
- Pricing discussions will occur only after validation criteria are met.
- Reference the packet hash in all communications.

Thank you,
[Your Name]
"""


def generate_response_template(task_id: str) -> str:
    """Generate response template for a specific validation task."""
    registry = get_validation_registry()
    task = registry.get(task_id)
    
    if task is None:
        return f"Unknown task: {task_id}"
    
    lines = [
        f"Validation Task: {task_id}",
        "Packet Hash: [INSERT PACKET HASH]",
        f"Evidence Type: {task.data_type.value}",
        "",
        "Parameter               Measured Value   Units",
        "-" * 50,
    ]
    
    for c in task.acceptance_criteria:
        lines.append(f"{c.parameter:<23} [VALUE]          {c.unit}")
    
    lines.extend([
        "",
        "--- OR JSON FORMAT ---",
        "",
        "{",
        '    "packet_hash": "[INSERT PACKET HASH]",',
        f'    "validation_task": "{task_id}",',
        f'    "evidence_type": "{task.data_type.value}",',
        '    "results": {',
    ])
    
    for i, c in enumerate(task.acceptance_criteria):
        comma = "," if i < len(task.acceptance_criteria) - 1 else ""
        lines.append(f'        "{c.parameter}": [VALUE]{comma}')
    
    lines.extend([
        '    }',
        '}',
    ])
    
    return "\n".join(lines)
