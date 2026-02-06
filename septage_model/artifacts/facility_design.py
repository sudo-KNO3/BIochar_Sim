"""
Facility Design Module - Canonical equipment lists and operating mode specifications.

This module defines the physical facility requirements for both deployment modes:
    - Product Mode: Owner-operator unit (1-3 trucks/day, centrate haul-off)
    - Hub Mode: 9-5 light-ops facility (12-15 trucks/day, permitted discharge)

Design anchors (locked 2026-02-06):
    - Hub receiving window: 08:00-16:00
    - Hub peak trucks: 12-15/day
    - Hub centrate: local discharge Mon-Fri 08:00-16:00
    - Product trucks: 1-3/day (owner schedule)
    - Product centrate: haul-off to WWTP (default)

These specifications define what makes a concept "buildable" vs "just a model."
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Literal
from enum import Enum
from datetime import datetime


# =============================================================================
# Enums and Types
# =============================================================================

class DeploymentMode(Enum):
    """Facility deployment mode."""
    PRODUCT = "product"          # Owner-operator unit
    HUB = "hub"                  # 9-5 light-ops facility


class Subsystem(Enum):
    """Facility subsystems."""
    RECEIVING = "receiving"
    STORAGE = "storage"
    DEWATERING = "dewatering"
    CAKE_HANDLING = "cake_handling"
    PYROLYSIS = "pyrolysis"
    CHAR_HANDLING = "char_handling"
    UTILITIES = "utilities"
    SITE_SYSTEMS = "site_systems"
    COMPLIANCE = "compliance"


class OperatingPhase(Enum):
    """Facility operating phases."""
    STARTUP = "startup"
    NORMAL_DAY = "normal_day"
    END_OF_DAY = "end_of_day"
    OVERNIGHT = "overnight"
    MORNING_RESTART = "morning_restart"
    SHUTDOWN = "shutdown"
    FAILURE_HANDLING = "failure_handling"


class NightMode(Enum):
    """Reactor night mode options (vendor-dependent)."""
    HOT_HOLD = "hot_hold"
    CONTROLLED_COOLDOWN = "controlled_cooldown"
    INERT_PURGE = "inert_purge"
    FULL_SHUTDOWN = "full_shutdown"


class CentrateDisposition(Enum):
    """How centrate leaves the site."""
    LOCAL_DISCHARGE = "local_discharge"
    HAUL_OFF = "haul_off"
    LAGOON = "lagoon"


# =============================================================================
# Equipment Item Dataclass
# =============================================================================

@dataclass(frozen=True)
class EquipmentItem:
    """A single piece of equipment in the facility."""
    tag: str
    name: str
    subsystem: Subsystem
    description: str
    sizing_basis: str
    owner_serviceable: bool = True
    spare_required: bool = False
    winterization_required: bool = False
    notes: Optional[str] = None


@dataclass(frozen=True)
class BestPractice:
    """A design best practice that must be followed."""
    id: str
    subsystem: Subsystem
    requirement: str
    rationale: str
    failure_if_skipped: str


# =============================================================================
# Product Mode Equipment List
# =============================================================================

PRODUCT_MODE_EQUIPMENT: List[EquipmentItem] = [
    # --- Receiving & Pre-treatment ---
    EquipmentItem(
        tag="RCV-101",
        name="Truck Discharge Station",
        subsystem=Subsystem.RECEIVING,
        description="Hose connection or dump point with splash control and washdown",
        sizing_basis="Single truck connection, 12 m³ capacity",
        owner_serviceable=True,
        winterization_required=True,
    ),
    EquipmentItem(
        tag="SCR-101",
        name="Coarse Screen",
        subsystem=Subsystem.RECEIVING,
        description="Basket screen or inline grinder for trash removal",
        sizing_basis="Peak flow rate from EQ pump",
        owner_serviceable=True,
        notes="Basket preferred for serviceability; grinder if rags are common",
    ),
    EquipmentItem(
        tag="GRT-101",
        name="Grit Separator",
        subsystem=Subsystem.RECEIVING,
        description="Compact grit box or vortex grit separator",
        sizing_basis="Septage flow rate, 2-5 min retention",
        owner_serviceable=True,
    ),
    EquipmentItem(
        tag="SMP-101",
        name="Receiving Sump",
        subsystem=Subsystem.RECEIVING,
        description="Collection sump for all receiving area drainage",
        sizing_basis="Spill containment + washdown volume",
        owner_serviceable=True,
    ),
    EquipmentItem(
        tag="P-101",
        name="Transfer Pump",
        subsystem=Subsystem.RECEIVING,
        description="Progressive cavity pump, trash tolerant",
        sizing_basis="Peak receiving rate to EQ tank",
        owner_serviceable=True,
        notes="PC pump preferred; seal/rotor are owner-replaceable",
    ),
    
    # --- Storage & Equalization ---
    EquipmentItem(
        tag="TK-101",
        name="Equalization Tank",
        subsystem=Subsystem.STORAGE,
        description="3-day autonomy storage with mixer and level control",
        sizing_basis="3 × peak daily volume (~36 m³ for 12 m³/day)",
        owner_serviceable=False,
        winterization_required=True,
        notes="High-high level interlock stops receiving",
    ),
    EquipmentItem(
        tag="MX-101",
        name="EQ Tank Mixer",
        subsystem=Subsystem.STORAGE,
        description="Submersible or top-entry mixer to prevent settling",
        sizing_basis="0.01-0.02 kW/m³ tank volume",
        owner_serviceable=True,
    ),
    EquipmentItem(
        tag="TK-102",
        name="Off-Spec Tank",
        subsystem=Subsystem.STORAGE,
        description="Holds rejected/suspect loads separately",
        sizing_basis="Minimum 1 truck load (12 m³)",
        owner_serviceable=False,
        notes="MANDATORY - one bad load without this = total downtime",
    ),
    
    # --- Dewatering ---
    EquipmentItem(
        tag="DW-101",
        name="Dewatering Unit",
        subsystem=Subsystem.DEWATERING,
        description="Screw press (preferred for serviceability) or small centrifuge",
        sizing_basis="Daily cake production requirement",
        owner_serviceable=True,
        notes="Screw press: seals, bearings, screen are owner-replaceable",
    ),
    EquipmentItem(
        tag="TK-103",
        name="Polymer Tote Containment",
        subsystem=Subsystem.DEWATERING,
        description="110% volume containment for polymer tote storage",
        sizing_basis="1-2 totes (1000L each)",
        owner_serviceable=True,
    ),
    EquipmentItem(
        tag="TK-104",
        name="Polymer Day Tank",
        subsystem=Subsystem.DEWATERING,
        description="Make-down tank for diluted polymer",
        sizing_basis="1 day polymer consumption",
        owner_serviceable=True,
    ),
    EquipmentItem(
        tag="P-102",
        name="Polymer Dosing Pump",
        subsystem=Subsystem.DEWATERING,
        description="Metering pump for polymer injection",
        sizing_basis="Polymer dose rate (5 kg/tDS typical)",
        owner_serviceable=True,
    ),
    EquipmentItem(
        tag="TK-105",
        name="Centrate Tank",
        subsystem=Subsystem.DEWATERING,
        description="Holds centrate for haul-off with quick-connect and sampling port",
        sizing_basis="3-day centrate accumulation (haul-off schedule)",
        owner_serviceable=True,
        winterization_required=True,
        notes="Quick-connect for vacuum truck pickup",
    ),
    
    # --- Cake Handling ---
    EquipmentItem(
        tag="HP-101",
        name="Cake Hopper",
        subsystem=Subsystem.CAKE_HANDLING,
        description="Live-bottom hopper receiving dewatered cake",
        sizing_basis="48-hour cake buffer (per model)",
        owner_serviceable=True,
    ),
    EquipmentItem(
        tag="CV-101",
        name="Cake Metering Screw",
        subsystem=Subsystem.CAKE_HANDLING,
        description="Variable speed screw conveyor to pyrolysis feed",
        sizing_basis="Max pyrolysis feed rate + 20% margin",
        owner_serviceable=True,
        notes="Cleanout ports accessible without tools",
    ),
    EquipmentItem(
        tag="CV-102",
        name="Co-feed Blending Screw",
        subsystem=Subsystem.CAKE_HANDLING,
        description="Blends co-feed with cake for reactor feed",
        sizing_basis="Combined cake + co-feed rate",
        owner_serviceable=True,
        notes="Bypass routing for dry co-feed direct to reactor",
    ),
    
    # --- Pyrolysis Island ---
    EquipmentItem(
        tag="PY-101",
        name="Pyrolysis Reactor Skid",
        subsystem=Subsystem.PYROLYSIS,
        description="Complete reactor package: feed airlock, reactor, char discharge",
        sizing_basis="Design throughput (kgDS/hr) per vendor",
        owner_serviceable=False,
        notes="Includes temperature control, char cooling section",
    ),
    EquipmentItem(
        tag="CY-101",
        name="Syngas Cyclone",
        subsystem=Subsystem.PYROLYSIS,
        description="Particulate removal from syngas stream",
        sizing_basis="Syngas volumetric flow rate",
        owner_serviceable=True,
    ),
    EquipmentItem(
        tag="FL-101",
        name="Flare/Burner",
        subsystem=Subsystem.PYROLYSIS,
        description="Syngas combustion with heat recovery option",
        sizing_basis="Peak syngas production rate",
        owner_serviceable=False,
    ),
    EquipmentItem(
        tag="HX-101",
        name="Heat Recovery Exchanger",
        subsystem=Subsystem.PYROLYSIS,
        description="Recovers heat from flue gas to dryer or preheat",
        sizing_basis="Dryer thermal demand",
        owner_serviceable=True,
    ),
    EquipmentItem(
        tag="PNL-101",
        name="Pyrolysis Control Panel",
        subsystem=Subsystem.PYROLYSIS,
        description="E-stops, LEL/O2 sensors, automated safe-shutdown logic",
        sizing_basis="Per vendor safety requirements",
        owner_serviceable=False,
        notes="Remote alarm capability required",
    ),
    
    # --- Char Handling ---
    EquipmentItem(
        tag="BN-101",
        name="Char Storage Bin",
        subsystem=Subsystem.CHAR_HANDLING,
        description="Metal bin with lid, receives cooled char",
        sizing_basis="14-day char production (per model autonomy)",
        owner_serviceable=True,
        notes="Char can reignite - must be cooled and covered",
    ),
    EquipmentItem(
        tag="BG-101",
        name="Bagging Station",
        subsystem=Subsystem.CHAR_HANDLING,
        description="Bulk bag filling station for char load-out",
        sizing_basis="Char production rate",
        owner_serviceable=True,
        notes="Optional if char sold in bulk bins",
    ),
    
    # --- Utilities ---
    EquipmentItem(
        tag="PWR-101",
        name="Electrical Service",
        subsystem=Subsystem.UTILITIES,
        description="Main electrical service sized for all equipment",
        sizing_basis="Sum of connected loads + 20% margin",
        owner_serviceable=False,
    ),
    EquipmentItem(
        tag="WTR-101",
        name="Washdown Water System",
        subsystem=Subsystem.UTILITIES,
        description="Water supply for equipment and area washdown",
        sizing_basis="Peak washdown demand + freeze protection",
        owner_serviceable=True,
        winterization_required=True,
    ),
    EquipmentItem(
        tag="CNT-101",
        name="Secondary Containment",
        subsystem=Subsystem.UTILITIES,
        description="Berms/curbs for spill containment",
        sizing_basis="110% of largest tank volume",
        owner_serviceable=False,
        notes="All receiving/storage areas drain to process, not storm",
    ),
]


# =============================================================================
# Hub Mode Equipment List
# =============================================================================

HUB_MODE_EQUIPMENT: List[EquipmentItem] = [
    # --- Receiving & Traffic (hub-specific) ---
    EquipmentItem(
        tag="RCV-201",
        name="Truck Receiving Bay",
        subsystem=Subsystem.RECEIVING,
        description="Covered receiving bay with defined truck route and turning radius",
        sizing_basis="12-15 trucks/day, 8-hour window",
        owner_serviceable=False,
        notes="Must include spill containment, washdown, queueing space",
    ),
    EquipmentItem(
        tag="SCR-201",
        name="Rotary Drum Screen",
        subsystem=Subsystem.RECEIVING,
        description="Continuous screening for high-volume receiving",
        sizing_basis="Peak receiving rate (15 trucks × 12 m³ / 8 hr = 22.5 m³/hr)",
        owner_serviceable=True,
    ),
    EquipmentItem(
        tag="GRT-201",
        name="Grit Classifier",
        subsystem=Subsystem.RECEIVING,
        description="Grit removal with classifier for continuous operation",
        sizing_basis="Peak septage flow rate",
        owner_serviceable=True,
    ),
    EquipmentItem(
        tag="FOG-201",
        name="Grease Trap/Skimmer",
        subsystem=Subsystem.RECEIVING,
        description="FOG removal if grease loads are significant",
        sizing_basis="Based on FOG loading analysis",
        owner_serviceable=True,
        notes="Optional but recommended for hub-scale receiving",
    ),
    
    # --- Storage (hub-scale) ---
    EquipmentItem(
        tag="TK-201A",
        name="Equalization Tank A",
        subsystem=Subsystem.STORAGE,
        description="Primary EQ tank with mixer, level control",
        sizing_basis="3-day autonomy (150 m³ for 50 m³/day)",
        owner_serviceable=False,
        winterization_required=True,
    ),
    EquipmentItem(
        tag="TK-201B",
        name="Equalization Tank B",
        subsystem=Subsystem.STORAGE,
        description="Standby/cleanout EQ tank (2-tank philosophy)",
        sizing_basis="Same as Tank A",
        owner_serviceable=False,
        winterization_required=True,
        notes="2-tank setup allows cleanout without stopping operations",
    ),
    EquipmentItem(
        tag="TK-202",
        name="Off-Spec Holding Tank",
        subsystem=Subsystem.STORAGE,
        description="Holds rejected/suspect loads",
        sizing_basis="Minimum 1 truck (12 m³), recommend 2 trucks (24 m³)",
        owner_serviceable=False,
    ),
    EquipmentItem(
        tag="TK-203",
        name="Centrate Storage Tank",
        subsystem=Subsystem.STORAGE,
        description="Sized for weekend + downtime accumulation",
        sizing_basis="(Weekend + buffer) × daily centrate production",
        owner_serviceable=False,
        winterization_required=True,
        notes="Discharge only Mon-Fri 08:00-16:00 per permit",
    ),
    EquipmentItem(
        tag="TK-204",
        name="Condensate Tank",
        subsystem=Subsystem.STORAGE,
        description="Segregated storage for pyrolysis condensate",
        sizing_basis="Condensate production × haul-off interval",
        owner_serviceable=False,
        notes="Condensate chemistry differs from centrate - keep separate",
    ),
    
    # --- Dewatering (hub-scale) ---
    EquipmentItem(
        tag="DW-201",
        name="Dewatering Centrifuge",
        subsystem=Subsystem.DEWATERING,
        description="Centrifuge for hub-scale throughput",
        sizing_basis="Daily cake production at hub volume",
        owner_serviceable=False,
        notes="Centrifuge often preferred at hub scale for throughput",
    ),
    EquipmentItem(
        tag="TK-205",
        name="Polymer Bulk Storage",
        subsystem=Subsystem.DEWATERING,
        description="Mini-bulk or multiple totes with containment",
        sizing_basis="2-4 weeks polymer consumption",
        owner_serviceable=True,
    ),
    EquipmentItem(
        tag="HP-201",
        name="Cake Buffer Hopper",
        subsystem=Subsystem.CAKE_HANDLING,
        description="1-day cake buffer so dewatering doesn't stop if pyro pauses",
        sizing_basis="24-hour cake production",
        owner_serviceable=True,
        notes="Critical for hub: decouples dewatering from pyrolysis",
    ),
    
    # --- Pyrolysis (hub-scale, night-mode capable) ---
    EquipmentItem(
        tag="PY-201",
        name="Pyrolysis Reactor Skid (Night-Mode)",
        subsystem=Subsystem.PYROLYSIS,
        description="Reactor with explicit overnight hold capability",
        sizing_basis="Hub throughput (kgDS/hr)",
        owner_serviceable=False,
        notes="MUST support: safe hold, purge logic, auto-shutdown",
    ),
    EquipmentItem(
        tag="PNL-201",
        name="Hub Control System",
        subsystem=Subsystem.PYROLYSIS,
        description="PLC with remote monitoring, alarm escalation",
        sizing_basis="All monitored points + alarm logic",
        owner_serviceable=False,
        notes="Remote notification to on-call required",
    ),
    
    # --- Compliance & Monitoring ---
    EquipmentItem(
        tag="SMP-201",
        name="Centrate Sampling Chamber",
        subsystem=Subsystem.COMPLIANCE,
        description="Sampling port for permit compliance",
        sizing_basis="Per permit sampling requirements",
        owner_serviceable=True,
    ),
    EquipmentItem(
        tag="SMP-202",
        name="Offgas Sampling Port",
        subsystem=Subsystem.COMPLIANCE,
        description="Sampling port for stack testing if required",
        sizing_basis="Per air permit requirements",
        owner_serviceable=False,
    ),
    EquipmentItem(
        tag="FLW-201",
        name="Receiving Flow Totalizer",
        subsystem=Subsystem.COMPLIANCE,
        description="Logs total septage received",
        sizing_basis="Max receiving rate",
        owner_serviceable=True,
    ),
    EquipmentItem(
        tag="FLW-202",
        name="Discharge Flow Totalizer",
        subsystem=Subsystem.COMPLIANCE,
        description="Logs centrate discharge for permit reporting",
        sizing_basis="Permit discharge rate",
        owner_serviceable=True,
    ),
    
    # --- Site Systems ---
    EquipmentItem(
        tag="ODR-201",
        name="Odour Control System",
        subsystem=Subsystem.SITE_SYSTEMS,
        description="Local exhaust at receiving + carbon/biofilter treatment",
        sizing_basis="Air changes at receiving bay",
        owner_serviceable=True,
        notes="Hub odour control is not optional - neighbors exist",
    ),
    EquipmentItem(
        tag="SWM-201",
        name="Stormwater Management",
        subsystem=Subsystem.SITE_SYSTEMS,
        description="Segregated clean/dirty areas, dirty pad containment",
        sizing_basis="Design storm + dirty area runoff",
        owner_serviceable=False,
    ),
    EquipmentItem(
        tag="HT-201",
        name="Heat Tracing System",
        subsystem=Subsystem.SITE_SYSTEMS,
        description="Freeze protection for exposed lines and pumps",
        sizing_basis="All exposed liquid lines",
        owner_serviceable=True,
        winterization_required=True,
    ),
]


# =============================================================================
# Best Practices Registry
# =============================================================================

BEST_PRACTICES: List[BestPractice] = [
    BestPractice(
        id="BP-001",
        subsystem=Subsystem.RECEIVING,
        requirement="Curbed containment pad draining to process sump, not storm",
        rationale="Septage spills must not reach stormwater system",
        failure_if_skipped="Environmental violation on first spill",
    ),
    BestPractice(
        id="BP-002",
        subsystem=Subsystem.STORAGE,
        requirement="Dedicated off-spec tank for rejected loads",
        rationale="One bad load without diversion = total process upset",
        failure_if_skipped="Dewatering/pyrolysis poisoned by oil, chemicals, or trash",
    ),
    BestPractice(
        id="BP-003",
        subsystem=Subsystem.STORAGE,
        requirement="High-high level interlock stops receiving",
        rationale="Overfill creates uncontrolled spill",
        failure_if_skipped="Tank overflow, environmental release",
    ),
    BestPractice(
        id="BP-004",
        subsystem=Subsystem.RECEIVING,
        requirement="Hub: Real traffic planning - routing, queueing, turning radius",
        rationale="12-15 trucks/day cannot self-organize",
        failure_if_skipped="Truck conflicts, blocked access, unsafe operations",
    ),
    BestPractice(
        id="BP-005",
        subsystem=Subsystem.PYROLYSIS,
        requirement="Hub: Explicit night-mode definition (hold/cooldown/shutdown)",
        rationale="Reactor must remain stable 16+ hours without operators",
        failure_if_skipped="Unsafe condition, potential fire/explosion",
    ),
    BestPractice(
        id="BP-006",
        subsystem=Subsystem.PYROLYSIS,
        requirement="Remote alarm escalation with defined call chain",
        rationale="Critical alarms overnight need human response",
        failure_if_skipped="Undetected failure, extended damage",
    ),
    BestPractice(
        id="BP-007",
        subsystem=Subsystem.CHAR_HANDLING,
        requirement="Char cooled before storage, metal bins with lids",
        rationale="Hot char can reignite; smouldering is a fire hazard",
        failure_if_skipped="Char fire in storage",
    ),
    BestPractice(
        id="BP-008",
        subsystem=Subsystem.STORAGE,
        requirement="Centrate storage sized for weekend + downtime (hub)",
        rationale="Discharge only Mon-Fri 08:00-16:00 per permit",
        failure_if_skipped="Forced shutdown or permit violation",
    ),
    BestPractice(
        id="BP-009",
        subsystem=Subsystem.UTILITIES,
        requirement="Winterization: heat tracing, insulated tanks, freeze protection",
        rationale="Northern Ontario freezes; unprotected lines fail",
        failure_if_skipped="Frozen lines, pump damage, winter shutdown",
    ),
    BestPractice(
        id="BP-010",
        subsystem=Subsystem.DEWATERING,
        requirement="Polymer tote containment (110% volume)",
        rationale="Polymer spills are slippery and regulatory issue",
        failure_if_skipped="Slip hazard, cleanup cost, violation",
    ),
    BestPractice(
        id="BP-011",
        subsystem=Subsystem.CAKE_HANDLING,
        requirement="Cake buffer hopper (hub: 24hr; product: 48hr)",
        rationale="Decouples dewatering from pyrolysis; prevents forced stops",
        failure_if_skipped="Pyrolysis trip = immediate dewatering stop",
    ),
    BestPractice(
        id="BP-012",
        subsystem=Subsystem.SITE_SYSTEMS,
        requirement="Hub: Odour control at receiving (local exhaust + treatment)",
        rationale="Hubs have neighbors; odour complaints = permit risk",
        failure_if_skipped="Complaints, enforcement, shutdown order",
    ),
]


# =============================================================================
# Operating Mode Specifications
# =============================================================================

@dataclass(frozen=True)
class OperatingModeStep:
    """A single step in an operating mode sequence."""
    sequence: int
    action: str
    responsible: str
    verification: Optional[str] = None
    notes: Optional[str] = None


@dataclass(frozen=True)
class OperatingModeSpec:
    """Complete specification for an operating mode."""
    mode: DeploymentMode
    phase: OperatingPhase
    description: str
    steps: Tuple[OperatingModeStep, ...]
    duration_typical: Optional[str] = None
    triggers: Optional[Tuple[str, ...]] = None
    safe_state_if_failed: Optional[str] = None


# --- Product Mode Operating Modes ---

PRODUCT_NORMAL_DAY = OperatingModeSpec(
    mode=DeploymentMode.PRODUCT,
    phase=OperatingPhase.NORMAL_DAY,
    description="Normal daily operation (1-3 trucks, owner schedule)",
    duration_typical="8-12 hours (flexible)",
    steps=(
        OperatingModeStep(1, "Receive 1-3 septage loads", "operator"),
        OperatingModeStep(2, "Screen/grit removal runs with receiving", "auto"),
        OperatingModeStep(3, "Fill EQ tank, mixer runs continuously", "auto"),
        OperatingModeStep(4, "Dewater in batches per cake demand", "operator"),
        OperatingModeStep(5, "Feed pyrolysis skid as cake available", "auto"),
        OperatingModeStep(6, "Load-out char to bins/bags", "operator"),
        OperatingModeStep(7, "Schedule centrate haul-off (weekly typical)", "operator"),
    ),
)

PRODUCT_STARTUP = OperatingModeSpec(
    mode=DeploymentMode.PRODUCT,
    phase=OperatingPhase.STARTUP,
    description="Daily startup sequence",
    duration_typical="30-60 minutes",
    steps=(
        OperatingModeStep(1, "Verify tank levels (EQ, centrate, polymer)", "operator"),
        OperatingModeStep(2, "Check polymer day tank, refill if needed", "operator"),
        OperatingModeStep(3, "Verify cake hopper level", "operator"),
        OperatingModeStep(4, "Warm pyrolysis skid if cold", "operator", 
                         notes="Per vendor startup procedure"),
        OperatingModeStep(5, "Ramp feed gradually (avoid tar/plugging)", "operator"),
        OperatingModeStep(6, "Verify flare/burner stable", "operator"),
    ),
)

PRODUCT_SHUTDOWN = OperatingModeSpec(
    mode=DeploymentMode.PRODUCT,
    phase=OperatingPhase.SHUTDOWN,
    description="End-of-day or extended shutdown",
    duration_typical="30-60 minutes",
    steps=(
        OperatingModeStep(1, "Stop receiving (secure discharge station)", "operator"),
        OperatingModeStep(2, "Run dewatering until cake hopper at target", "operator"),
        OperatingModeStep(3, "Clear feed screws (run empty)", "operator"),
        OperatingModeStep(4, "Place pyrolysis skid into safe state", "operator",
                         notes="Per vendor shutdown procedure"),
        OperatingModeStep(5, "Secure char bins (lids closed)", "operator"),
        OperatingModeStep(6, "Final walkthrough, secure site", "operator"),
    ),
)

PRODUCT_FAILURE_HANDLING = OperatingModeSpec(
    mode=DeploymentMode.PRODUCT,
    phase=OperatingPhase.FAILURE_HANDLING,
    description="Response to upset conditions",
    steps=(
        OperatingModeStep(1, "Off-spec load detected → divert to off-spec tank", "operator",
                         verification="Load does not enter EQ"),
        OperatingModeStep(2, "Dewatering upset → hold in EQ, adjust polymer dose", "operator",
                         verification="Cake TS returns to target"),
        OperatingModeStep(3, "Pyrolysis trip → cake to buffer hopper, stop dewatering", "auto",
                         verification="Feed stops, reactor enters safe state"),
        OperatingModeStep(4, "Investigate root cause before restart", "operator"),
    ),
    safe_state_if_failed="Pyrolysis in vendor-defined safe state, dewatering stopped, receiving stopped",
)


# --- Hub Mode Operating Modes ---

HUB_NORMAL_DAY = OperatingModeSpec(
    mode=DeploymentMode.HUB,
    phase=OperatingPhase.NORMAL_DAY,
    description="Normal day shift (08:00-16:00)",
    duration_typical="8 hours",
    steps=(
        OperatingModeStep(1, "Receiving active: 12-15 trucks, screening continuous", "operator"),
        OperatingModeStep(2, "Dewatering runs continuously to maintain cake buffer", "auto"),
        OperatingModeStep(3, "Centrate discharge active (08:00-16:00 permit window)", "auto"),
        OperatingModeStep(4, "Pyrolysis runs to consume cake + co-feed", "auto"),
        OperatingModeStep(5, "Monitor alarms, tank levels, process parameters", "operator"),
        OperatingModeStep(6, "Log receiving volumes, handle off-spec loads", "operator"),
    ),
)

HUB_END_OF_DAY = OperatingModeSpec(
    mode=DeploymentMode.HUB,
    phase=OperatingPhase.END_OF_DAY,
    description="Mandatory end-of-day sequence (16:00)",
    duration_typical="30-45 minutes",
    triggers=("Clock reaches 16:00", "All trucks departed"),
    steps=(
        OperatingModeStep(1, "Stop receiving (close receiving bay)", "operator"),
        OperatingModeStep(2, "Verify cake buffer within safe band", "operator",
                         verification="Cake hopper level 40-80%"),
        OperatingModeStep(3, "Enter reactor overnight mode (per vendor)", "operator",
                         notes="Hot hold, controlled cooldown, or inert purge"),
        OperatingModeStep(4, "Confirm centrate tank has capacity for overnight", "operator",
                         verification="Level < 70% for weekend, < 85% weekday"),
        OperatingModeStep(5, "Arm alarms and verify remote notification active", "operator",
                         verification="Test alarm acknowledgement"),
        OperatingModeStep(6, "Final walkthrough, secure facility", "operator"),
    ),
)

HUB_OVERNIGHT = OperatingModeSpec(
    mode=DeploymentMode.HUB,
    phase=OperatingPhase.OVERNIGHT,
    description="Unattended overnight operation (16:00-08:00)",
    duration_typical="16 hours",
    steps=(
        OperatingModeStep(1, "No operators on site", "auto"),
        OperatingModeStep(2, "Reactor maintains overnight mode (hot hold or cooldown)", "auto"),
        OperatingModeStep(3, "Critical alarms trigger remote notification", "auto",
                         notes="Temperature deviation, pressure, O2 ingress, flame fault"),
        OperatingModeStep(4, "Auto-shutdown if critical parameter exceeded", "auto"),
    ),
    triggers=("Critical alarm thresholds defined per vendor",),
    safe_state_if_failed="Feed stopped, reactor purged, flare off, alarms escalated",
)

HUB_MORNING_RESTART = OperatingModeSpec(
    mode=DeploymentMode.HUB,
    phase=OperatingPhase.MORNING_RESTART,
    description="Morning restart sequence (08:00)",
    duration_typical="30-60 minutes (hot hold) to 2-4 hours (cold)",
    steps=(
        OperatingModeStep(1, "System health check (alarms, levels, temperatures)", "operator"),
        OperatingModeStep(2, "Check overnight logs for anomalies", "operator"),
        OperatingModeStep(3, "Restart pyrolysis per vendor procedure", "operator",
                         notes="Time depends on overnight mode: hot=fast, cold=slow"),
        OperatingModeStep(4, "Resume dewatering when pyrolysis stable", "operator"),
        OperatingModeStep(5, "Open receiving when system ready", "operator"),
        OperatingModeStep(6, "Start centrate discharge (08:00 permit window opens)", "auto"),
    ),
)

HUB_FAILURE_HANDLING = OperatingModeSpec(
    mode=DeploymentMode.HUB,
    phase=OperatingPhase.FAILURE_HANDLING,
    description="Response to upset conditions (hub-specific)",
    steps=(
        OperatingModeStep(1, "Off-spec load → divert to TK-202, log and notify", "operator"),
        OperatingModeStep(2, "Dewatering upset → adjust polymer, slow receiving if needed", "operator"),
        OperatingModeStep(3, "Pyrolysis trip during day → stop receiving, investigate", "operator"),
        OperatingModeStep(4, "Pyrolysis alarm overnight → auto-shutdown, remote notification", "auto"),
        OperatingModeStep(5, "On-call responds per escalation procedure", "operator",
                         notes="Gate access, isolation procedures documented"),
    ),
    safe_state_if_failed="Pyrolysis shutdown and purged, receiving closed, centrate held",
)


# =============================================================================
# Site Concept Gates
# =============================================================================

@dataclass(frozen=True)
class SiteConceptGate:
    """A gate that must be passed for the concept to be buildable."""
    id: str
    name: str
    question: str
    applies_to: Tuple[DeploymentMode, ...]
    failure_consequence: str


SITE_CONCEPT_GATES: List[SiteConceptGate] = [
    SiteConceptGate(
        id="GATE-01",
        name="Logistics",
        question="Hub: Is truck routing, queueing, washdown, and containment proven? "
                 "Product: Can the truck connect, dump, and leave safely year-round?",
        applies_to=(DeploymentMode.PRODUCT, DeploymentMode.HUB),
        failure_consequence="Operational chaos, access conflicts, winter failures",
    ),
    SiteConceptGate(
        id="GATE-02",
        name="Off-Spec Management",
        question="Is there a separate off-spec tank and decision logic?",
        applies_to=(DeploymentMode.PRODUCT, DeploymentMode.HUB),
        failure_consequence="One bad load contaminates EQ → total process upset",
    ),
    SiteConceptGate(
        id="GATE-03",
        name="Storage Sizing",
        question="Is EQ sized for autonomy (3 days)? Is centrate storage sized "
                 "for discharge/haul schedule (especially weekends)?",
        applies_to=(DeploymentMode.PRODUCT, DeploymentMode.HUB),
        failure_consequence="Forced shutdown due to full tanks",
    ),
    SiteConceptGate(
        id="GATE-04",
        name="Unattended Safety",
        question="Hub: Is safe state defined? Hold mode, purge, auto-shutdown? "
                 "Is there a remote alarm escalation chain?",
        applies_to=(DeploymentMode.HUB,),
        failure_consequence="Unsafe overnight condition, potential fire/explosion",
    ),
    SiteConceptGate(
        id="GATE-05",
        name="Winterization",
        question="Is freeze protection specified for lines, pumps, tanks, washdown? "
                 "Is snow storage and truck access planned?",
        applies_to=(DeploymentMode.PRODUCT, DeploymentMode.HUB),
        failure_consequence="Winter shutdown, frozen damage",
    ),
    SiteConceptGate(
        id="GATE-06",
        name="Maintenance Access",
        question="Can wear parts (screws, seals, bearings, screens) be removed/replaced "
                 "without special tools or cranes?",
        applies_to=(DeploymentMode.PRODUCT, DeploymentMode.HUB),
        failure_consequence="Extended downtime for simple repairs",
    ),
    SiteConceptGate(
        id="GATE-07",
        name="Sampling Plan",
        question="Are sample points located for each regulated stream "
                 "(centrate, char, emissions)? Is frequency and chain-of-custody defined?",
        applies_to=(DeploymentMode.PRODUCT, DeploymentMode.HUB),
        failure_consequence="Cannot prove compliance, permit violations",
    ),
    SiteConceptGate(
        id="GATE-08",
        name="Odour Control",
        question="Hub: Is receiving covered with local exhaust to treatment? "
                 "Product: Is receiving area ventilated?",
        applies_to=(DeploymentMode.PRODUCT, DeploymentMode.HUB),
        failure_consequence="Complaints, enforcement action",
    ),
]


# =============================================================================
# Design Gaps Tracker
# =============================================================================

@dataclass
class DesignGap:
    """A known gap between model and buildable facility."""
    id: str
    category: str
    description: str
    current_state: str
    required_for_buildable: str
    priority: Literal["critical", "high", "medium", "low"]
    resolution_path: str


KNOWN_DESIGN_GAPS: List[DesignGap] = [
    DesignGap(
        id="GAP-001",
        category="Logistics",
        description="Truck pad design and traffic flow",
        current_state="Not modeled",
        required_for_buildable="GA drawing with turning radii, queue space, washdown",
        priority="high",
        resolution_path="Site layout study or reference design",
    ),
    DesignGap(
        id="GAP-002",
        category="Storage",
        description="Off-spec tank and diversion logic",
        current_state="RESOLVED: OffSpecParams in parameters.py with triggers, thresholds, hold time",
        required_for_buildable="TK-102/TK-202 sized and logic defined",
        priority="medium",  # Downgraded from critical - now implemented
        resolution_path="OffSpecParams dataclass integrated into ModelParameters",
    ),
    DesignGap(
        id="GAP-003",
        category="Centrate",
        description="Product mode centrate haul-off logistics",
        current_state="Model assumes discharge; haul-off not parameterized",
        required_for_buildable="Haul frequency, tank size, connector spec",
        priority="high",
        resolution_path="Add CentrateDisposition enum and haul-off parameters",
    ),
    DesignGap(
        id="GAP-004",
        category="Night Mode",
        description="Explicit overnight sequences and triggers",
        current_state="Placeholder implemented with DRL-4 blocking. Awaiting ≥2 consistent vendor responses.",
        required_for_buildable="VendorOvernightData from ≥2 vendors → validate_overnight_responses()",
        priority="critical",
        resolution_path="Parse vendor responses → VendorOvernightData → validate_overnight_responses(policy) → OvernightModeParams",
    ),
    DesignGap(
        id="GAP-005",
        category="Serviceability",
        description="Maintenance access and MTTR assumptions",
        current_state="Not modeled",
        required_for_buildable="Part list with owner-serviceable flag, MTTR estimates",
        priority="medium",
        resolution_path="Equipment list with serviceability tags (this module)",
    ),
    DesignGap(
        id="GAP-006",
        category="Compliance",
        description="Sampling plan and chain-of-custody",
        current_state="Sample points mentioned but not specified",
        required_for_buildable="Sample point locations, frequency, analytes, CoC protocol",
        priority="medium",
        resolution_path="Compliance sampling spec document",
    ),
    DesignGap(
        id="GAP-007",
        category="Odour",
        description="Odour control strategy",
        current_state="Not modeled",
        required_for_buildable="Exhaust rates, treatment sizing, dispersion estimate",
        priority="high",
        resolution_path="Odour control basis of design",
    ),
]


# =============================================================================
# Utility Functions
# =============================================================================

def get_equipment_list(mode: DeploymentMode) -> List[EquipmentItem]:
    """Get canonical equipment list for deployment mode."""
    if mode == DeploymentMode.PRODUCT:
        return PRODUCT_MODE_EQUIPMENT
    else:
        return HUB_MODE_EQUIPMENT


def get_operating_modes(mode: DeploymentMode) -> List[OperatingModeSpec]:
    """Get all operating mode specs for deployment mode."""
    if mode == DeploymentMode.PRODUCT:
        return [PRODUCT_NORMAL_DAY, PRODUCT_STARTUP, PRODUCT_SHUTDOWN, PRODUCT_FAILURE_HANDLING]
    else:
        return [HUB_NORMAL_DAY, HUB_END_OF_DAY, HUB_OVERNIGHT, HUB_MORNING_RESTART, HUB_FAILURE_HANDLING]


def get_applicable_gates(mode: DeploymentMode) -> List[SiteConceptGate]:
    """Get gates that apply to a deployment mode."""
    return [g for g in SITE_CONCEPT_GATES if mode in g.applies_to]


def get_best_practices_by_subsystem(subsystem: Subsystem) -> List[BestPractice]:
    """Get best practices for a specific subsystem."""
    return [bp for bp in BEST_PRACTICES if bp.subsystem == subsystem]


def check_design_gaps(priority_filter: Optional[str] = None) -> List[DesignGap]:
    """Get known design gaps, optionally filtered by priority."""
    if priority_filter:
        return [g for g in KNOWN_DESIGN_GAPS if g.priority == priority_filter]
    return KNOWN_DESIGN_GAPS


# =============================================================================
# GATE-04 Programmatic Enforcement (Unattended Safety)
# =============================================================================

@dataclass
class GateCheckResult:
    """Result from a site concept gate check."""
    gate_id: str
    gate_name: str
    passed: bool
    details: str
    remediation: Optional[str] = None


def check_gate04_unattended_safety(
    overnight_mode: str,
    overnight_status: str,
    shutdown_philosophy: str,
    claimed_drl: int,
    continuous_heat_required: bool = False,
) -> GateCheckResult:
    """Programmatic check for GATE-04: Unattended Safety.
    
    GATE-04 asks: "Is safe state defined? Hold mode, purge, auto-shutdown?
    Remote alarm escalation chain?"
    
    This function bridges the declarative GATE-04 definition in
    SITE_CONCEPT_GATES with the overnight mode validation pipeline.
    
    Hub-only gate (Product mode always passes — attended operation).
    
    Pass conditions:
        - DRL ≤ 3: Always passes (screening level, warn only)
        - DRL 4+: Requires VALIDATED overnight status AND
                   shutdown_philosophy != "unknown"
    
    Args:
        overnight_mode: OvernightMode value string (hold, controlled_cooldown, etc.)
        overnight_status: OvernightModeStatus value string (unknown, partial, validated)
        shutdown_philosophy: Vendor shutdown philosophy (alarm_only, auto_rampdown, etc.)
        claimed_drl: DRL level being claimed
        continuous_heat_required: Whether reactor needs continuous heat overnight
    
    Returns:
        GateCheckResult with pass/fail and remediation
    """
    gate = next(g for g in SITE_CONCEPT_GATES if g.id == "GATE-04")
    
    # DRL ≤ 3: screening level, warn but pass
    if claimed_drl <= 3:
        warnings = []
        if overnight_status == "unknown":
            warnings.append("overnight_mode unvalidated")
        if shutdown_philosophy == "unknown":
            warnings.append("shutdown_philosophy undefined")
        
        detail_msg = f"DRL-{claimed_drl} screening: GATE-04 advisory only"
        if warnings:
            detail_msg += f" (warnings: {', '.join(warnings)})"
        
        return GateCheckResult(
            gate_id="GATE-04",
            gate_name=gate.name,
            passed=True,
            details=detail_msg,
            remediation=None,
        )
    
    # DRL 4+: Hard requirements
    issues = []
    
    if overnight_status != "validated":
        issues.append(
            f"overnight_status={overnight_status}, require 'validated' "
            f"(≥2 consistent vendor responses)"
        )
    
    if shutdown_philosophy == "unknown":
        issues.append(
            "shutdown_philosophy is undefined — "
            "need vendor-specified safe shutdown sequence"
        )
    
    if overnight_mode == "unknown":
        issues.append(
            "overnight_mode is undefined — "
            "cannot prove unattended safe state"
        )
    
    if continuous_heat_required and shutdown_philosophy not in (
        "auto_rampdown", "auto_shutdown", "hybrid"
    ):
        issues.append(
            f"continuous_heat_required=True but shutdown_philosophy='{shutdown_philosophy}' "
            f"does not provide automatic safe-state transition"
        )
    
    passed = len(issues) == 0
    
    remediation = None
    if not passed:
        remediation = (
            f"GATE-04 BLOCKED at DRL-{claimed_drl}: {gate.failure_consequence}. "
            f"Issues: {'; '.join(issues)}. "
            f"Resolution: {gate.question}"
        )
    
    return GateCheckResult(
        gate_id="GATE-04",
        gate_name=gate.name,
        passed=passed,
        details=f"DRL-{claimed_drl} check: {len(issues)} issue(s)",
        remediation=remediation,
    )


def check_site_concept_gates_programmatic(
    mode: DeploymentMode,
    claimed_drl: int,
    overnight_mode: str = "unknown",
    overnight_status: str = "unknown",
    shutdown_philosophy: str = "unknown",
    continuous_heat_required: bool = False,
) -> List[GateCheckResult]:
    """Run all programmatically-checkable site concept gates.
    
    Currently only GATE-04 (Unattended Safety) has programmatic enforcement.
    Other gates remain declarative checklists awaiting human input.
    
    Args:
        mode: Deployment mode (PRODUCT or HUB)
        claimed_drl: DRL level being claimed
        overnight_mode: OvernightMode value string
        overnight_status: OvernightModeStatus value string
        shutdown_philosophy: Vendor shutdown philosophy
        continuous_heat_required: Whether reactor needs continuous heat overnight
    
    Returns:
        List of GateCheckResult for all applicable programmatic gates
    """
    results = []
    applicable = get_applicable_gates(mode)
    
    for gate in applicable:
        if gate.id == "GATE-04":
            results.append(check_gate04_unattended_safety(
                overnight_mode=overnight_mode,
                overnight_status=overnight_status,
                shutdown_philosophy=shutdown_philosophy,
                claimed_drl=claimed_drl,
                continuous_heat_required=continuous_heat_required,
            ))
        # Other gates remain declarative — no programmatic check yet
    
    return results


def generate_equipment_summary(mode: DeploymentMode) -> str:
    """Generate markdown summary of equipment for a mode."""
    equipment = get_equipment_list(mode)
    lines = [f"# Equipment List: {mode.value.title()} Mode\n"]
    
    by_subsystem: Dict[Subsystem, List[EquipmentItem]] = {}
    for item in equipment:
        if item.subsystem not in by_subsystem:
            by_subsystem[item.subsystem] = []
        by_subsystem[item.subsystem].append(item)
    
    for subsystem in Subsystem:
        if subsystem in by_subsystem:
            lines.append(f"\n## {subsystem.value.replace('_', ' ').title()}\n")
            lines.append("| Tag | Name | Sizing Basis | Owner Svc | Winter |")
            lines.append("|-----|------|--------------|-----------|--------|")
            for item in by_subsystem[subsystem]:
                winter = "✓" if item.winterization_required else ""
                service = "✓" if item.owner_serviceable else ""
                lines.append(f"| {item.tag} | {item.name} | {item.sizing_basis} | {service} | {winter} |")
    
    return "\n".join(lines)


def generate_operating_mode_summary(mode: DeploymentMode) -> str:
    """Generate markdown summary of operating modes."""
    modes = get_operating_modes(mode)
    lines = [f"# Operating Modes: {mode.value.title()} Mode\n"]
    
    for op_mode in modes:
        lines.append(f"\n## {op_mode.phase.value.replace('_', ' ').title()}\n")
        lines.append(f"**Description:** {op_mode.description}\n")
        if op_mode.duration_typical:
            lines.append(f"**Duration:** {op_mode.duration_typical}\n")
        
        lines.append("\n| # | Action | Responsible | Notes |")
        lines.append("|---|--------|-------------|-------|")
        for step in op_mode.steps:
            notes = step.notes or step.verification or ""
            lines.append(f"| {step.sequence} | {step.action} | {step.responsible} | {notes} |")
        
        if op_mode.safe_state_if_failed:
            lines.append(f"\n**Safe State:** {op_mode.safe_state_if_failed}")
    
    return "\n".join(lines)


# =============================================================================
# CLI Entry Point
# =============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m septage_model.artifacts.facility_design <command>")
        print()
        print("Commands:")
        print("  equipment-product    Print product mode equipment list")
        print("  equipment-hub        Print hub mode equipment list")
        print("  modes-product        Print product mode operating modes")
        print("  modes-hub            Print hub mode operating modes")
        print("  gates                Print site concept gates")
        print("  gaps                 Print known design gaps")
        print("  best-practices       Print all best practices")
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "equipment-product":
        print(generate_equipment_summary(DeploymentMode.PRODUCT))
    elif cmd == "equipment-hub":
        print(generate_equipment_summary(DeploymentMode.HUB))
    elif cmd == "modes-product":
        print(generate_operating_mode_summary(DeploymentMode.PRODUCT))
    elif cmd == "modes-hub":
        print(generate_operating_mode_summary(DeploymentMode.HUB))
    elif cmd == "gates":
        print("# Site Concept Gates\n")
        for gate in SITE_CONCEPT_GATES:
            modes = ", ".join(m.value for m in gate.applies_to)
            print(f"## {gate.id}: {gate.name} ({modes})")
            print(f"**Question:** {gate.question}")
            print(f"**If Failed:** {gate.failure_consequence}\n")
    elif cmd == "gaps":
        print("# Known Design Gaps\n")
        for gap in KNOWN_DESIGN_GAPS:
            print(f"## {gap.id}: {gap.description} [{gap.priority.upper()}]")
            print(f"- **Current:** {gap.current_state}")
            print(f"- **Required:** {gap.required_for_buildable}")
            print(f"- **Resolution:** {gap.resolution_path}\n")
    elif cmd == "best-practices":
        print("# Design Best Practices\n")
        for bp in BEST_PRACTICES:
            print(f"## {bp.id}: {bp.subsystem.value}")
            print(f"**Requirement:** {bp.requirement}")
            print(f"**Rationale:** {bp.rationale}")
            print(f"**If Skipped:** {bp.failure_if_skipped}\n")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
