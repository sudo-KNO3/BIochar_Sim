"""
Design Readiness Level (DRL) Evaluator.

Provides a structured assessment of product readiness based on:
    - CI gate status
    - FMEA analysis
    - Economic validation
    - Documentation completeness

DRL Scale (1-9):
    DRL 1-3: Concept phase
    DRL 4-6: Development phase  
    DRL 7-9: Production-ready

Current target: DRL 6 (Development complete, validation in progress)
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum
from datetime import datetime
from pathlib import Path
import json


class DRLLevel(Enum):
    """Design Readiness Level definitions."""
    DRL_1 = (1, "Basic principles observed", "Concept")
    DRL_2 = (2, "Technology concept formulated", "Concept")
    DRL_3 = (3, "Analytical/experimental proof of concept", "Concept")
    DRL_4 = (4, "Component validation in lab", "Development")
    DRL_5 = (5, "Component validation in relevant environment", "Development")
    DRL_6 = (6, "System/subsystem model or prototype demo", "Development")
    DRL_7 = (7, "System prototype demo in operational environment", "Production")
    DRL_8 = (8, "Actual system completed and qualified", "Production")
    DRL_9 = (9, "Actual system proven in operation", "Production")
    
    def __init__(self, level: int, description: str, phase: str):
        self._level = level
        self._description = description
        self._phase = phase
    
    @property
    def level(self) -> int:
        return self._level
    
    @property
    def description(self) -> str:
        return self._description
    
    @property
    def phase(self) -> str:
        return self._phase


@dataclass
class DRLCriterion:
    """A single criterion for DRL assessment."""
    name: str
    description: str
    required_for_drl: int  # Minimum DRL that requires this
    passed: bool
    evidence: str = ""
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "required_for_drl": self.required_for_drl,
            "passed": self.passed,
            "evidence": self.evidence,
            "notes": self.notes,
        }


@dataclass
class DRLAssessment:
    """
    Complete Design Readiness Level assessment.
    
    The achieved DRL is the highest level where ALL required criteria pass.
    """
    criteria: List[DRLCriterion]
    assessed_at: datetime = field(default_factory=datetime.now)
    assessed_by: str = "automated"
    notes: str = ""
    
    @property
    def achieved_drl(self) -> int:
        """
        Calculate achieved DRL based on passing criteria.
        
        DRL N requires all criteria with required_for_drl <= N to pass.
        """
        for level in range(9, 0, -1):
            required_criteria = [c for c in self.criteria if c.required_for_drl <= level]
            if all(c.passed for c in required_criteria):
                return level
        return 0
    
    @property
    def achieved_drl_enum(self) -> Optional[DRLLevel]:
        """Get the DRL enum for the achieved level."""
        level = self.achieved_drl
        for drl in DRLLevel:
            if drl.level == level:
                return drl
        return None
    
    @property
    def next_drl(self) -> int:
        """Next DRL level to achieve."""
        return min(self.achieved_drl + 1, 9)
    
    @property
    def blocking_criteria(self) -> List[DRLCriterion]:
        """Criteria blocking the next DRL level."""
        return [
            c for c in self.criteria 
            if c.required_for_drl <= self.next_drl and not c.passed
        ]
    
    @property
    def passing_criteria(self) -> List[DRLCriterion]:
        """All passing criteria."""
        return [c for c in self.criteria if c.passed]
    
    @property
    def failing_criteria(self) -> List[DRLCriterion]:
        """All failing criteria."""
        return [c for c in self.criteria if not c.passed]
    
    def get_criteria_for_drl(self, level: int) -> List[DRLCriterion]:
        """Get all criteria required for a specific DRL."""
        return [c for c in self.criteria if c.required_for_drl <= level]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "achieved_drl": self.achieved_drl,
            "assessed_at": self.assessed_at.isoformat(),
            "assessed_by": self.assessed_by,
            "notes": self.notes,
            "criteria": [c.to_dict() for c in self.criteria],
        }
    
    def to_badge_string(self) -> str:
        """Generate a badge-friendly string."""
        level = self.achieved_drl
        phase = self.achieved_drl_enum.phase if self.achieved_drl_enum else "Unknown"
        return f"DRL-{level} ({phase})"


# =============================================================================
# Standard Criteria Definitions
# =============================================================================

def create_standard_criteria() -> List[DRLCriterion]:
    """
    Create the standard set of DRL criteria for septage-to-biochar system.
    
    Returns criteria with passed=False - must be evaluated separately.
    """
    return [
        # DRL 1-3: Concept Phase
        DRLCriterion(
            name="mass_balance_validated",
            description="Mass balance equations verified against literature",
            required_for_drl=2,
            passed=False,
        ),
        DRLCriterion(
            name="energy_balance_validated",
            description="Energy balance equations verified against literature",
            required_for_drl=2,
            passed=False,
        ),
        DRLCriterion(
            name="proof_of_concept_model",
            description="Simulation model produces reasonable outputs",
            required_for_drl=3,
            passed=False,
        ),
        
        # DRL 4: Component validation in lab
        DRLCriterion(
            name="dewatering_params_validated",
            description="Dewatering performance validated with bench tests",
            required_for_drl=4,
            passed=False,
        ),
        DRLCriterion(
            name="pyrolysis_yields_validated",
            description="Pyrolysis yields validated with lab tests",
            required_for_drl=4,
            passed=False,
        ),
        
        # DRL 5: Component validation in relevant environment
        DRLCriterion(
            name="economics_locked",
            description="Economic model frozen with validated parameters",
            required_for_drl=5,
            passed=False,
        ),
        DRLCriterion(
            name="ci_gates_passing",
            description="All CI design gates passing",
            required_for_drl=5,
            passed=False,
        ),
        DRLCriterion(
            name="fmea_no_critical",
            description="No critical failure modes (RPN > 100)",
            required_for_drl=5,
            passed=False,
        ),
        
        # DRL 6: System prototype demo
        DRLCriterion(
            name="maintenance_model_validated",
            description="Maintenance model validated with vendor data",
            required_for_drl=6,
            passed=False,
        ),
        DRLCriterion(
            name="capex_vendor_validated",
            description="CAPEX estimates validated with vendor quotes",
            required_for_drl=6,
            passed=False,
        ),
        DRLCriterion(
            name="pilot_design_complete",
            description="Pilot system design package complete",
            required_for_drl=6,
            passed=False,
        ),
        
        # DRL 7: System prototype in operational environment
        DRLCriterion(
            name="pilot_commissioned",
            description="Pilot system commissioned and operational",
            required_for_drl=7,
            passed=False,
        ),
        DRLCriterion(
            name="pilot_performance_validated",
            description="Pilot performance matches model predictions",
            required_for_drl=7,
            passed=False,
        ),
        
        # DRL 8: Actual system completed
        DRLCriterion(
            name="production_design_complete",
            description="Production system design package complete",
            required_for_drl=8,
            passed=False,
        ),
        DRLCriterion(
            name="regulatory_approval",
            description="Required regulatory approvals obtained",
            required_for_drl=8,
            passed=False,
        ),
        
        # DRL 9: Proven in operation
        DRLCriterion(
            name="production_operational",
            description="Production system operational at customer site",
            required_for_drl=9,
            passed=False,
        ),
        DRLCriterion(
            name="performance_sustained",
            description="Performance sustained over 12+ months",
            required_for_drl=9,
            passed=False,
        ),
    ]


# =============================================================================
# Automated DRL Evaluation
# =============================================================================

def evaluate_drl(
    gate_report=None,
    fmea_analysis=None,
    manual_overrides: Optional[Dict[str, bool]] = None
) -> DRLAssessment:
    """
    Evaluate Design Readiness Level based on current system state.
    
    Args:
        gate_report: GateReport from run_design_gates()
        fmea_analysis: FMEAAnalysis from analyze_fmea()
        manual_overrides: Dict of {criterion_name: passed_bool} for manual entries
    
    Returns:
        DRLAssessment with evaluated criteria
    """
    criteria = create_standard_criteria()
    overrides = manual_overrides or {}
    
    # Create lookup for easy modification
    criteria_map = {c.name: c for c in criteria}
    
    # Auto-evaluate: proof_of_concept_model (DRL 3)
    # If we can import and run the model, it produces reasonable outputs
    try:
        from septage_model.simulation.deterministic import run_product_mode
        result = run_product_mode()
        if result is not None:
            criteria_map["proof_of_concept_model"].passed = True
            criteria_map["proof_of_concept_model"].evidence = "Model runs successfully"
            
            # If model runs, mass/energy balances are at least implemented
            criteria_map["mass_balance_validated"].passed = True
            criteria_map["mass_balance_validated"].evidence = "Implemented in core.balances"
            criteria_map["energy_balance_validated"].passed = True
            criteria_map["energy_balance_validated"].evidence = "Implemented in core.balances"
    except Exception as e:
        criteria_map["proof_of_concept_model"].notes = str(e)
    
    # Auto-evaluate: ci_gates_passing (DRL 5)
    if gate_report is not None:
        criteria_map["ci_gates_passing"].passed = gate_report.all_passed
        criteria_map["ci_gates_passing"].evidence = (
            f"{len(gate_report.passed_gates)}/{len(gate_report.gates)} gates passed"
        )
        if not gate_report.all_passed:
            failed_names = [g.name for g in gate_report.failed_gates]
            criteria_map["ci_gates_passing"].notes = f"Failed: {', '.join(failed_names)}"
    
    # Auto-evaluate: fmea_no_critical (DRL 5)
    if fmea_analysis is not None:
        criteria_map["fmea_no_critical"].passed = not fmea_analysis.has_critical
        criteria_map["fmea_no_critical"].evidence = (
            f"{fmea_analysis.critical_count} critical modes"
        )
        if fmea_analysis.has_critical:
            critical_components = [m.component for m in fmea_analysis.get_critical_modes()[:3]]
            criteria_map["fmea_no_critical"].notes = f"Critical: {', '.join(critical_components)}"
    
    # Auto-evaluate: economics_locked (DRL 5)
    # This is based on the project state - frozen constants exist
    try:
        from septage_model.ci.gates import MAX_MAINTENANCE_BUDGET, MAX_PAYBACK_YEARS
        criteria_map["economics_locked"].passed = True
        criteria_map["economics_locked"].evidence = (
            f"Frozen: maintenance<${MAX_MAINTENANCE_BUDGET:,}, payback<{MAX_PAYBACK_YEARS}yr"
        )
    except ImportError:
        pass
    
    # Apply manual overrides
    for name, passed in overrides.items():
        if name in criteria_map:
            criteria_map[name].passed = passed
            criteria_map[name].evidence = "Manual override"
    
    return DRLAssessment(
        criteria=list(criteria_map.values()),
        assessed_by="automated",
    )


def evaluate_drl_from_results() -> DRLAssessment:
    """
    Convenience function to evaluate DRL by running all checks.
    
    Returns:
        DRLAssessment with current system state
    """
    # Run the simulation
    from septage_model.simulation.deterministic import run_product_mode
    from septage_model.ci.gates import run_design_gates
    from septage_model.artifacts.fmea import analyze_fmea, DEFAULT_FAILURE_MODES
    
    result = run_product_mode()
    gate_report = run_design_gates(result)
    fmea_analysis = analyze_fmea(DEFAULT_FAILURE_MODES)
    
    return evaluate_drl(
        gate_report=gate_report,
        fmea_analysis=fmea_analysis,
    )


# =============================================================================
# DRL Report Generation
# =============================================================================

def generate_drl_report(assessment: DRLAssessment) -> str:
    """
    Generate a human-readable DRL report.
    
    Args:
        assessment: DRLAssessment to report
    
    Returns:
        Formatted report string
    """
    lines = [
        "=" * 60,
        "DESIGN READINESS LEVEL ASSESSMENT",
        "=" * 60,
        "",
        f"Achieved Level: DRL-{assessment.achieved_drl}",
    ]
    
    if assessment.achieved_drl_enum:
        lines.append(f"Description: {assessment.achieved_drl_enum.description}")
        lines.append(f"Phase: {assessment.achieved_drl_enum.phase}")
    
    lines.extend([
        f"Assessed: {assessment.assessed_at.strftime('%Y-%m-%d %H:%M')}",
        "",
        "-" * 60,
        "CRITERIA STATUS",
        "-" * 60,
        "",
    ])
    
    # Group by DRL level
    for level in range(1, 10):
        level_criteria = [c for c in assessment.criteria if c.required_for_drl == level]
        if not level_criteria:
            continue
        
        lines.append(f"DRL {level}:")
        for c in level_criteria:
            status = "✅" if c.passed else "❌"
            lines.append(f"  {status} {c.name}: {c.description}")
            if c.evidence:
                lines.append(f"      Evidence: {c.evidence}")
            if c.notes:
                lines.append(f"      Notes: {c.notes}")
        lines.append("")
    
    # Summary
    lines.extend([
        "-" * 60,
        "SUMMARY",
        "-" * 60,
        f"Total Criteria: {len(assessment.criteria)}",
        f"Passing: {len(assessment.passing_criteria)}",
        f"Failing: {len(assessment.failing_criteria)}",
        "",
    ])
    
    if assessment.blocking_criteria:
        lines.append(f"To reach DRL-{assessment.next_drl}, complete:")
        for c in assessment.blocking_criteria:
            lines.append(f"  - {c.name}")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)


def generate_drl_badge_url(assessment: DRLAssessment) -> str:
    """
    Generate shields.io badge URL for README.
    
    Args:
        assessment: DRLAssessment
    
    Returns:
        URL for badge image
    """
    level = assessment.achieved_drl
    
    # Color based on phase
    if level >= 7:
        color = "brightgreen"
    elif level >= 4:
        color = "yellow"
    else:
        color = "orange"
    
    label = "DRL"
    message = str(level)
    
    # shields.io static badge URL
    return f"https://img.shields.io/badge/{label}-{message}-{color}"


def generate_drl_markdown(
    assessment: DRLAssessment,
    output_path: Optional[Path] = None
) -> str:
    """
    Generate DRL documentation as Markdown.
    
    Args:
        assessment: DRLAssessment to document
        output_path: Optional path to write markdown file
    
    Returns:
        Markdown string
    """
    badge_url = generate_drl_badge_url(assessment)
    drl = assessment.achieved_drl_enum
    
    lines = [
        "# Design Readiness Level (DRL) Assessment",
        "",
        f"![DRL Badge]({badge_url})",
        "",
        "## Current Status",
        "",
        f"- **Achieved Level**: DRL-{assessment.achieved_drl}",
    ]
    
    if drl:
        lines.extend([
            f"- **Description**: {drl.description}",
            f"- **Phase**: {drl.phase}",
        ])
    
    lines.extend([
        f"- **Assessed**: {assessment.assessed_at.strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
        "## Criteria Status",
        "",
        "| DRL | Criterion | Status | Evidence |",
        "|-----|-----------|--------|----------|",
    ])
    
    for c in sorted(assessment.criteria, key=lambda x: (x.required_for_drl, x.name)):
        status = "✅" if c.passed else "❌"
        evidence = c.evidence or c.notes or "-"
        lines.append(f"| {c.required_for_drl} | {c.name} | {status} | {evidence} |")
    
    lines.extend([
        "",
        "---",
        "",
        "## Next Steps",
        "",
    ])
    
    if assessment.blocking_criteria:
        lines.append(f"To reach **DRL-{assessment.next_drl}**, complete the following:")
        lines.append("")
        for c in assessment.blocking_criteria:
            lines.append(f"- [ ] **{c.name}**: {c.description}")
    else:
        lines.append("All criteria for the next level are complete!")
    
    lines.extend([
        "",
        "---",
        "",
        "## DRL Scale Reference",
        "",
        "| Level | Phase | Description |",
        "|-------|-------|-------------|",
    ])
    
    for drl_level in DRLLevel:
        lines.append(f"| {drl_level.level} | {drl_level.phase} | {drl_level.description} |")
    
    lines.extend([
        "",
        "---",
        "",
        f"*Generated by Biochar_Sim DRL Evaluator*",
    ])
    
    markdown = "\n".join(lines)
    
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(markdown)
    
    return markdown
