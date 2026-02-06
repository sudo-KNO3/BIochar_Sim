"""
FMEA Module - Failure Mode and Effects Analysis.

Provides hardcoded realistic defaults for all subsystems.
Parameterized for future vendor data override.

RPN Thresholds:
    - RPN > 100: CRITICAL - requires redesign or mitigation
    - RPN 50-100: MODERATE - monitor and improve
    - RPN < 50: ACCEPTABLE - standard maintenance

Subsystems covered:
    - Receiving & Dewatering
    - Drying
    - Pyrolysis
    - Char Handling
    - Syngas & Energy
    - Controls & Safety
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path
from enum import Enum
import json


class Subsystem(Enum):
    """Subsystems in the septage-to-biochar process."""
    RECEIVING = "receiving"
    DEWATERING = "dewatering"
    DRYING = "drying"
    PYROLYSIS = "pyrolysis"
    CHAR_HANDLING = "char_handling"
    SYNGAS_ENERGY = "syngas_energy"
    CONTROLS_SAFETY = "controls_safety"


class Severity(Enum):
    """
    Severity of failure effect (1-10 scale).
    
    10: Safety hazard, no warning
    9: Safety hazard with warning
    8: System inoperable, major repair
    7: System impaired, significant repair
    6: System impaired, moderate repair
    5: System operable with degraded performance
    4: System operable, minor performance impact
    3: Nuisance, cosmetic issue
    2: Very minor effect
    1: No effect
    """
    CATASTROPHIC = 10
    SAFETY_WARNING = 9
    SYSTEM_DOWN = 8
    MAJOR_IMPAIRED = 7
    MODERATE_IMPAIRED = 6
    DEGRADED = 5
    MINOR_IMPACT = 4
    NUISANCE = 3
    VERY_MINOR = 2
    NO_EFFECT = 1


class MitigationStatus(Enum):
    """
    Status of mitigation implementation.
    
    PROPOSED: Mitigation identified but not yet designed/implemented
    IMPLEMENTED: Mitigation designed into system but not validated
    VALIDATED: Mitigation proven effective through testing/operation
    """
    PROPOSED = "proposed"
    IMPLEMENTED = "implemented"
    VALIDATED = "validated"


@dataclass
class FailureMode:
    """
    A single failure mode with RPN calculation.
    
    RPN = Severity × Occurrence × Detection
    
    Attributes:
        subsystem: Which subsystem this failure belongs to
        component: Specific component that fails
        failure_mode: Description of how it fails
        effect: What happens when it fails
        cause: Root cause of failure
        severity: Impact of failure (1-10)
        occurrence: Likelihood of failure (1-10)
        detection: Ability to detect before failure (1-10, lower is better)
        mitigation: Current or proposed mitigation
        owner_serviceable: Can owner perform repair?
        mttr_hours: Mean time to repair
        estimated_cost: Repair cost estimate
    """
    subsystem: Subsystem
    component: str
    failure_mode: str
    effect: str
    cause: str
    severity: int
    occurrence: int
    detection: int
    mitigation: str = ""
    mitigation_status: 'MitigationStatus' = None  # type: ignore
    owner_serviceable: bool = True
    mttr_hours: float = 2.0
    estimated_cost: float = 500.0
    
    def __post_init__(self):
        """Set default mitigation_status if not provided."""
        if self.mitigation_status is None:
            # Default: if mitigation text exists, assume proposed
            object.__setattr__(self, 'mitigation_status', 
                MitigationStatus.PROPOSED if self.mitigation else MitigationStatus.PROPOSED)
    
    @property
    def is_mitigated(self) -> bool:
        """True if mitigation is implemented or validated."""
        return self.mitigation_status in (MitigationStatus.IMPLEMENTED, MitigationStatus.VALIDATED)
    
    @property
    def rpn(self) -> int:
        """Risk Priority Number = S × O × D."""
        return self.severity * self.occurrence * self.detection
    
    @property
    def is_critical(self) -> bool:
        """RPN > 100 requires redesign."""
        return self.rpn > 100
    
    @property
    def is_moderate(self) -> bool:
        """RPN 50-100 requires monitoring."""
        return 50 <= self.rpn <= 100
    
    @property
    def risk_level(self) -> str:
        """Human-readable risk classification."""
        if self.is_critical:
            return "CRITICAL"
        elif self.is_moderate:
            return "MODERATE"
        else:
            return "ACCEPTABLE"
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "subsystem": self.subsystem.value,
            "component": self.component,
            "failure_mode": self.failure_mode,
            "mitigation_status": self.mitigation_status.value if self.mitigation_status else "proposed",
            "effect": self.effect,
            "cause": self.cause,
            "severity": self.severity,
            "occurrence": self.occurrence,
            "detection": self.detection,
            "rpn": self.rpn,
            "risk_level": self.risk_level,
            "mitigation": self.mitigation,
            "owner_serviceable": self.owner_serviceable,
            "mttr_hours": self.mttr_hours,
            "estimated_cost": self.estimated_cost,
        }


# =============================================================================
# DEFAULT FAILURE MODES - Realistic estimates for each subsystem
# =============================================================================

DEFAULT_FAILURE_MODES: List[FailureMode] = [
    # -------------------------------------------------------------------------
    # RECEIVING
    # -------------------------------------------------------------------------
    FailureMode(
        subsystem=Subsystem.RECEIVING,
        component="Receiving Tank Level Sensor",
        failure_mode="Sensor drift/failure",
        effect="Overfill or dry-run pump",
        cause="Fouling, calibration drift",
        severity=5,
        occurrence=4,
        detection=3,
        mitigation="Redundant sensor, weekly calibration check",
        owner_serviceable=True,
        mttr_hours=1.0,
        estimated_cost=200.0,
    ),
    FailureMode(
        subsystem=Subsystem.RECEIVING,
        component="Receiving Pump",
        failure_mode="Pump seal failure",
        effect="Leakage, reduced flow",
        cause="Wear, abrasive solids",
        severity=6,
        occurrence=3,
        detection=4,
        mitigation="Progressive cavity pump with replaceable stator",
        owner_serviceable=True,
        mttr_hours=3.0,
        estimated_cost=800.0,
    ),
    FailureMode(
        subsystem=Subsystem.RECEIVING,
        component="Receiving Tank Mixer",
        failure_mode="Mixer blade wear/failure",
        effect="Poor mixing, settling",
        cause="Abrasive solids, fatigue",
        severity=4,
        occurrence=3,
        detection=5,
        mitigation="Hardened blades, visual inspection window",
        owner_serviceable=True,
        mttr_hours=2.0,
        estimated_cost=400.0,
    ),
    
    # -------------------------------------------------------------------------
    # DEWATERING
    # -------------------------------------------------------------------------
    FailureMode(
        subsystem=Subsystem.DEWATERING,
        component="Screw Press",
        failure_mode="Screw wear/binding",
        effect="Reduced throughput, cake too wet",
        cause="Abrasive solids, overload",
        severity=6,
        occurrence=4,
        detection=4,
        mitigation="Modular flight design, torque monitoring",
        owner_serviceable=True,
        mttr_hours=4.0,
        estimated_cost=1500.0,
    ),
    FailureMode(
        subsystem=Subsystem.DEWATERING,
        component="Polymer Dosing Pump",
        failure_mode="Pump diaphragm failure",
        effect="No polymer, poor dewatering",
        cause="Chemical attack, fatigue",
        severity=5,
        occurrence=4,
        detection=3,
        mitigation="Peristaltic backup, flow alarm",
        owner_serviceable=True,
        mttr_hours=1.5,
        estimated_cost=300.0,
    ),
    FailureMode(
        subsystem=Subsystem.DEWATERING,
        component="Filtrate Return Pump",
        failure_mode="Impeller clog",
        effect="Backup, overflow risk",
        cause="Fiber accumulation",
        severity=5,
        occurrence=3,
        detection=4,
        mitigation="Self-cleaning pump, strainer upstream",
        owner_serviceable=True,
        mttr_hours=1.0,
        estimated_cost=250.0,
    ),
    FailureMode(
        subsystem=Subsystem.DEWATERING,
        component="Cake Conveyor",
        failure_mode="Belt tracking/slip",
        effect="Spillage, shutdown",
        cause="Misalignment, wear",
        severity=4,
        occurrence=3,
        detection=3,
        mitigation="Screw conveyor alternative, alignment sensors",
        owner_serviceable=True,
        mttr_hours=2.0,
        estimated_cost=350.0,
    ),
    
    # -------------------------------------------------------------------------
    # DRYING
    # -------------------------------------------------------------------------
    FailureMode(
        subsystem=Subsystem.DRYING,
        component="Dryer Auger/Flights",
        failure_mode="Wear/binding",
        effect="Reduced drying, overheating",
        cause="High temp, abrasion",
        severity=7,
        occurrence=3,  # Reduced: modular flight segments allow targeted replacement
        detection=3,   # Reduced: vibration monitoring + torque trending
        mitigation="Modular bolt-on flight segments (owner-replaceable), vibration sensors with trend analysis, torque monitoring with auto-shutdown",
        mitigation_status=MitigationStatus.PROPOSED,
        owner_serviceable=True,
        mttr_hours=4.0,  # Reduced: modular design
        estimated_cost=1200.0,  # Reduced: replace segments not full auger
    ),
    FailureMode(
        subsystem=Subsystem.DRYING,
        component="Dryer Burner",
        failure_mode="Ignition failure",
        effect="System shutdown",
        cause="Flame sensor, electrode wear",
        severity=7,
        occurrence=3,
        detection=2,
        mitigation="Dual ignition, flame supervision",
        owner_serviceable=False,
        mttr_hours=4.0,
        estimated_cost=1200.0,
    ),
    FailureMode(
        subsystem=Subsystem.DRYING,
        component="Exhaust Blower",
        failure_mode="Bearing failure",
        effect="Overheating, shutdown",
        cause="High temp, dust ingress",
        severity=6,
        occurrence=3,
        detection=3,
        mitigation="Vibration sensor, sealed bearings",
        owner_serviceable=True,
        mttr_hours=3.0,
        estimated_cost=800.0,
    ),
    FailureMode(
        subsystem=Subsystem.DRYING,
        component="Dryer Temperature Sensor",
        failure_mode="Sensor drift",
        effect="Over/under drying",
        cause="High temp degradation",
        severity=5,
        occurrence=4,
        detection=3,
        mitigation="Redundant sensors, cross-check logic",
        owner_serviceable=True,
        mttr_hours=1.0,
        estimated_cost=150.0,
    ),
    
    # -------------------------------------------------------------------------
    # PYROLYSIS
    # -------------------------------------------------------------------------
    FailureMode(
        subsystem=Subsystem.PYROLYSIS,
        component="Pyrolyzer Auger",
        failure_mode="Auger seizure",
        effect="Complete shutdown, high repair",
        cause="Char buildup, thermal expansion",
        severity=8,
        occurrence=3,
        detection=4,
        mitigation="Torque monitoring, modular sections",
        owner_serviceable=False,
        mttr_hours=8.0,
        estimated_cost=4000.0,
    ),
    FailureMode(
        subsystem=Subsystem.PYROLYSIS,
        component="Pyrolyzer Seals",
        failure_mode="Seal degradation",
        effect="Air ingress, syngas quality loss",
        cause="High temp cycling",
        severity=7,
        occurrence=4,
        detection=3,   # Reduced: redundant O2 sensors + predictive seal-life tracking
        mitigation="Quick-change cartridge seal design, redundant O2 sensors (inlet/outlet differential), seal-life tracking based on thermal cycles, scheduled replacement at 80% predicted life",
        mitigation_status=MitigationStatus.PROPOSED,
        owner_serviceable=True,
        mttr_hours=1.5,  # Reduced: cartridge design
        estimated_cost=400.0,  # Reduced: cartridge vs custom seal
    ),
    FailureMode(
        subsystem=Subsystem.PYROLYSIS,
        component="Pyrolyzer Heating Elements",
        failure_mode="Element burnout",
        effect="Temp loss, incomplete conversion",
        cause="Oxidation, cycling",
        severity=6,
        occurrence=3,
        detection=3,
        mitigation="Redundant zones, zone isolation",
        owner_serviceable=False,
        mttr_hours=4.0,
        estimated_cost=2500.0,
    ),
    FailureMode(
        subsystem=Subsystem.PYROLYSIS,
        component="Char Discharge Valve",
        failure_mode="Valve sticking",
        effect="Char backup, shutdown",
        cause="Hot char adhesion",
        severity=6,
        occurrence=4,
        detection=4,
        mitigation="Water-cooled valve, position feedback",
        owner_serviceable=True,
        mttr_hours=2.0,
        estimated_cost=700.0,
    ),
    
    # -------------------------------------------------------------------------
    # CHAR HANDLING
    # -------------------------------------------------------------------------
    FailureMode(
        subsystem=Subsystem.CHAR_HANDLING,
        component="Char Cooler",
        failure_mode="Cooling water blockage",
        effect="Hot char, fire risk",
        cause="Scale, debris",
        severity=8,
        occurrence=2,
        detection=3,
        mitigation="Temp monitoring, bypass capability",
        owner_serviceable=True,
        mttr_hours=2.0,
        estimated_cost=400.0,
    ),
    FailureMode(
        subsystem=Subsystem.CHAR_HANDLING,
        component="Char Screw Conveyor",
        failure_mode="Screw wear",
        effect="Reduced throughput",
        cause="Abrasive char",
        severity=4,
        occurrence=4,
        detection=4,
        mitigation="Hardened flights, throughput monitoring",
        owner_serviceable=True,
        mttr_hours=3.0,
        estimated_cost=600.0,
    ),
    FailureMode(
        subsystem=Subsystem.CHAR_HANDLING,
        component="Char Storage Silo",
        failure_mode="Bridging/ratholing",
        effect="Flow stoppage",
        cause="Moisture, fines",
        severity=4,
        occurrence=3,
        detection=4,
        mitigation="Vibrating discharge, moisture control",
        owner_serviceable=True,
        mttr_hours=1.5,
        estimated_cost=200.0,
    ),
    
    # -------------------------------------------------------------------------
    # SYNGAS & ENERGY
    # -------------------------------------------------------------------------
    FailureMode(
        subsystem=Subsystem.SYNGAS_ENERGY,
        component="Syngas Blower",
        failure_mode="Bearing failure",
        effect="Energy loss, flare activation",
        cause="Tar condensation, heat",
        severity=6,
        occurrence=3,
        detection=3,
        mitigation="Vibration monitoring, tar separator",
        owner_serviceable=True,
        mttr_hours=4.0,
        estimated_cost=1200.0,
    ),
    FailureMode(
        subsystem=Subsystem.SYNGAS_ENERGY,
        component="Syngas Burner",
        failure_mode="Nozzle fouling",
        effect="Incomplete combustion, emissions",
        cause="Tar, particulate",
        severity=6,
        occurrence=4,
        detection=3,
        mitigation="Self-cleaning design, redundant burner",
        owner_serviceable=True,
        mttr_hours=2.0,
        estimated_cost=500.0,
    ),
    FailureMode(
        subsystem=Subsystem.SYNGAS_ENERGY,
        component="Flare Stack",
        failure_mode="Igniter failure",
        effect="Syngas release (safety)",
        cause="Electrode wear",
        severity=9,
        occurrence=2,
        detection=2,
        mitigation="Continuous pilot, UV sensor",
        owner_serviceable=False,
        mttr_hours=3.0,
        estimated_cost=800.0,
    ),
    FailureMode(
        subsystem=Subsystem.SYNGAS_ENERGY,
        component="Heat Exchanger",
        failure_mode="Tube fouling",
        effect="Reduced heat recovery",
        cause="Tar, soot",
        severity=4,
        occurrence=4,
        detection=5,
        mitigation="Soot blowers, ΔT monitoring",
        owner_serviceable=True,
        mttr_hours=4.0,
        estimated_cost=600.0,
    ),
    
    # -------------------------------------------------------------------------
    # CONTROLS & SAFETY
    # -------------------------------------------------------------------------
    FailureMode(
        subsystem=Subsystem.CONTROLS_SAFETY,
        component="PLC Controller",
        failure_mode="Processor lockup",
        effect="System shutdown (fail-safe)",
        cause="Software bug, power glitch",
        severity=7,
        occurrence=2,
        detection=2,
        mitigation="Watchdog timer, UPS, dual CPU option",
        owner_serviceable=False,
        mttr_hours=2.0,
        estimated_cost=300.0,
    ),
    FailureMode(
        subsystem=Subsystem.CONTROLS_SAFETY,
        component="Emergency Stop System",
        failure_mode="E-stop stuck/failed",
        effect="Cannot stop safely",
        cause="Mechanical failure, corrosion",
        severity=10,
        occurrence=1,
        detection=2,
        mitigation="Monthly testing, redundant circuits",
        owner_serviceable=True,
        mttr_hours=1.0,
        estimated_cost=150.0,
    ),
    FailureMode(
        subsystem=Subsystem.CONTROLS_SAFETY,
        component="Gas Detection System",
        failure_mode="Sensor drift/failure",
        effect="Undetected gas leak",
        cause="Sensor aging, poisoning",
        severity=9,
        occurrence=2,
        detection=2,
        mitigation="Dual sensors, bump testing",
        owner_serviceable=True,
        mttr_hours=1.0,
        estimated_cost=400.0,
    ),
    FailureMode(
        subsystem=Subsystem.CONTROLS_SAFETY,
        component="Fire Suppression",
        failure_mode="Activation failure",
        effect="Fire damage",
        cause="Nozzle clog, pressure loss",
        severity=10,
        occurrence=1,
        detection=3,
        mitigation="Annual inspection, pressure monitoring",
        owner_serviceable=False,
        mttr_hours=4.0,
        estimated_cost=1500.0,
    ),
]


# =============================================================================
# FMEA Analysis Functions
# =============================================================================

@dataclass
class FMEAAnalysis:
    """Summary of FMEA analysis results."""
    failure_modes: List[FailureMode]
    critical_count: int = 0
    moderate_count: int = 0
    acceptable_count: int = 0
    total_rpn: int = 0
    avg_rpn: float = 0.0
    owner_serviceable_pct: float = 0.0
    
    @classmethod
    def from_modes(cls, modes: List[FailureMode]) -> 'FMEAAnalysis':
        """Create analysis from list of failure modes."""
        if not modes:
            return cls(failure_modes=[])
        
        critical = sum(1 for m in modes if m.is_critical)
        moderate = sum(1 for m in modes if m.is_moderate)
        acceptable = len(modes) - critical - moderate
        total_rpn = sum(m.rpn for m in modes)
        owner_serviceable = sum(1 for m in modes if m.owner_serviceable)
        
        return cls(
            failure_modes=modes,
            critical_count=critical,
            moderate_count=moderate,
            acceptable_count=acceptable,
            total_rpn=total_rpn,
            avg_rpn=total_rpn / len(modes),
            owner_serviceable_pct=owner_serviceable / len(modes) * 100,
        )
    
    @property
    def has_critical(self) -> bool:
        """Any critical failure modes require redesign."""
        return self.critical_count > 0
    
    def get_critical_modes(self) -> List[FailureMode]:
        """Get all critical failure modes (RPN > 100)."""
        return [m for m in self.failure_modes if m.is_critical]
    
    def get_by_subsystem(self, subsystem: Subsystem) -> List[FailureMode]:
        """Get failure modes for a specific subsystem."""
        return [m for m in self.failure_modes if m.subsystem == subsystem]


def load_fmea(override_path: Optional[Path] = None) -> List[FailureMode]:
    """
    Load FMEA data from JSON file or return defaults.
    
    Args:
        override_path: Optional path to vendor-provided FMEA JSON file.
                      If None or file doesn't exist, returns DEFAULT_FAILURE_MODES.
    
    Returns:
        List of FailureMode objects
    
    File format (JSON):
        [
            {
                "subsystem": "dewatering",
                "component": "Screw Press",
                "failure_mode": "Screw wear",
                ...
            },
            ...
        ]
    """
    if override_path is None:
        return DEFAULT_FAILURE_MODES.copy()
    
    if not override_path.exists():
        return DEFAULT_FAILURE_MODES.copy()
    
    try:
        with open(override_path, 'r') as f:
            data = json.load(f)
        
        modes = []
        for item in data:
            mode = FailureMode(
                subsystem=Subsystem(item["subsystem"]),
                component=item["component"],
                failure_mode=item["failure_mode"],
                effect=item["effect"],
                cause=item["cause"],
                severity=item["severity"],
                occurrence=item["occurrence"],
                detection=item["detection"],
                mitigation=item.get("mitigation", ""),
                owner_serviceable=item.get("owner_serviceable", True),
                mttr_hours=item.get("mttr_hours", 2.0),
                estimated_cost=item.get("estimated_cost", 500.0),
            )
            modes.append(mode)
        
        return modes
    
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        # Fall back to defaults if file is malformed
        print(f"Warning: Could not load FMEA from {override_path}: {e}")
        return DEFAULT_FAILURE_MODES.copy()


def analyze_fmea(modes: Optional[List[FailureMode]] = None) -> FMEAAnalysis:
    """
    Analyze failure modes and return summary.
    
    Args:
        modes: List of failure modes. If None, uses defaults.
    
    Returns:
        FMEAAnalysis with summary statistics
    """
    if modes is None:
        modes = DEFAULT_FAILURE_MODES
    
    return FMEAAnalysis.from_modes(modes)


def generate_fmea_markdown(
    modes: Optional[List[FailureMode]] = None,
    output_path: Optional[Path] = None
) -> str:
    """
    Generate FMEA documentation as Markdown.
    
    Critical modes (RPN > 100) are highlighted in red.
    
    Args:
        modes: List of failure modes. If None, uses defaults.
        output_path: Optional path to write markdown file.
    
    Returns:
        Markdown string
    """
    if modes is None:
        modes = DEFAULT_FAILURE_MODES
    
    analysis = FMEAAnalysis.from_modes(modes)
    
    lines = [
        "# Failure Mode and Effects Analysis (FMEA)",
        "",
        "## Summary",
        "",
        f"- **Total Failure Modes**: {len(modes)}",
        f"- **Critical (RPN > 100)**: {analysis.critical_count} ⚠️",
        f"- **Moderate (RPN 50-100)**: {analysis.moderate_count}",
        f"- **Acceptable (RPN < 50)**: {analysis.acceptable_count}",
        f"- **Average RPN**: {analysis.avg_rpn:.1f}",
        f"- **Owner Serviceable**: {analysis.owner_serviceable_pct:.0f}%",
        "",
        "---",
        "",
    ]
    
    # Critical modes section
    critical_modes = analysis.get_critical_modes()
    if critical_modes:
        lines.extend([
            "## ⚠️ Critical Failure Modes (Requires Redesign)",
            "",
            "These failure modes have RPN > 100 and require design changes or enhanced mitigation.",
            "",
            "| Subsystem | Component | Failure Mode | RPN | Status | Mitigation |",
            "|-----------|-----------|--------------|-----|--------|------------|",
        ])
        for m in sorted(critical_modes, key=lambda x: x.rpn, reverse=True):
            status_icon = "⏳" if m.mitigation_status == MitigationStatus.PROPOSED else ("🔧" if m.mitigation_status == MitigationStatus.IMPLEMENTED else "✅")
            lines.append(
                f"| {m.subsystem.value} | {m.component} | {m.failure_mode} | "
                f"**{m.rpn}** 🔴 | {status_icon} {m.mitigation_status.value} | {m.mitigation} |"
            )
        lines.extend(["", "---", ""])
    
    # Full table by subsystem
    lines.extend([
        "## Full FMEA Table by Subsystem",
        "",
    ])
    
    for subsystem in Subsystem:
        subsystem_modes = [m for m in modes if m.subsystem == subsystem]
        if not subsystem_modes:
            continue
        
        lines.extend([
            f"### {subsystem.value.replace('_', ' ').title()}",
            "",
            "| Component | Failure Mode | S | O | D | RPN | Risk | Status | Serviceable |",
            "|-----------|--------------|---|---|---|-----|------|--------|-------------|",
        ])
        
        for m in sorted(subsystem_modes, key=lambda x: x.rpn, reverse=True):
            risk_icon = "🔴" if m.is_critical else ("🟡" if m.is_moderate else "🟢")
            serviceable = "✅" if m.owner_serviceable else "❌"
            status_abbrev = "P" if m.mitigation_status == MitigationStatus.PROPOSED else ("I" if m.mitigation_status == MitigationStatus.IMPLEMENTED else "V")
            lines.append(
                f"| {m.component} | {m.failure_mode} | {m.severity} | "
                f"{m.occurrence} | {m.detection} | {m.rpn} | {risk_icon} | {status_abbrev} | {serviceable} |"
            )
        
        lines.extend(["", ""])
    
    # RPN Scale Reference
    lines.extend([
        "---",
        "",
        "## RPN Scale Reference",
        "",
        "**Risk Priority Number (RPN) = Severity × Occurrence × Detection**",
        "",
        "| Scale | Severity | Occurrence | Detection |",
        "|-------|----------|------------|-----------|",
        "| 10 | Safety hazard, no warning | Almost certain | Cannot detect |",
        "| 7-9 | Major system impact | High | Poor detection |",
        "| 4-6 | Moderate impact | Moderate | Some detection |",
        "| 1-3 | Minor/no impact | Rare | Good detection |",
        "",
        "**Thresholds:**",
        "- 🔴 **RPN > 100**: CRITICAL - Requires redesign or enhanced mitigation",
        "- 🟡 **RPN 50-100**: MODERATE - Monitor and improve",
        "- 🟢 **RPN < 50**: ACCEPTABLE - Standard maintenance",
        "",
        "**Mitigation Status:**",
        "- **P** (Proposed): Mitigation identified, not yet implemented",
        "- **I** (Implemented): Mitigation designed into system, not validated",
        "- **V** (Validated): Mitigation proven effective",
        "",
        "---",
        "",
        f"*Generated by Biochar_Sim FMEA Module*",
    ])
    
    markdown = "\n".join(lines)
    
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown)
    
    return markdown


# =============================================================================
# FMEA Gate (for CI integration)
# =============================================================================

def fmea_criticality_gate(modes: Optional[List[FailureMode]] = None) -> 'GateResult':
    """
    Gate: No failure modes with RPN > 100 allowed.
    
    Args:
        modes: List of failure modes. If None, uses defaults.
    
    Returns:
        GateResult with pass/fail
    """
    # Import here to avoid circular dependency
    from septage_model.ci.gates import GateResult
    
    if modes is None:
        modes = DEFAULT_FAILURE_MODES
    
    analysis = FMEAAnalysis.from_modes(modes)
    
    passed = analysis.critical_count == 0
    
    remediation = None
    if not passed:
        critical = analysis.get_critical_modes()
        components = ", ".join(m.component for m in critical[:3])
        if len(critical) > 3:
            components += f" (+{len(critical)-3} more)"
        
        remediation = (
            f"{analysis.critical_count} failure mode(s) exceed RPN threshold. "
            f"Critical components: {components}. "
            "Review design for: improved detection, reduced occurrence, "
            "or modular replacement to reduce severity. "
            "Do NOT attempt to fix via revenue assumptions."
        )
    
    return GateResult(
        name="FMEA Criticality",
        passed=passed,
        value=float(analysis.critical_count),
        threshold=0.0,
        remediation=remediation,
    )
