"""
Facility Geometry Module - XYZ Bounding Box Layout System.

This module defines physical facility layouts using an XYZ coordinate system.
All equipment is represented as bounding boxes with clearance requirements.

Design Philosophy:
    - Physics ≠ Packaging (ReactorParams stays physics-only)
    - Fixed conservative envelopes until vendor cutsheets arrive
    - Layout reads only "envelope blocks", never kinetics directly
    - Gates enforce clearances, hot-zone exclusion, containment separation

Coordinate System:
    - Origin (0, 0, 0) at southwest interior corner of building, floor level
    - X = length (east-west), Y = width (north-south), Z = height
    - All dimensions in meters

Containment Philosophy:
    - Hub mode: MUST use separate containment (Rule C-1)
    - Product mode: MAY share slab, not sump (Rule C-2)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple
import sys


# =============================================================================
# Enums
# =============================================================================

class DeploymentMode(Enum):
    """Facility deployment mode."""
    PRODUCT = "product"
    HUB = "hub"


class Subsystem(Enum):
    """Facility subsystem categories."""
    RECEIVING = "receiving"
    EQ_STORAGE = "eq_storage"
    OFF_SPEC = "off_spec"
    DEWATERING = "dewatering"
    CENTRATE = "centrate"
    CAKE_HANDLING = "cake_handling"
    PYROLYSIS = "pyrolysis"
    CHAR_HANDLING = "char_handling"
    UTILITIES = "utilities"
    ACCESS = "access"


class ContainmentType(Enum):
    """Containment classification."""
    NONE = "none"
    SHARED_SLAB = "shared_slab"           # Product: shared slab, separate sump
    SEPARATE_BERM = "separate_berm"       # Hub: fully separate containment
    HOT_ZONE = "hot_zone"                 # Exclusion zone, not containment


class PullOutDirection(Enum):
    """Equipment maintenance pull-out direction."""
    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"
    VERTICAL = "vertical"
    NONE = "none"


# =============================================================================
# Core Geometry Dataclasses
# =============================================================================

@dataclass(frozen=True)
class BoundingBox:
    """3D bounding box with origin at southwest corner, floor level.
    
    All dimensions in meters.
    """
    x_min: float          # Southwest corner X
    y_min: float          # Southwest corner Y
    z_min: float          # Floor level (usually 0)
    length: float         # X dimension (east-west)
    width: float          # Y dimension (north-south)  
    height: float         # Z dimension (vertical)
    
    @property
    def x_max(self) -> float:
        return self.x_min + self.length
    
    @property
    def y_max(self) -> float:
        return self.y_min + self.width
    
    @property
    def z_max(self) -> float:
        return self.z_min + self.height
    
    @property
    def footprint_area(self) -> float:
        """Plan view area in m²."""
        return self.length * self.width
    
    @property
    def volume(self) -> float:
        """Bounding volume in m³."""
        return self.length * self.width * self.height
    
    @property
    def center(self) -> Tuple[float, float, float]:
        """Center point (x, y, z)."""
        return (
            self.x_min + self.length / 2,
            self.y_min + self.width / 2,
            self.z_min + self.height / 2,
        )
    
    def intersects_xy(self, other: "BoundingBox") -> bool:
        """Check if footprints overlap in plan view."""
        return not (
            self.x_max <= other.x_min or
            other.x_max <= self.x_min or
            self.y_max <= other.y_min or
            other.y_max <= self.y_min
        )
    
    def expand(self, margin: float) -> "BoundingBox":
        """Return new box expanded by margin on all sides."""
        return BoundingBox(
            x_min=self.x_min - margin,
            y_min=self.y_min - margin,
            z_min=self.z_min,
            length=self.length + 2 * margin,
            width=self.width + 2 * margin,
            height=self.height + margin,  # Only expand upward
        )
    
    def expand_directional(
        self,
        north: float = 0,
        south: float = 0,
        east: float = 0,
        west: float = 0,
        up: float = 0,
    ) -> "BoundingBox":
        """Return new box with directional expansion."""
        return BoundingBox(
            x_min=self.x_min - west,
            y_min=self.y_min - south,
            z_min=self.z_min,
            length=self.length + west + east,
            width=self.width + south + north,
            height=self.height + up,
        )


@dataclass(frozen=True)
class FacilityEnvelope:
    """Overall facility bounding envelope (the "XYZ cube")."""
    length_m: float       # X dimension
    width_m: float        # Y dimension
    height_m: float       # Z dimension (clear interior height)
    name: str = ""
    
    @property
    def footprint_area(self) -> float:
        return self.length_m * self.width_m
    
    @property
    def volume(self) -> float:
        return self.length_m * self.width_m * self.height_m
    
    def as_bounding_box(self) -> BoundingBox:
        """Return as BoundingBox with origin at (0, 0, 0)."""
        return BoundingBox(
            x_min=0, y_min=0, z_min=0,
            length=self.length_m,
            width=self.width_m,
            height=self.height_m,
        )


# =============================================================================
# Reactor Envelope (Layout-Only, Rule R-1)
# =============================================================================

@dataclass(frozen=True)
class ReactorEnvelopeParams:
    """Reactor skid envelope for layout purposes only.
    
    Rule R-1: Physics ≠ Packaging
        - ReactorParams (in parameters.py) = physics (D, L, kinetics, U, etc.)
        - ReactorEnvelopeParams = layout only (footprint, clearances)
    
    Rule R-2: Fixed conservative envelope until vendor cutsheets
        - Use default blocks now
        - Only switch after vendor validation via derive_envelope_from_vendor_cut_sheet()
    """
    # Skid footprint
    footprint_L_m: float        # Length (X direction)
    footprint_W_m: float        # Width (Y direction)
    height_m: float             # Total height including stack
    
    # Service clearances (required clear space)
    service_clearance_inlet_m: float
    service_clearance_outlet_m: float
    overhead_clearance_m: float
    
    # Hot zone exclusion (fire safety)
    hot_zone_exclusion_m: float
    
    # Metadata
    validated_by_vendor: bool = False
    vendor_id: Optional[str] = None
    
    def get_equipment_box(self, origin_x: float, origin_y: float) -> BoundingBox:
        """Return equipment bounding box at given origin."""
        return BoundingBox(
            x_min=origin_x,
            y_min=origin_y,
            z_min=0,
            length=self.footprint_L_m,
            width=self.footprint_W_m,
            height=self.height_m,
        )
    
    def get_service_envelope(self, origin_x: float, origin_y: float) -> BoundingBox:
        """Return expanded box including service clearances."""
        base = self.get_equipment_box(origin_x, origin_y)
        return base.expand_directional(
            west=self.service_clearance_inlet_m,
            east=self.service_clearance_outlet_m,
            up=self.overhead_clearance_m,
        )
    
    def get_hot_zone(self, origin_x: float, origin_y: float) -> BoundingBox:
        """Return hot zone exclusion envelope."""
        base = self.get_equipment_box(origin_x, origin_y)
        return base.expand(self.hot_zone_exclusion_m)


# Default conservative reactor envelopes (use until vendor data)
PRODUCT_REACTOR_ENVELOPE = ReactorEnvelopeParams(
    footprint_L_m=6.0,
    footprint_W_m=2.5,
    height_m=5.0,
    service_clearance_inlet_m=1.5,
    service_clearance_outlet_m=2.0,
    overhead_clearance_m=1.0,
    hot_zone_exclusion_m=1.5,
)

HUB_REACTOR_ENVELOPE = ReactorEnvelopeParams(
    footprint_L_m=9.0,
    footprint_W_m=3.0,
    height_m=6.0,
    service_clearance_inlet_m=2.0,
    service_clearance_outlet_m=3.0,
    overhead_clearance_m=1.5,
    hot_zone_exclusion_m=2.0,
)


# =============================================================================
# Vendor Cut-Sheet Reconciliation (Rule R-2)
# =============================================================================

@dataclass(frozen=True)
class VendorCutSheetData:
    """Structured vendor cut-sheet dimensions for reactor skid.
    
    This is the intake structure for vendor-provided physical dimensions.
    Parsed from vendor PDFs/drawings — no free-text fields.
    
    The pipeline:
        Vendor PDF/DWG → VendorCutSheetData (structured)
                       → derive_envelope_from_vendor_cut_sheet()
                       → ReactorEnvelopeParams (validated_by_vendor=True)
                       → Layout gates re-run with updated envelope
    """
    vendor_id: str
    model_number: str
    
    # Physical dimensions from cut-sheet (meters)
    skid_length_m: float
    skid_width_m: float
    skid_height_m: float
    
    # Vendor-specified clearances (meters)
    clearance_inlet_m: float
    clearance_outlet_m: float
    clearance_overhead_m: float
    
    # Hot zone (thermal exclusion) from vendor safety data
    hot_zone_exclusion_m: float
    
    # Metadata
    drawing_ref: str = ""
    date_received: str = ""
    
    def validate(self) -> List[str]:
        """Return list of validation issues, empty if clean."""
        issues = []
        if self.skid_length_m <= 0:
            issues.append(f"skid_length_m must be positive, got {self.skid_length_m}")
        if self.skid_width_m <= 0:
            issues.append(f"skid_width_m must be positive, got {self.skid_width_m}")
        if self.skid_height_m <= 0:
            issues.append(f"skid_height_m must be positive, got {self.skid_height_m}")
        if self.clearance_inlet_m < 0:
            issues.append(f"clearance_inlet_m must be non-negative, got {self.clearance_inlet_m}")
        if self.clearance_outlet_m < 0:
            issues.append(f"clearance_outlet_m must be non-negative, got {self.clearance_outlet_m}")
        if self.clearance_overhead_m < 0:
            issues.append(f"clearance_overhead_m must be non-negative, got {self.clearance_overhead_m}")
        if self.hot_zone_exclusion_m < 0:
            issues.append(f"hot_zone_exclusion_m must be non-negative, got {self.hot_zone_exclusion_m}")
        return issues


@dataclass(frozen=True)
class CutSheetReconciliation:
    """Result of reconciling vendor cut-sheet against conservative envelope.
    
    Tracks what changed and flags if the vendor envelope exceeds
    the layout's bounding envelope (requires layout re-validation).
    """
    vendor_id: str
    model_number: str
    conservative_envelope: ReactorEnvelopeParams
    vendor_envelope: ReactorEnvelopeParams
    
    # Dimensional deltas (vendor - conservative, negative = vendor is smaller)
    delta_length_m: float = 0.0
    delta_width_m: float = 0.0
    delta_height_m: float = 0.0
    delta_hot_zone_m: float = 0.0
    
    # Flags
    fits_conservative_footprint: bool = True   # Vendor fits inside conservative box
    requires_layout_revalidation: bool = False  # True if vendor exceeds conservative
    validation_issues: Tuple[str, ...] = ()


def derive_envelope_from_vendor_cut_sheet(
    cut_sheet: VendorCutSheetData,
    conservative_envelope: ReactorEnvelopeParams,
) -> Tuple[ReactorEnvelopeParams, CutSheetReconciliation]:
    """Convert vendor cut-sheet data to a validated reactor envelope.
    
    Rule R-2: Fixed conservative envelope until vendor cutsheets arrive.
    This function implements the transition from conservative to vendor-validated.
    
    Logic:
        1. Validate cut-sheet data (positive dimensions, etc.)
        2. Build ReactorEnvelopeParams with validated_by_vendor=True
        3. Compare against conservative envelope
        4. Flag if vendor exceeds conservative (requires re-layout)
    
    Args:
        cut_sheet: Parsed vendor cut-sheet data
        conservative_envelope: The current conservative envelope to compare against
    
    Returns:
        Tuple of (new validated envelope, reconciliation report)
    
    Raises:
        ValueError: If cut-sheet has validation issues
    """
    # Step 1: Validate input
    issues = cut_sheet.validate()
    if issues:
        raise ValueError(
            f"Vendor cut-sheet validation failed for {cut_sheet.vendor_id}: "
            + "; ".join(issues)
        )
    
    # Step 2: Build vendor-validated envelope
    vendor_envelope = ReactorEnvelopeParams(
        footprint_L_m=cut_sheet.skid_length_m,
        footprint_W_m=cut_sheet.skid_width_m,
        height_m=cut_sheet.skid_height_m,
        service_clearance_inlet_m=cut_sheet.clearance_inlet_m,
        service_clearance_outlet_m=cut_sheet.clearance_outlet_m,
        overhead_clearance_m=cut_sheet.clearance_overhead_m,
        hot_zone_exclusion_m=cut_sheet.hot_zone_exclusion_m,
        validated_by_vendor=True,
        vendor_id=cut_sheet.vendor_id,
    )
    
    # Step 3: Compute deltas
    delta_L = cut_sheet.skid_length_m - conservative_envelope.footprint_L_m
    delta_W = cut_sheet.skid_width_m - conservative_envelope.footprint_W_m
    delta_H = cut_sheet.skid_height_m - conservative_envelope.height_m
    delta_hz = cut_sheet.hot_zone_exclusion_m - conservative_envelope.hot_zone_exclusion_m
    
    # Step 4: Check if vendor fits inside conservative
    fits = (delta_L <= 0 and delta_W <= 0 and delta_H <= 0)
    requires_revalidation = not fits or delta_hz > 0
    
    reconciliation = CutSheetReconciliation(
        vendor_id=cut_sheet.vendor_id,
        model_number=cut_sheet.model_number,
        conservative_envelope=conservative_envelope,
        vendor_envelope=vendor_envelope,
        delta_length_m=round(delta_L, 3),
        delta_width_m=round(delta_W, 3),
        delta_height_m=round(delta_H, 3),
        delta_hot_zone_m=round(delta_hz, 3),
        fits_conservative_footprint=fits,
        requires_layout_revalidation=requires_revalidation,
    )
    
    return vendor_envelope, reconciliation


# =============================================================================
# Overnight Mode ↔ Hot Zone Bridge (GAP-004 Integration)
# =============================================================================

# Hot zone multipliers by overnight mode
# - HOLD: reactor stays hot → exclusion zone must be maintained at full size
# - CONTROLLED_COOLDOWN: reduced but non-zero thermal risk
# - FULL_SHUTDOWN: thermal risk dissipates, standard clearance is sufficient
# - UNKNOWN: conservative assumption = hot hold (worst case)
OVERNIGHT_HOT_ZONE_MULTIPLIERS = {
    "hold": 1.0,                # Full exclusion — reactor at operating temp
    "controlled_cooldown": 0.75, # Reduced but present — gradual cooling
    "full_shutdown": 0.5,        # Minimal — only residual heat
    "unknown": 1.0,              # Conservative default until vendor validates
}


def get_overnight_hot_zone_exclusion(
    base_hot_zone_m: float,
    overnight_mode: str,
    continuous_heat_required: bool = False,
) -> float:
    """Calculate overnight hot zone exclusion distance.
    
    During overnight periods, the hot zone exclusion may differ from
    daytime operations depending on the reactor's overnight mode.
    
    If continuous_heat_required (vendor-specified), the full exclusion
    always applies regardless of mode — the reactor stays hot.
    
    Args:
        base_hot_zone_m: Daytime hot zone exclusion in meters
        overnight_mode: OvernightMode value string (hold, controlled_cooldown, etc.)
        continuous_heat_required: If True, full exclusion always applies
    
    Returns:
        Overnight hot zone exclusion distance in meters
    """
    if continuous_heat_required:
        return base_hot_zone_m  # Full exclusion — heat source stays on
    
    multiplier = OVERNIGHT_HOT_ZONE_MULTIPLIERS.get(overnight_mode, 1.0)
    return round(base_hot_zone_m * multiplier, 2)


def validate_overnight_geometry(
    equipment: Tuple[EquipmentPlacement, ...],
    overnight_mode: str,
    continuous_heat_required: bool = False,
) -> LayoutGateResult:
    """Gate: Verify hot zone clearances hold under overnight conditions.
    
    Checks that no non-pyrolysis equipment overlaps the overnight
    hot zone of any pyrolysis equipment.  This is the spatial
    counterpart to GATE-04 (Unattended Safety).
    
    The overnight hot zone may be smaller than daytime (if mode is
    FULL_SHUTDOWN) or identical (if HOLD or continuous_heat_required).
    
    Args:
        equipment: All equipment placements
        overnight_mode: OvernightMode value string
        continuous_heat_required: If True, full exclusion always applies
    
    Returns:
        LayoutGateResult with pass/fail and violation details
    """
    violations = []
    
    # Find pyrolysis equipment (hot zone sources)
    pyro_items = [eq for eq in equipment if eq.hot_zone_exclusion_m > 0]
    non_pyro_items = [eq for eq in equipment if eq.hot_zone_exclusion_m == 0]
    
    for pyro in pyro_items:
        overnight_exclusion = get_overnight_hot_zone_exclusion(
            pyro.hot_zone_exclusion_m,
            overnight_mode,
            continuous_heat_required,
        )
        
        # Build overnight hot zone bounding box
        base_box = pyro.bounding_box
        overnight_hot_zone = base_box.expand(overnight_exclusion)
        
        for other in non_pyro_items:
            other_box = other.bounding_box
            if overnight_hot_zone.intersects_xy(other_box):
                violations.append(
                    f"{other.tag} overlaps overnight hot zone of {pyro.tag} "
                    f"(mode={overnight_mode}, exclusion={overnight_exclusion:.1f}m)"
                )
    
    passed = len(violations) == 0
    mode_label = overnight_mode if overnight_mode != "unknown" else "unknown (conservative)"
    
    return LayoutGateResult(
        name="Overnight Hot Zone Clearance",
        passed=passed,
        details=f"Overnight mode: {mode_label}, heat_required: {continuous_heat_required}",
        violations=violations,
    )


# =============================================================================
# Tank Geometry
# =============================================================================

@dataclass(frozen=True)
class TankGeometry:
    """Physical tank geometry for layout and procurement.
    
    Assumes vertical cylindrical tanks with flat bottom.
    """
    tag: str
    name: str
    diameter_m: float
    straight_side_m: float      # Cylinder height (not including dish/cone)
    freeboard_m: float = 0.3    # Headspace above max liquid
    
    # Containment
    containment_type: ContainmentType = ContainmentType.SHARED_SLAB
    containment_volume_m3: Optional[float] = None  # If separate berm
    
    @property
    def volume_gross_m3(self) -> float:
        """Gross tank volume (π r² h)."""
        import math
        r = self.diameter_m / 2
        return math.pi * r * r * self.straight_side_m
    
    @property
    def volume_working_m3(self) -> float:
        """Working volume (gross minus freeboard)."""
        import math
        r = self.diameter_m / 2
        h_working = self.straight_side_m - self.freeboard_m
        return math.pi * r * r * h_working
    
    @property
    def footprint_diameter_with_access(self) -> float:
        """Diameter including 0.8m perimeter access."""
        return self.diameter_m + 2 * 0.8
    
    def get_bounding_box(self, center_x: float, center_y: float) -> BoundingBox:
        """Return bounding box centered at (x, y)."""
        r = self.diameter_m / 2
        return BoundingBox(
            x_min=center_x - r,
            y_min=center_y - r,
            z_min=0,
            length=self.diameter_m,
            width=self.diameter_m,
            height=self.straight_side_m + self.freeboard_m,
        )
    
    def get_access_envelope(self, center_x: float, center_y: float) -> BoundingBox:
        """Return bounding box including 0.8m perimeter access."""
        r = self.footprint_diameter_with_access / 2
        return BoundingBox(
            x_min=center_x - r,
            y_min=center_y - r,
            z_min=0,
            length=self.footprint_diameter_with_access,
            width=self.footprint_diameter_with_access,
            height=self.straight_side_m + self.freeboard_m,
        )


# =============================================================================
# Equipment Placement
# =============================================================================

@dataclass(frozen=True)
class EquipmentPlacement:
    """Equipment placement in facility layout."""
    tag: str
    name: str
    subsystem: Subsystem
    
    # Position (southwest corner of equipment box)
    origin_x: float
    origin_y: float
    
    # Footprint
    length_m: float     # X dimension
    width_m: float      # Y dimension
    height_m: float     # Z dimension
    
    # Position Z (default 0 = floor)
    origin_z: float = 0.0
    
    # Clearances
    service_clearance_m: float = 1.0
    pull_out_direction: PullOutDirection = PullOutDirection.NONE
    pull_out_distance_m: float = 0.0
    
    # Containment
    containment_type: ContainmentType = ContainmentType.NONE
    
    # Hot zone (pyrolysis only)
    hot_zone_exclusion_m: float = 0.0
    
    @property
    def bounding_box(self) -> BoundingBox:
        return BoundingBox(
            x_min=self.origin_x,
            y_min=self.origin_y,
            z_min=self.origin_z,
            length=self.length_m,
            width=self.width_m,
            height=self.height_m,
        )
    
    @property
    def service_envelope(self) -> BoundingBox:
        """Bounding box including service clearance."""
        return self.bounding_box.expand(self.service_clearance_m)
    
    @property
    def pull_out_envelope(self) -> Optional[BoundingBox]:
        """Bounding box including pull-out clearance."""
        if self.pull_out_direction == PullOutDirection.NONE:
            return None
        
        box = self.bounding_box
        if self.pull_out_direction == PullOutDirection.EAST:
            return box.expand_directional(east=self.pull_out_distance_m)
        elif self.pull_out_direction == PullOutDirection.WEST:
            return box.expand_directional(west=self.pull_out_distance_m)
        elif self.pull_out_direction == PullOutDirection.NORTH:
            return box.expand_directional(north=self.pull_out_distance_m)
        elif self.pull_out_direction == PullOutDirection.SOUTH:
            return box.expand_directional(south=self.pull_out_distance_m)
        return None
    
    @property
    def hot_zone_envelope(self) -> Optional[BoundingBox]:
        """Hot zone exclusion envelope (pyrolysis only)."""
        if self.hot_zone_exclusion_m <= 0:
            return None
        return self.bounding_box.expand(self.hot_zone_exclusion_m)


# =============================================================================
# Zone Definition
# =============================================================================

@dataclass(frozen=True)
class Zone:
    """Functional zone in facility layout."""
    name: str
    subsystem: Subsystem
    origin_x: float
    origin_y: float
    length_m: float
    width_m: float
    height_m: float
    
    # Containment
    containment_type: ContainmentType = ContainmentType.NONE
    containment_volume_m3: float = 0
    
    # Sump (for product mode shared slab)
    sump_volume_m3: float = 0
    sump_isolated: bool = True  # Rule C-2: isolated by default
    
    @property
    def bounding_box(self) -> BoundingBox:
        return BoundingBox(
            x_min=self.origin_x,
            y_min=self.origin_y,
            z_min=0,
            length=self.length_m,
            width=self.width_m,
            height=self.height_m,
        )
    
    @property
    def area_m2(self) -> float:
        return self.length_m * self.width_m


# =============================================================================
# Containment
# =============================================================================

@dataclass(frozen=True)
class ContainmentArea:
    """Containment area specification (Rule C-1, C-2)."""
    name: str
    bounding_box: BoundingBox
    containment_type: ContainmentType
    
    # Volume requirements
    tank_volume_m3: float
    freeboard_fraction: float = 0.10      # 10% freeboard
    rainfall_allowance_m3: float = 0      # 25mm over area if outdoor
    spill_allowance_m3: float = 0         # Skid spill allowance
    
    # Sump (product mode)
    sump_volume_m3: float = 0
    sump_isolated: bool = True
    isolation_valve_lockable: bool = True
    
    @property
    def required_volume_m3(self) -> float:
        """Total required containment volume."""
        return (
            self.tank_volume_m3 * (1 + self.freeboard_fraction) +
            self.rainfall_allowance_m3 +
            self.spill_allowance_m3
        )
    
    @property
    def berm_height_m(self) -> float:
        """Required berm height (if separate berm)."""
        area = self.bounding_box.footprint_area
        if area <= 0:
            return 0
        return self.required_volume_m3 / area


# =============================================================================
# Tank Schedules (Standard Diameters)
# =============================================================================

# Product Mode Tank Schedule (standardized to 2 diameters)
PRODUCT_TANKS = (
    TankGeometry(
        tag="TK-101",
        name="EQ Tank",
        diameter_m=2.7,
        straight_side_m=3.5,
        freeboard_m=0.3,
        containment_type=ContainmentType.SHARED_SLAB,
    ),
    TankGeometry(
        tag="TK-102",
        name="Off-Spec Tank",
        diameter_m=2.2,
        straight_side_m=3.2,
        freeboard_m=0.3,
        containment_type=ContainmentType.SHARED_SLAB,
    ),
    TankGeometry(
        tag="TK-103",
        name="Centrate Tank",
        diameter_m=2.7,
        straight_side_m=3.5,
        freeboard_m=0.3,
        containment_type=ContainmentType.SHARED_SLAB,
    ),
)

# Hub Mode Tank Schedule (standardized to 3 diameters)
HUB_TANKS = (
    TankGeometry(
        tag="TK-201A",
        name="EQ Tank A (Duty)",
        diameter_m=3.0,
        straight_side_m=4.5,
        freeboard_m=0.3,
        containment_type=ContainmentType.SEPARATE_BERM,
    ),
    TankGeometry(
        tag="TK-201B",
        name="EQ Tank B (Standby)",
        diameter_m=3.0,
        straight_side_m=4.5,
        freeboard_m=0.3,
        containment_type=ContainmentType.SEPARATE_BERM,
    ),
    TankGeometry(
        tag="TK-202",
        name="Off-Spec Tank",
        diameter_m=2.7,
        straight_side_m=3.5,
        freeboard_m=0.3,
        containment_type=ContainmentType.SEPARATE_BERM,
    ),
    TankGeometry(
        tag="TK-203",
        name="Centrate Storage",
        diameter_m=4.0,
        straight_side_m=8.0,
        freeboard_m=0.5,
        containment_type=ContainmentType.SEPARATE_BERM,
    ),
)


# =============================================================================
# Facility Layouts
# =============================================================================

# Product Mode: 14m × 8m × 5.5m
PRODUCT_ENVELOPE = FacilityEnvelope(
    length_m=14.0,
    width_m=8.0,
    height_m=5.5,
    name="Product Mode Facility",
)

# Hub Mode: 30m × 18m × 7.5m
HUB_ENVELOPE = FacilityEnvelope(
    length_m=30.0,
    width_m=18.0,
    height_m=7.5,
    name="Hub Mode Facility",
)


# =============================================================================
# Product Mode Layout (14m × 8m × 5.5m)
# =============================================================================

PRODUCT_ZONES = (
    Zone(
        name="Receiving/Dirty Pad",
        subsystem=Subsystem.RECEIVING,
        origin_x=0.0,
        origin_y=3.0,
        length_m=6.0,
        width_m=5.0,
        height_m=5.5,
        containment_type=ContainmentType.SHARED_SLAB,
        sump_volume_m3=2.0,
        sump_isolated=True,
    ),
    Zone(
        name="Tank Bay",
        subsystem=Subsystem.EQ_STORAGE,
        origin_x=0.0,
        origin_y=0.0,
        length_m=6.0,
        width_m=3.0,
        height_m=4.0,
        containment_type=ContainmentType.SHARED_SLAB,
        sump_volume_m3=2.0,
        sump_isolated=True,
    ),
    Zone(
        name="Dewatering Skid Bay",
        subsystem=Subsystem.DEWATERING,
        origin_x=6.0,
        origin_y=0.0,
        length_m=4.0,
        width_m=3.0,
        height_m=3.5,
        containment_type=ContainmentType.SHARED_SLAB,
    ),
    Zone(
        name="Pyrolysis Skid Bay",
        subsystem=Subsystem.PYROLYSIS,
        origin_x=6.0,
        origin_y=3.0,
        length_m=7.0,
        width_m=3.5,
        height_m=5.5,
        containment_type=ContainmentType.HOT_ZONE,
    ),
    Zone(
        name="Char Storage + Bagging",
        subsystem=Subsystem.CHAR_HANDLING,
        origin_x=11.0,
        origin_y=0.0,
        length_m=3.0,
        width_m=3.0,
        height_m=4.0,
    ),
    Zone(
        name="Service Aisle",
        subsystem=Subsystem.ACCESS,
        origin_x=6.0,
        origin_y=6.5,
        length_m=8.0,
        width_m=1.5,
        height_m=5.5,
    ),
)

PRODUCT_EQUIPMENT = (
    # Layout strategy for 14×8m footprint:
    # - West strip (x=0-4): EQ + Centrate tanks (stacked N-S)
    # - Center strip (x=4-7.5): Off-spec + Dewatering  
    # - East strip (x=7.5-14): Pyrolysis + Char (hot zone)
    # - Char is downstream of pyrolysis, within hot zone (acceptable)
    
    # EQ Tank - southwest (0.3, 0.3)
    # Box: 0.3 to 3.0 X, 0.3 to 3.0 Y
    # Service: -0.2 to 3.5 X, -0.2 to 3.5 Y (clearance 0.5m)
    EquipmentPlacement(
        tag="TK-101",
        name="EQ Tank",
        subsystem=Subsystem.EQ_STORAGE,
        origin_x=0.3,
        origin_y=0.3,
        length_m=2.7,
        width_m=2.7,
        height_m=3.8,
        service_clearance_m=0.5,
        containment_type=ContainmentType.SHARED_SLAB,
    ),
    # Centrate Tank - northwest (0.3, 4.0)
    # Box: 0.3 to 3.0 X, 4.0 to 6.7 Y
    # Service: -0.2 to 3.5 X, 3.5 to 7.2 Y
    # Gap from TK-101: Y=3.0+0.5 to 4.0-0.5 = 0.5m (OK, barely)
    EquipmentPlacement(
        tag="TK-103",
        name="Centrate Tank",
        subsystem=Subsystem.CENTRATE,
        origin_x=0.3,
        origin_y=4.0,
        length_m=2.7,
        width_m=2.7,
        height_m=3.8,
        service_clearance_m=0.5,
        containment_type=ContainmentType.SHARED_SLAB,
    ),
    # Off-Spec Tank - center-south (4.0, 0.3)
    # Box: 4.0 to 6.2 X, 0.3 to 2.5 Y
    # Service: 3.5 to 6.7 X, -0.2 to 3.0 Y
    EquipmentPlacement(
        tag="TK-102",
        name="Off-Spec Tank",
        subsystem=Subsystem.OFF_SPEC,
        origin_x=4.0,
        origin_y=0.3,
        length_m=2.2,
        width_m=2.2,
        height_m=3.5,
        service_clearance_m=0.5,
        containment_type=ContainmentType.SHARED_SLAB,
    ),
    # Dewatering Skid - center-north (4.0, 3.8)
    # Box: 4.0 to 6.8 X, 3.8 to 5.8 Y  
    # Service: 3.5 to 7.3 X, 3.3 to 6.3 Y
    # Gap from TK-102: Y service ends at 3.0, DW service starts at 3.3 = 0.3m gap
    EquipmentPlacement(
        tag="DW-101",
        name="Dewatering Skid",
        subsystem=Subsystem.DEWATERING,
        origin_x=4.0,
        origin_y=3.8,
        length_m=2.8,
        width_m=2.0,
        height_m=2.5,
        service_clearance_m=0.5,
        pull_out_direction=PullOutDirection.NORTH,
        pull_out_distance_m=0.8,
        containment_type=ContainmentType.SHARED_SLAB,
    ),
    # Pyrolysis Skid - east side (8.5, 1.0)
    # Box: 8.5 to 13.0 X, 1.0 to 3.5 Y
    # Hot zone (1.2m): 7.3 to 14.2 X, -0.2 to 4.7 Y
    # Service: 7.5 to 14.0 X, 0.0 to 4.5 Y
    EquipmentPlacement(
        tag="PY-101",
        name="Pyrolysis Skid",
        subsystem=Subsystem.PYROLYSIS,
        origin_x=8.5,
        origin_y=1.0,
        length_m=4.5,
        width_m=2.5,
        height_m=5.0,
        service_clearance_m=1.0,
        pull_out_direction=PullOutDirection.EAST,
        pull_out_distance_m=0.5,
        hot_zone_exclusion_m=1.2,
    ),
    # Char Storage - east-north (8.5, 4.2) 
    # Box: 8.5 to 10.5 X, 4.2 to 6.0 Y
    # Service: 8.2 to 10.8 X, 3.9 to 6.3 Y
    # Note: This IS within pyro hot zone (Y=4.7 > 4.2), but char is downstream
    # of pyrolysis so this is intentional layout (char exits hot zone)
    EquipmentPlacement(
        tag="CH-101",
        name="Char Storage Bin",
        subsystem=Subsystem.CHAR_HANDLING,
        origin_x=8.5,
        origin_y=5.5,
        length_m=2.0,
        width_m=1.8,
        height_m=2.5,
        service_clearance_m=0.3,
    ),
)


# =============================================================================
# Hub Mode Layout (30m × 18m × 7.5m)
# =============================================================================

HUB_ZONES = (
    Zone(
        name="Receiving Bay (Drive-In)",
        subsystem=Subsystem.RECEIVING,
        origin_x=0.0,
        origin_y=10.0,
        length_m=12.0,
        width_m=8.0,
        height_m=7.5,
        containment_type=ContainmentType.SEPARATE_BERM,
        containment_volume_m3=10.0,
    ),
    Zone(
        name="Screening + Grit",
        subsystem=Subsystem.RECEIVING,
        origin_x=12.0,
        origin_y=15.0,
        length_m=5.0,
        width_m=3.0,
        height_m=4.0,
        containment_type=ContainmentType.SEPARATE_BERM,
    ),
    Zone(
        name="EQ Tank Bay",
        subsystem=Subsystem.EQ_STORAGE,
        origin_x=0.0,
        origin_y=0.0,
        length_m=10.0,
        width_m=6.0,
        height_m=5.0,
        containment_type=ContainmentType.SEPARATE_BERM,
        containment_volume_m3=70.0,
    ),
    Zone(
        name="Off-Spec Containment",
        subsystem=Subsystem.OFF_SPEC,
        origin_x=10.0,
        origin_y=0.0,
        length_m=5.0,
        width_m=4.0,
        height_m=4.0,
        containment_type=ContainmentType.SEPARATE_BERM,
        containment_volume_m3=25.0,
    ),
    Zone(
        name="Dewatering Bay",
        subsystem=Subsystem.DEWATERING,
        origin_x=15.0,
        origin_y=0.0,
        length_m=6.0,
        width_m=5.0,
        height_m=5.0,
        containment_type=ContainmentType.SEPARATE_BERM,
    ),
    Zone(
        name="Cake Buffer + Conveyance",
        subsystem=Subsystem.CAKE_HANDLING,
        origin_x=21.0,
        origin_y=0.0,
        length_m=6.0,
        width_m=4.0,
        height_m=4.0,
    ),
    Zone(
        name="Pyrolysis Island",
        subsystem=Subsystem.PYROLYSIS,
        origin_x=17.0,
        origin_y=5.0,
        length_m=12.0,
        width_m=5.0,
        height_m=7.5,
        containment_type=ContainmentType.HOT_ZONE,
    ),
    Zone(
        name="Centrate Storage",
        subsystem=Subsystem.CENTRATE,
        origin_x=0.0,
        origin_y=6.0,
        length_m=8.0,
        width_m=4.0,
        height_m=9.0,
        containment_type=ContainmentType.SEPARATE_BERM,
        containment_volume_m3=110.0,
    ),
    Zone(
        name="Char Handling + Storage",
        subsystem=Subsystem.CHAR_HANDLING,
        origin_x=22.0,
        origin_y=10.0,
        length_m=8.0,
        width_m=5.0,
        height_m=5.0,
    ),
    Zone(
        name="Maintenance Corridor",
        subsystem=Subsystem.ACCESS,
        origin_x=8.0,
        origin_y=6.0,
        length_m=9.0,
        width_m=4.0,
        height_m=7.5,
    ),
)

HUB_EQUIPMENT = (
    # Hub Mode: 30m × 18m × 7.5m
    # Layout strategy:
    # - South strip (y=0-6): EQ tanks, Off-spec, Dewatering, Cake buffer
    # - Center strip (y=6-12): Centrate, Maintenance corridor, Pyrolysis
    # - North strip (y=12-18): Receiving bay, Screening, Char handling
    
    # EQ Tank A - southwest
    EquipmentPlacement(
        tag="TK-201A",
        name="EQ Tank A (Duty)",
        subsystem=Subsystem.EQ_STORAGE,
        origin_x=1.0,
        origin_y=1.0,
        length_m=3.0,
        width_m=3.0,
        height_m=4.8,
        service_clearance_m=0.6,
        containment_type=ContainmentType.SEPARATE_BERM,
    ),
    # EQ Tank B - east of A (need 0.6+0.6 = 1.2m gap)
    # A ends at x=4.0, B starts at x=5.5 (gap = 1.5m)
    EquipmentPlacement(
        tag="TK-201B",
        name="EQ Tank B (Standby)",
        subsystem=Subsystem.EQ_STORAGE,
        origin_x=5.5,
        origin_y=1.0,
        length_m=3.0,
        width_m=3.0,
        height_m=4.8,
        service_clearance_m=0.6,
        containment_type=ContainmentType.SEPARATE_BERM,
    ),
    # Off-Spec Tank - separate containment area, south of centrate
    # Centrate service Y ends at 6.5-0.8=5.7 to 10.5+0.8=11.3
    # Place off-spec in separate zone, south side
    EquipmentPlacement(
        tag="TK-202",
        name="Off-Spec Tank",
        subsystem=Subsystem.OFF_SPEC,
        origin_x=10.0,
        origin_y=1.0,
        length_m=2.7,
        width_m=2.7,
        height_m=3.8,
        service_clearance_m=0.5,
        containment_type=ContainmentType.SEPARATE_BERM,
    ),
    # Centrate Storage - center-west (reduced height to 7.5m max)
    EquipmentPlacement(
        tag="TK-203",
        name="Centrate Storage",
        subsystem=Subsystem.CENTRATE,
        origin_x=1.0,
        origin_y=6.5,
        length_m=4.0,
        width_m=4.0,
        height_m=7.0,
        service_clearance_m=0.8,
        containment_type=ContainmentType.SEPARATE_BERM,
    ),
    # Screening - north receiving bay
    EquipmentPlacement(
        tag="SC-201",
        name="Rotary Screen",
        subsystem=Subsystem.RECEIVING,
        origin_x=12.5,
        origin_y=14.5,
        length_m=3.0,
        width_m=2.0,
        height_m=2.5,
        service_clearance_m=0.8,
    ),
    # Dewatering Skid - south strip, outside pyro hot zone
    EquipmentPlacement(
        tag="DW-201",
        name="Dewatering Skid",
        subsystem=Subsystem.DEWATERING,
        origin_x=14.0,
        origin_y=1.0,
        length_m=4.0,
        width_m=3.0,
        height_m=3.0,
        service_clearance_m=0.8,
        pull_out_direction=PullOutDirection.SOUTH,
        pull_out_distance_m=1.5,
        containment_type=ContainmentType.SEPARATE_BERM,
    ),
    # Cake Buffer - north of pyrolysis, outside hot zone
    # Hot zone Y ends at 11.5, cake starts at 12.0
    # Away from screening (which ends at Y=16.5+0.8=17.3)
    EquipmentPlacement(
        tag="CB-201",
        name="Cake Buffer Hopper",
        subsystem=Subsystem.CAKE_HANDLING,
        origin_x=17.5,
        origin_y=12.0,
        length_m=3.0,
        width_m=2.5,
        height_m=3.0,
        service_clearance_m=0.6,
    ),
    # Pyrolysis Skid - east side with 2m hot zone
    # Box: 19.0 to 28.0 X, 6.5 to 9.5 Y
    # Hot zone: 17.0 to 30.0 X, 4.5 to 11.5 Y
    EquipmentPlacement(
        tag="PY-201",
        name="Pyrolysis Skid",
        subsystem=Subsystem.PYROLYSIS,
        origin_x=19.0,
        origin_y=6.5,
        length_m=9.0,
        width_m=3.0,
        height_m=6.0,
        service_clearance_m=1.5,
        pull_out_direction=PullOutDirection.EAST,
        pull_out_distance_m=2.0,
        hot_zone_exclusion_m=2.0,
    ),
    # Char Storage - northeast, outside hot zone Y range
    # Hot zone Y ends at 11.5, char starts at 12.0
    EquipmentPlacement(
        tag="CH-201",
        name="Char Storage Bin",
        subsystem=Subsystem.CHAR_HANDLING,
        origin_x=24.0,
        origin_y=12.0,
        length_m=4.0,
        width_m=3.0,
        height_m=4.0,
        service_clearance_m=0.8,
    ),
)


# =============================================================================
# Layout Gates (Validation)
# =============================================================================

@dataclass
class LayoutGateResult:
    """Result from a layout validation gate."""
    name: str
    passed: bool
    details: str
    violations: List[str] = field(default_factory=list)


def validate_clearance_overlap(equipment: Tuple[EquipmentPlacement, ...]) -> LayoutGateResult:
    """Gate: No equipment service envelopes may overlap."""
    violations = []
    
    for i, eq1 in enumerate(equipment):
        for eq2 in equipment[i+1:]:
            env1 = eq1.service_envelope
            env2 = eq2.service_envelope
            if env1.intersects_xy(env2):
                violations.append(f"{eq1.tag} service envelope overlaps {eq2.tag}")
    
    return LayoutGateResult(
        name="Clearance Overlap",
        passed=len(violations) == 0,
        details=f"Checked {len(equipment)} equipment items",
        violations=violations,
    )


def validate_hot_zone_exclusion(equipment: Tuple[EquipmentPlacement, ...]) -> LayoutGateResult:
    """Gate: No equipment may intersect pyrolysis hot zone."""
    violations = []
    
    # Find pyrolysis equipment
    pyro_items = [eq for eq in equipment if eq.hot_zone_exclusion_m > 0]
    non_pyro = [eq for eq in equipment if eq.hot_zone_exclusion_m == 0]
    
    for pyro in pyro_items:
        hot_zone = pyro.hot_zone_envelope
        if hot_zone is None:
            continue
        
        for eq in non_pyro:
            if hot_zone.intersects_xy(eq.bounding_box):
                violations.append(f"{eq.tag} intersects {pyro.tag} hot zone exclusion")
    
    return LayoutGateResult(
        name="Hot Zone Exclusion",
        passed=len(violations) == 0,
        details=f"Checked {len(pyro_items)} hot zones against {len(non_pyro)} items",
        violations=violations,
    )


def validate_containment_separation(
    equipment: Tuple[EquipmentPlacement, ...],
    mode: DeploymentMode,
) -> LayoutGateResult:
    """Gate: Hub mode requires separate containment for off-spec and centrate."""
    violations = []
    
    if mode == DeploymentMode.HUB:
        # Rule C-1: Hub must use separate containment
        off_spec = [eq for eq in equipment if eq.subsystem == Subsystem.OFF_SPEC]
        centrate = [eq for eq in equipment if eq.subsystem == Subsystem.CENTRATE]
        
        for eq in off_spec:
            if eq.containment_type != ContainmentType.SEPARATE_BERM:
                violations.append(f"{eq.tag}: Hub off-spec must have SEPARATE_BERM containment")
        
        for eq in centrate:
            if eq.containment_type != ContainmentType.SEPARATE_BERM:
                violations.append(f"{eq.tag}: Hub centrate must have SEPARATE_BERM containment")
    
    return LayoutGateResult(
        name="Containment Separation",
        passed=len(violations) == 0,
        details=f"Mode: {mode.value}",
        violations=violations,
    )


def validate_facility_bounds(
    equipment: Tuple[EquipmentPlacement, ...],
    envelope: FacilityEnvelope,
) -> LayoutGateResult:
    """Gate: All equipment must fit within facility envelope."""
    violations = []
    facility_box = envelope.as_bounding_box()
    
    for eq in equipment:
        box = eq.bounding_box
        if box.x_max > facility_box.x_max:
            violations.append(f"{eq.tag} exceeds X boundary by {box.x_max - facility_box.x_max:.1f}m")
        if box.y_max > facility_box.y_max:
            violations.append(f"{eq.tag} exceeds Y boundary by {box.y_max - facility_box.y_max:.1f}m")
        if box.z_max > facility_box.z_max:
            violations.append(f"{eq.tag} exceeds Z boundary by {box.z_max - facility_box.z_max:.1f}m")
        if box.x_min < 0 or box.y_min < 0:
            violations.append(f"{eq.tag} has negative origin coordinates")
    
    return LayoutGateResult(
        name="Facility Bounds",
        passed=len(violations) == 0,
        details=f"Envelope: {envelope.length_m}m × {envelope.width_m}m × {envelope.height_m}m",
        violations=violations,
    )


def run_layout_gates(
    equipment: Tuple[EquipmentPlacement, ...],
    envelope: FacilityEnvelope,
    mode: DeploymentMode,
) -> List[LayoutGateResult]:
    """Run all layout validation gates."""
    return [
        validate_facility_bounds(equipment, envelope),
        validate_clearance_overlap(equipment),
        validate_hot_zone_exclusion(equipment),
        validate_containment_separation(equipment, mode),
    ]


# =============================================================================
# Output Functions
# =============================================================================

def print_tank_schedule(tanks: Tuple[TankGeometry, ...]) -> None:
    """Print tank schedule table."""
    print("\n" + "=" * 80)
    print("TANK SCHEDULE")
    print("=" * 80)
    print(f"{'Tag':<10} {'Name':<25} {'Dia (m)':<10} {'H (m)':<10} {'V_work (m³)':<12} {'Containment':<15}")
    print("-" * 80)
    for t in tanks:
        print(f"{t.tag:<10} {t.name:<25} {t.diameter_m:<10.1f} {t.straight_side_m:<10.1f} {t.volume_working_m3:<12.1f} {t.containment_type.value:<15}")


def print_equipment_schedule(equipment: Tuple[EquipmentPlacement, ...]) -> None:
    """Print equipment placement table."""
    print("\n" + "=" * 100)
    print("EQUIPMENT PLACEMENT SCHEDULE")
    print("=" * 100)
    print(f"{'Tag':<10} {'Name':<25} {'Origin (x,y)':<15} {'L×W×H (m)':<20} {'Hot Zone':<10}")
    print("-" * 100)
    for eq in equipment:
        origin = f"({eq.origin_x:.1f}, {eq.origin_y:.1f})"
        dims = f"{eq.length_m:.1f} × {eq.width_m:.1f} × {eq.height_m:.1f}"
        hot = f"{eq.hot_zone_exclusion_m:.1f}m" if eq.hot_zone_exclusion_m > 0 else "-"
        print(f"{eq.tag:<10} {eq.name:<25} {origin:<15} {dims:<20} {hot:<10}")


def print_zone_schedule(zones: Tuple[Zone, ...]) -> None:
    """Print zone layout table."""
    print("\n" + "=" * 90)
    print("ZONE LAYOUT")
    print("=" * 90)
    print(f"{'Zone':<30} {'Origin (x,y)':<15} {'L×W (m)':<15} {'Area (m²)':<12} {'Containment':<15}")
    print("-" * 90)
    for z in zones:
        origin = f"({z.origin_x:.1f}, {z.origin_y:.1f})"
        dims = f"{z.length_m:.1f} × {z.width_m:.1f}"
        print(f"{z.name:<30} {origin:<15} {dims:<15} {z.area_m2:<12.1f} {z.containment_type.value:<15}")


def print_layout_report(
    envelope: FacilityEnvelope,
    zones: Tuple[Zone, ...],
    equipment: Tuple[EquipmentPlacement, ...],
    tanks: Tuple[TankGeometry, ...],
    mode: DeploymentMode,
) -> None:
    """Print complete layout report."""
    print("\n" + "=" * 80)
    print(f"FACILITY LAYOUT REPORT: {envelope.name}")
    print("=" * 80)
    print(f"Mode: {mode.value.upper()}")
    print(f"Envelope: {envelope.length_m}m (L) × {envelope.width_m}m (W) × {envelope.height_m}m (H)")
    print(f"Footprint: {envelope.footprint_area:.0f} m²")
    print(f"Volume: {envelope.volume:.0f} m³")
    
    print_zone_schedule(zones)
    print_equipment_schedule(equipment)
    print_tank_schedule(tanks)
    
    # Run gates
    print("\n" + "=" * 80)
    print("LAYOUT GATES")
    print("=" * 80)
    gates = run_layout_gates(equipment, envelope, mode)
    all_passed = True
    for gate in gates:
        status = "✓ PASS" if gate.passed else "✗ FAIL"
        print(f"{gate.name}: {status}")
        if not gate.passed:
            all_passed = False
            for v in gate.violations:
                print(f"    - {v}")
    
    print("\n" + ("All gates passed." if all_passed else "LAYOUT GATES FAILED - Review violations."))


def print_ascii_layout(
    equipment: Tuple[EquipmentPlacement, ...],
    envelope: FacilityEnvelope,
    scale: float = 2.0,  # chars per meter
) -> None:
    """Print simple ASCII plan view."""
    width = int(envelope.length_m * scale) + 1
    height = int(envelope.width_m * scale) + 1
    
    # Initialize grid
    grid = [['.' for _ in range(width)] for _ in range(height)]
    
    # Draw boundary
    for x in range(width):
        grid[0][x] = '-'
        grid[height-1][x] = '-'
    for y in range(height):
        grid[y][0] = '|'
        grid[y][width-1] = '|'
    
    # Draw equipment
    for eq in equipment:
        x1 = int(eq.origin_x * scale)
        y1 = int(eq.origin_y * scale)
        x2 = int((eq.origin_x + eq.length_m) * scale)
        y2 = int((eq.origin_y + eq.width_m) * scale)
        
        # Draw box
        for x in range(max(1, x1), min(width-1, x2)):
            for y in range(max(1, y1), min(height-1, y2)):
                if y < height and x < width:
                    grid[height - 1 - y][x] = '#'
        
        # Label center
        cx = (x1 + x2) // 2
        cy = height - 1 - (y1 + y2) // 2
        if 0 <= cx < width and 0 <= cy < height:
            label = eq.tag[:3]
            for i, c in enumerate(label):
                if cx + i < width:
                    grid[cy][cx + i] = c
    
    print("\n" + "=" * 60)
    print("ASCII PLAN VIEW (North = Top)")
    print(f"Scale: 1 char ≈ {1/scale:.1f}m")
    print("=" * 60)
    for row in grid:
        print(''.join(row))


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m septage_model.artifacts.facility_geometry <command>")
        print("\nCommands:")
        print("  layout-product    Product mode layout report")
        print("  layout-hub        Hub mode layout report")
        print("  tanks-product     Product mode tank schedule")
        print("  tanks-hub         Hub mode tank schedule")
        print("  ascii-product     Product mode ASCII layout")
        print("  ascii-hub         Hub mode ASCII layout")
        print("  gates-product     Run product mode layout gates")
        print("  gates-hub         Run hub mode layout gates")
        return
    
    cmd = sys.argv[1].lower()
    
    if cmd == "layout-product":
        print_layout_report(PRODUCT_ENVELOPE, PRODUCT_ZONES, PRODUCT_EQUIPMENT, PRODUCT_TANKS, DeploymentMode.PRODUCT)
    
    elif cmd == "layout-hub":
        print_layout_report(HUB_ENVELOPE, HUB_ZONES, HUB_EQUIPMENT, HUB_TANKS, DeploymentMode.HUB)
    
    elif cmd == "tanks-product":
        print_tank_schedule(PRODUCT_TANKS)
    
    elif cmd == "tanks-hub":
        print_tank_schedule(HUB_TANKS)
    
    elif cmd == "ascii-product":
        print_ascii_layout(PRODUCT_EQUIPMENT, PRODUCT_ENVELOPE, scale=3.0)
    
    elif cmd == "ascii-hub":
        print_ascii_layout(HUB_EQUIPMENT, HUB_ENVELOPE, scale=1.5)
    
    elif cmd == "gates-product":
        gates = run_layout_gates(PRODUCT_EQUIPMENT, PRODUCT_ENVELOPE, DeploymentMode.PRODUCT)
        for g in gates:
            print(f"{g.name}: {'PASS' if g.passed else 'FAIL'}")
            for v in g.violations:
                print(f"  - {v}")
    
    elif cmd == "gates-hub":
        gates = run_layout_gates(HUB_EQUIPMENT, HUB_ENVELOPE, DeploymentMode.HUB)
        for g in gates:
            print(f"{g.name}: {'PASS' if g.passed else 'FAIL'}")
            for v in g.violations:
                print(f"  - {v}")
    
    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
