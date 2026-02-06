"""
Tests for Facility Geometry Module - XYZ Bounding Box Layout System.

Covers:
- Core geometry: BoundingBox, FacilityEnvelope, Zone, ContainmentArea
- Reactor envelopes: service clearances, hot zone exclusion
- Tank geometry: volumes, access envelopes
- Equipment placement: bounding boxes, service envelopes, pull-out, hot zone
- Layout data integrity: envelopes, equipment fit, tag uniqueness
- Validation gates: bounds, clearance overlap, hot zone, containment
- Cross-module consistency: geometry ↔ design tag matching
"""

import math
import pytest

from septage_model.artifacts.facility_geometry import (
    # Enums
    DeploymentMode,
    Subsystem,
    ContainmentType,
    PullOutDirection,
    # Core geometry
    BoundingBox,
    FacilityEnvelope,
    # Reactor
    ReactorEnvelopeParams,
    PRODUCT_REACTOR_ENVELOPE,
    HUB_REACTOR_ENVELOPE,
    # Tank
    TankGeometry,
    PRODUCT_TANKS,
    HUB_TANKS,
    # Equipment + Zone
    EquipmentPlacement,
    Zone,
    ContainmentArea,
    # Layouts
    PRODUCT_ENVELOPE,
    HUB_ENVELOPE,
    PRODUCT_ZONES,
    HUB_ZONES,
    PRODUCT_EQUIPMENT,
    HUB_EQUIPMENT,
    # Gates
    LayoutGateResult,
    validate_facility_bounds,
    validate_clearance_overlap,
    validate_hot_zone_exclusion,
    validate_containment_separation,
    run_layout_gates,
)


# =============================================================================
# BOUNDING BOX TESTS
# =============================================================================

class TestBoundingBox:
    """Test 3D bounding box geometry."""

    def test_basic_properties(self):
        """Box should report correct max coordinates."""
        box = BoundingBox(x_min=1, y_min=2, z_min=0, length=4, width=3, height=5)
        assert box.x_max == 5.0
        assert box.y_max == 5.0
        assert box.z_max == 5.0

    def test_footprint_area(self):
        """Footprint area = length × width."""
        box = BoundingBox(x_min=0, y_min=0, z_min=0, length=10, width=5, height=3)
        assert box.footprint_area == 50.0

    def test_volume(self):
        """Volume = L × W × H."""
        box = BoundingBox(x_min=0, y_min=0, z_min=0, length=10, width=5, height=3)
        assert box.volume == 150.0

    def test_center(self):
        """Center should be midpoint in all three axes."""
        box = BoundingBox(x_min=2, y_min=4, z_min=0, length=6, width=8, height=10)
        cx, cy, cz = box.center
        assert cx == 5.0
        assert cy == 8.0
        assert cz == 5.0

    def test_intersects_xy_overlapping(self):
        """Overlapping boxes should intersect."""
        a = BoundingBox(x_min=0, y_min=0, z_min=0, length=5, width=5, height=3)
        b = BoundingBox(x_min=3, y_min=3, z_min=0, length=5, width=5, height=3)
        assert a.intersects_xy(b) is True
        assert b.intersects_xy(a) is True

    def test_intersects_xy_no_overlap(self):
        """Non-overlapping boxes should not intersect."""
        a = BoundingBox(x_min=0, y_min=0, z_min=0, length=5, width=5, height=3)
        b = BoundingBox(x_min=6, y_min=0, z_min=0, length=5, width=5, height=3)
        assert a.intersects_xy(b) is False

    def test_intersects_xy_edge_touching(self):
        """Edge-touching boxes should NOT intersect (< not <=)."""
        a = BoundingBox(x_min=0, y_min=0, z_min=0, length=5, width=5, height=3)
        b = BoundingBox(x_min=5, y_min=0, z_min=0, length=5, width=5, height=3)
        assert a.intersects_xy(b) is False

    def test_expand_uniform(self):
        """Expand should grow box by margin on all XY sides."""
        box = BoundingBox(x_min=5, y_min=5, z_min=0, length=4, width=4, height=3)
        expanded = box.expand(1.0)
        assert expanded.x_min == 4.0
        assert expanded.y_min == 4.0
        assert expanded.length == 6.0
        assert expanded.width == 6.0
        # Height expands upward only
        assert expanded.height == 4.0
        assert expanded.z_min == 0.0

    def test_expand_directional(self):
        """Directional expansion should grow only specified sides."""
        box = BoundingBox(x_min=5, y_min=5, z_min=0, length=4, width=4, height=3)
        expanded = box.expand_directional(north=2, east=3)
        assert expanded.x_min == 5.0       # no west expansion
        assert expanded.y_min == 5.0       # no south expansion
        assert expanded.length == 4 + 3    # east
        assert expanded.width == 4 + 2     # north


# =============================================================================
# FACILITY ENVELOPE TESTS
# =============================================================================

class TestFacilityEnvelope:
    """Test facility envelope properties."""

    def test_product_envelope_dimensions(self):
        """Product envelope should be 14 × 8 × 5.5 m."""
        assert PRODUCT_ENVELOPE.length_m == 14.0
        assert PRODUCT_ENVELOPE.width_m == 8.0
        assert PRODUCT_ENVELOPE.height_m == 5.5

    def test_hub_envelope_dimensions(self):
        """Hub envelope should be 30 × 18 × 7.5 m."""
        assert HUB_ENVELOPE.length_m == 30.0
        assert HUB_ENVELOPE.width_m == 18.0
        assert HUB_ENVELOPE.height_m == 7.5

    def test_product_footprint(self):
        """Product footprint = 14 × 8 = 112 m²."""
        assert PRODUCT_ENVELOPE.footprint_area == 112.0

    def test_hub_footprint(self):
        """Hub footprint = 30 × 18 = 540 m²."""
        assert HUB_ENVELOPE.footprint_area == 540.0

    def test_as_bounding_box(self):
        """as_bounding_box should start at origin."""
        box = PRODUCT_ENVELOPE.as_bounding_box()
        assert box.x_min == 0
        assert box.y_min == 0
        assert box.z_min == 0
        assert box.x_max == 14.0
        assert box.y_max == 8.0
        assert box.z_max == 5.5

    def test_hub_volume(self):
        """Hub volume = 30 × 18 × 7.5 = 4050 m³."""
        assert HUB_ENVELOPE.volume == 4050.0


# =============================================================================
# REACTOR ENVELOPE TESTS
# =============================================================================

class TestReactorEnvelope:
    """Test reactor envelope layout parameters."""

    def test_product_reactor_footprint(self):
        """Product reactor: 6.0 × 2.5 × 5.0 m."""
        r = PRODUCT_REACTOR_ENVELOPE
        assert r.footprint_L_m == 6.0
        assert r.footprint_W_m == 2.5
        assert r.height_m == 5.0

    def test_hub_reactor_footprint(self):
        """Hub reactor: 9.0 × 3.0 × 6.0 m."""
        r = HUB_REACTOR_ENVELOPE
        assert r.footprint_L_m == 9.0
        assert r.footprint_W_m == 3.0
        assert r.height_m == 6.0

    def test_equipment_box_at_origin(self):
        """Equipment box should place reactor at given origin."""
        r = PRODUCT_REACTOR_ENVELOPE
        box = r.get_equipment_box(2.0, 3.0)
        assert box.x_min == 2.0
        assert box.y_min == 3.0
        assert box.length == 6.0
        assert box.width == 2.5

    def test_service_envelope_larger_than_equipment(self):
        """Service envelope must be larger than equipment box."""
        r = HUB_REACTOR_ENVELOPE
        eq = r.get_equipment_box(5.0, 5.0)
        svc = r.get_service_envelope(5.0, 5.0)
        assert svc.x_min < eq.x_min
        assert svc.x_max > eq.x_max
        assert svc.z_max > eq.z_max

    def test_hot_zone_larger_than_service(self):
        """Hot zone should be larger than service envelope."""
        r = HUB_REACTOR_ENVELOPE
        svc = r.get_service_envelope(5.0, 5.0)
        hot = r.get_hot_zone(5.0, 5.0)
        assert hot.footprint_area > svc.footprint_area

    def test_not_validated_by_default(self):
        """Default reactor envelopes should not be vendor-validated."""
        assert PRODUCT_REACTOR_ENVELOPE.validated_by_vendor is False
        assert HUB_REACTOR_ENVELOPE.validated_by_vendor is False


# =============================================================================
# TANK GEOMETRY TESTS
# =============================================================================

class TestTankGeometry:
    """Test tank geometry calculations."""

    def test_product_tanks_count(self):
        """Product mode should have 3 tanks (EQ, Off-Spec, Centrate)."""
        assert len(PRODUCT_TANKS) == 3

    def test_hub_tanks_count(self):
        """Hub mode should have 4 tanks (EQ×2, Off-Spec, Centrate)."""
        assert len(HUB_TANKS) == 4

    def test_gross_volume_formula(self):
        """Gross volume = π r² h."""
        t = TankGeometry(tag="T1", name="Test", diameter_m=2.0, straight_side_m=3.0)
        expected = math.pi * 1.0**2 * 3.0
        assert abs(t.volume_gross_m3 - expected) < 0.01

    def test_working_volume_less_than_gross(self):
        """Working volume should be less than gross (freeboard deducted)."""
        for t in PRODUCT_TANKS:
            assert t.volume_working_m3 < t.volume_gross_m3

    def test_footprint_includes_access(self):
        """Footprint with access should be diameter + 2 × 0.8m."""
        t = PRODUCT_TANKS[0]
        expected = t.diameter_m + 2 * 0.8
        assert abs(t.footprint_diameter_with_access - expected) < 0.01

    def test_bounding_box_centered(self):
        """Tank bounding box should be centered at given coordinates."""
        t = TankGeometry(tag="T1", name="Test", diameter_m=3.0, straight_side_m=4.0)
        box = t.get_bounding_box(5.0, 5.0)
        # Center at (5,5), radius 1.5 → box starts at (3.5, 3.5)
        assert abs(box.x_min - 3.5) < 0.01
        assert abs(box.y_min - 3.5) < 0.01
        assert abs(box.length - 3.0) < 0.01

    def test_access_envelope_larger(self):
        """Access envelope should be larger than tank bounding box."""
        t = PRODUCT_TANKS[0]
        tank_box = t.get_bounding_box(5.0, 5.0)
        access_box = t.get_access_envelope(5.0, 5.0)
        assert access_box.footprint_area > tank_box.footprint_area

    def test_all_tanks_positive_volume(self):
        """All tanks in both modes should have positive working volume."""
        for t in PRODUCT_TANKS + HUB_TANKS:
            assert t.volume_working_m3 > 0, f"{t.tag} has non-positive working volume"


# =============================================================================
# EQUIPMENT PLACEMENT TESTS
# =============================================================================

class TestEquipmentPlacement:
    """Test equipment placement geometry."""

    def test_bounding_box(self):
        """Equipment box should match origin + dimensions."""
        eq = EquipmentPlacement(
            tag="T1", name="Test", subsystem=Subsystem.UTILITIES,
            origin_x=2.0, origin_y=3.0, length_m=4.0, width_m=2.0, height_m=3.0,
        )
        box = eq.bounding_box
        assert box.x_min == 2.0
        assert box.y_min == 3.0
        assert box.x_max == 6.0
        assert box.y_max == 5.0

    def test_service_envelope_expands(self):
        """Service envelope should expand by clearance on all sides."""
        eq = EquipmentPlacement(
            tag="T1", name="Test", subsystem=Subsystem.UTILITIES,
            origin_x=5.0, origin_y=5.0, length_m=3.0, width_m=2.0, height_m=2.0,
            service_clearance_m=1.0,
        )
        svc = eq.service_envelope
        assert svc.x_min == 4.0
        assert svc.y_min == 4.0
        assert svc.length == 5.0  # 3 + 2*1
        assert svc.width == 4.0   # 2 + 2*1

    def test_pull_out_east(self):
        """East pull-out should extend X max."""
        eq = EquipmentPlacement(
            tag="T1", name="Test", subsystem=Subsystem.PYROLYSIS,
            origin_x=5.0, origin_y=5.0, length_m=4.0, width_m=2.0, height_m=3.0,
            pull_out_direction=PullOutDirection.EAST, pull_out_distance_m=2.0,
        )
        pull = eq.pull_out_envelope
        assert pull is not None
        assert pull.x_max == 5.0 + 4.0 + 2.0

    def test_pull_out_none(self):
        """No pull-out direction should return None."""
        eq = EquipmentPlacement(
            tag="T1", name="Test", subsystem=Subsystem.UTILITIES,
            origin_x=5.0, origin_y=5.0, length_m=3.0, width_m=2.0, height_m=2.0,
        )
        assert eq.pull_out_envelope is None

    def test_hot_zone_envelope(self):
        """Hot zone should expand equipment box by exclusion margin."""
        eq = EquipmentPlacement(
            tag="PY", name="Pyro", subsystem=Subsystem.PYROLYSIS,
            origin_x=10.0, origin_y=5.0, length_m=5.0, width_m=3.0, height_m=5.0,
            hot_zone_exclusion_m=2.0,
        )
        hot = eq.hot_zone_envelope
        assert hot is not None
        assert hot.x_min == 8.0   # 10 - 2
        assert hot.y_min == 3.0   # 5 - 2
        assert hot.length == 9.0  # 5 + 2*2

    def test_no_hot_zone_when_zero(self):
        """Equipment with zero hot zone should return None."""
        eq = EquipmentPlacement(
            tag="TK", name="Tank", subsystem=Subsystem.EQ_STORAGE,
            origin_x=1.0, origin_y=1.0, length_m=3.0, width_m=3.0, height_m=4.0,
        )
        assert eq.hot_zone_envelope is None


# =============================================================================
# ZONE TESTS
# =============================================================================

class TestZone:
    """Test zone definitions."""

    def test_zone_area(self):
        """Zone area = length × width."""
        z = Zone(name="Test", subsystem=Subsystem.RECEIVING,
                 origin_x=0, origin_y=0, length_m=10, width_m=5, height_m=4)
        assert z.area_m2 == 50.0

    def test_zone_bounding_box(self):
        """Zone bounding box should match origin + dimensions."""
        z = Zone(name="Test", subsystem=Subsystem.RECEIVING,
                 origin_x=2, origin_y=3, length_m=8, width_m=6, height_m=5)
        box = z.bounding_box
        assert box.x_min == 2
        assert box.y_max == 9
        assert box.z_max == 5

    def test_product_zones_cover_subsystems(self):
        """Product layout should cover key subsystems."""
        subsystems = {z.subsystem for z in PRODUCT_ZONES}
        assert Subsystem.RECEIVING in subsystems
        assert Subsystem.EQ_STORAGE in subsystems
        assert Subsystem.DEWATERING in subsystems
        assert Subsystem.PYROLYSIS in subsystems
        assert Subsystem.CHAR_HANDLING in subsystems

    def test_hub_zones_cover_subsystems(self):
        """Hub layout should cover key subsystems."""
        subsystems = {z.subsystem for z in HUB_ZONES}
        assert Subsystem.RECEIVING in subsystems
        assert Subsystem.EQ_STORAGE in subsystems
        assert Subsystem.DEWATERING in subsystems
        assert Subsystem.PYROLYSIS in subsystems
        assert Subsystem.CHAR_HANDLING in subsystems
        assert Subsystem.CENTRATE in subsystems
        assert Subsystem.OFF_SPEC in subsystems


# =============================================================================
# CONTAINMENT AREA TESTS
# =============================================================================

class TestContainmentArea:
    """Test containment area calculations."""

    def test_required_volume(self):
        """Required volume = tank × (1+freeboard) + rainfall + spill."""
        ca = ContainmentArea(
            name="Test",
            bounding_box=BoundingBox(0, 0, 0, 10, 10, 1),
            containment_type=ContainmentType.SEPARATE_BERM,
            tank_volume_m3=50.0,
            freeboard_fraction=0.10,
            rainfall_allowance_m3=2.0,
            spill_allowance_m3=1.0,
        )
        expected = 50 * 1.10 + 2.0 + 1.0  # 58.0
        assert abs(ca.required_volume_m3 - expected) < 0.01

    def test_berm_height(self):
        """Berm height = required_volume / footprint_area."""
        ca = ContainmentArea(
            name="Test",
            bounding_box=BoundingBox(0, 0, 0, 10, 10, 1),
            containment_type=ContainmentType.SEPARATE_BERM,
            tank_volume_m3=50.0,
        )
        # required = 50 * 1.10 = 55.0; area = 100; height = 0.55m
        assert abs(ca.berm_height_m - 0.55) < 0.01


# =============================================================================
# LAYOUT DATA INTEGRITY TESTS
# =============================================================================

class TestLayoutDataIntegrity:
    """Verify layout data is physically consistent."""

    def test_product_equipment_tags_unique(self):
        """All product equipment tags should be unique."""
        tags = [eq.tag for eq in PRODUCT_EQUIPMENT]
        assert len(tags) == len(set(tags)), f"Duplicate tags: {[t for t in tags if tags.count(t) > 1]}"

    def test_hub_equipment_tags_unique(self):
        """All hub equipment tags should be unique."""
        tags = [eq.tag for eq in HUB_EQUIPMENT]
        assert len(tags) == len(set(tags)), f"Duplicate tags: {[t for t in tags if tags.count(t) > 1]}"

    def test_product_equipment_nonnegative_origins(self):
        """All product equipment should have non-negative origins."""
        for eq in PRODUCT_EQUIPMENT:
            assert eq.origin_x >= 0, f"{eq.tag} has negative origin_x"
            assert eq.origin_y >= 0, f"{eq.tag} has negative origin_y"

    def test_hub_equipment_nonnegative_origins(self):
        """All hub equipment should have non-negative origins."""
        for eq in HUB_EQUIPMENT:
            assert eq.origin_x >= 0, f"{eq.tag} has negative origin_x"
            assert eq.origin_y >= 0, f"{eq.tag} has negative origin_y"

    def test_product_equipment_within_envelope(self):
        """All product equipment bounding boxes should fit within envelope."""
        env = PRODUCT_ENVELOPE
        for eq in PRODUCT_EQUIPMENT:
            box = eq.bounding_box
            assert box.x_max <= env.length_m, f"{eq.tag} exceeds X ({box.x_max} > {env.length_m})"
            assert box.y_max <= env.width_m, f"{eq.tag} exceeds Y ({box.y_max} > {env.width_m})"
            assert box.z_max <= env.height_m, f"{eq.tag} exceeds Z ({box.z_max} > {env.height_m})"

    def test_hub_equipment_within_envelope(self):
        """All hub equipment bounding boxes should fit within envelope."""
        env = HUB_ENVELOPE
        for eq in HUB_EQUIPMENT:
            box = eq.bounding_box
            assert box.x_max <= env.length_m, f"{eq.tag} exceeds X ({box.x_max} > {env.length_m})"
            assert box.y_max <= env.width_m, f"{eq.tag} exceeds Y ({box.y_max} > {env.width_m})"
            assert box.z_max <= env.height_m, f"{eq.tag} exceeds Z ({box.z_max} > {env.height_m})"

    def test_product_tank_tags_match_equipment(self):
        """Product tank tags should have matching equipment placements."""
        tank_tags = {t.tag for t in PRODUCT_TANKS}
        equip_tags = {eq.tag for eq in PRODUCT_EQUIPMENT}
        for tag in tank_tags:
            assert tag in equip_tags, f"Tank {tag} has no equipment placement"

    def test_hub_tank_tags_match_equipment(self):
        """Hub tank tags should have matching equipment placements."""
        tank_tags = {t.tag for t in HUB_TANKS}
        equip_tags = {eq.tag for eq in HUB_EQUIPMENT}
        for tag in tank_tags:
            assert tag in equip_tags, f"Tank {tag} has no equipment placement"

    def test_product_pyrolysis_has_hot_zone(self):
        """Product pyrolysis equipment should have hot zone exclusion."""
        pyro = [eq for eq in PRODUCT_EQUIPMENT if eq.subsystem == Subsystem.PYROLYSIS]
        assert len(pyro) > 0, "No pyrolysis equipment in product layout"
        for eq in pyro:
            assert eq.hot_zone_exclusion_m > 0, f"{eq.tag} pyrolysis missing hot zone"

    def test_hub_pyrolysis_has_hot_zone(self):
        """Hub pyrolysis equipment should have hot zone exclusion."""
        pyro = [eq for eq in HUB_EQUIPMENT if eq.subsystem == Subsystem.PYROLYSIS]
        assert len(pyro) > 0, "No pyrolysis equipment in hub layout"
        for eq in pyro:
            assert eq.hot_zone_exclusion_m > 0, f"{eq.tag} pyrolysis missing hot zone"

    def test_hub_has_more_equipment_than_product(self):
        """Hub should have more equipment items than product."""
        assert len(HUB_EQUIPMENT) > len(PRODUCT_EQUIPMENT)

    def test_hub_has_more_zones_than_product(self):
        """Hub should have more zones than product."""
        assert len(HUB_ZONES) > len(PRODUCT_ZONES)

    def test_hub_envelope_larger_than_product(self):
        """Hub footprint should be larger than product."""
        assert HUB_ENVELOPE.footprint_area > PRODUCT_ENVELOPE.footprint_area


# =============================================================================
# VALIDATION GATE TESTS
# =============================================================================

class TestValidateFacilityBounds:
    """Test facility bounds gate."""

    def test_product_layout_passes(self):
        """Current product layout should pass bounds gate."""
        result = validate_facility_bounds(PRODUCT_EQUIPMENT, PRODUCT_ENVELOPE)
        assert result.passed is True
        assert len(result.violations) == 0

    def test_hub_layout_passes(self):
        """Current hub layout should pass bounds gate."""
        result = validate_facility_bounds(HUB_EQUIPMENT, HUB_ENVELOPE)
        assert result.passed is True
        assert len(result.violations) == 0

    def test_oversized_equipment_fails(self):
        """Equipment exceeding envelope should fail."""
        oversized = (
            EquipmentPlacement(
                tag="BIG-1", name="Too Big", subsystem=Subsystem.UTILITIES,
                origin_x=0, origin_y=0, length_m=20, width_m=10, height_m=8,
            ),
        )
        result = validate_facility_bounds(oversized, PRODUCT_ENVELOPE)
        assert result.passed is False
        assert len(result.violations) > 0

    def test_negative_origin_fails(self):
        """Equipment with negative origin should fail."""
        neg = (
            EquipmentPlacement(
                tag="NEG-1", name="Neg", subsystem=Subsystem.UTILITIES,
                origin_x=-1, origin_y=0, length_m=2, width_m=2, height_m=2,
            ),
        )
        result = validate_facility_bounds(neg, PRODUCT_ENVELOPE)
        assert result.passed is False


class TestValidateClearanceOverlap:
    """Test clearance overlap gate."""

    def test_product_layout_passes(self):
        """Current product layout should have no service envelope overlaps."""
        result = validate_clearance_overlap(PRODUCT_EQUIPMENT)
        assert result.passed is True, f"Overlaps: {result.violations}"

    def test_hub_layout_passes(self):
        """Current hub layout should have no service envelope overlaps."""
        result = validate_clearance_overlap(HUB_EQUIPMENT)
        assert result.passed is True, f"Overlaps: {result.violations}"

    def test_overlapping_equipment_fails(self):
        """Equipment with overlapping service envelopes should fail."""
        eq1 = EquipmentPlacement(
            tag="A", name="A", subsystem=Subsystem.UTILITIES,
            origin_x=0, origin_y=0, length_m=3, width_m=3, height_m=2,
            service_clearance_m=1.0,
        )
        eq2 = EquipmentPlacement(
            tag="B", name="B", subsystem=Subsystem.UTILITIES,
            origin_x=2, origin_y=2, length_m=3, width_m=3, height_m=2,
            service_clearance_m=1.0,
        )
        result = validate_clearance_overlap((eq1, eq2))
        assert result.passed is False
        assert "A service envelope overlaps B" in result.violations[0]

    def test_well_spaced_equipment_passes(self):
        """Equipment with adequate spacing should pass."""
        eq1 = EquipmentPlacement(
            tag="A", name="A", subsystem=Subsystem.UTILITIES,
            origin_x=0, origin_y=0, length_m=2, width_m=2, height_m=2,
            service_clearance_m=0.5,
        )
        eq2 = EquipmentPlacement(
            tag="B", name="B", subsystem=Subsystem.UTILITIES,
            origin_x=5, origin_y=0, length_m=2, width_m=2, height_m=2,
            service_clearance_m=0.5,
        )
        result = validate_clearance_overlap((eq1, eq2))
        assert result.passed is True


class TestValidateHotZoneExclusion:
    """Test hot zone exclusion gate."""

    def test_product_layout_passes(self):
        """Current product layout should pass hot zone gate."""
        result = validate_hot_zone_exclusion(PRODUCT_EQUIPMENT)
        assert result.passed is True, f"Violations: {result.violations}"

    def test_hub_layout_passes(self):
        """Current hub layout should pass hot zone gate."""
        result = validate_hot_zone_exclusion(HUB_EQUIPMENT)
        assert result.passed is True, f"Violations: {result.violations}"

    def test_equipment_in_hot_zone_fails(self):
        """Non-pyro equipment inside hot zone should fail."""
        pyro = EquipmentPlacement(
            tag="PY", name="Pyro", subsystem=Subsystem.PYROLYSIS,
            origin_x=10, origin_y=10, length_m=5, width_m=3, height_m=5,
            hot_zone_exclusion_m=3.0,
        )
        # Place tank right next to pyro, inside hot zone
        tank = EquipmentPlacement(
            tag="TK", name="Tank", subsystem=Subsystem.EQ_STORAGE,
            origin_x=9, origin_y=10, length_m=2, width_m=2, height_m=3,
        )
        result = validate_hot_zone_exclusion((pyro, tank))
        assert result.passed is False
        assert "TK intersects PY hot zone" in result.violations[0]

    def test_equipment_outside_hot_zone_passes(self):
        """Equipment well clear of hot zone should pass."""
        pyro = EquipmentPlacement(
            tag="PY", name="Pyro", subsystem=Subsystem.PYROLYSIS,
            origin_x=10, origin_y=10, length_m=5, width_m=3, height_m=5,
            hot_zone_exclusion_m=2.0,
        )
        # Hot zone extends to x_min=8, so place tank at x=0 (well clear)
        tank = EquipmentPlacement(
            tag="TK", name="Tank", subsystem=Subsystem.EQ_STORAGE,
            origin_x=0, origin_y=0, length_m=3, width_m=3, height_m=4,
        )
        result = validate_hot_zone_exclusion((pyro, tank))
        assert result.passed is True


class TestValidateContainmentSeparation:
    """Test containment separation gate."""

    def test_product_layout_passes(self):
        """Product layout should pass containment gate."""
        result = validate_containment_separation(PRODUCT_EQUIPMENT, DeploymentMode.PRODUCT)
        assert result.passed is True

    def test_hub_layout_passes(self):
        """Hub layout should pass containment gate."""
        result = validate_containment_separation(HUB_EQUIPMENT, DeploymentMode.HUB)
        assert result.passed is True

    def test_hub_shared_slab_offspec_fails(self):
        """Hub off-spec with shared slab should fail (Rule C-1)."""
        bad_offspec = (
            EquipmentPlacement(
                tag="TK-202", name="Off-Spec", subsystem=Subsystem.OFF_SPEC,
                origin_x=5, origin_y=5, length_m=3, width_m=3, height_m=4,
                containment_type=ContainmentType.SHARED_SLAB,
            ),
        )
        result = validate_containment_separation(bad_offspec, DeploymentMode.HUB)
        assert result.passed is False
        assert "SEPARATE_BERM" in result.violations[0]

    def test_hub_shared_slab_centrate_fails(self):
        """Hub centrate with shared slab should fail (Rule C-1)."""
        bad_centrate = (
            EquipmentPlacement(
                tag="TK-203", name="Centrate", subsystem=Subsystem.CENTRATE,
                origin_x=5, origin_y=5, length_m=3, width_m=3, height_m=4,
                containment_type=ContainmentType.SHARED_SLAB,
            ),
        )
        result = validate_containment_separation(bad_centrate, DeploymentMode.HUB)
        assert result.passed is False

    def test_product_mode_allows_shared_slab(self):
        """Product mode should allow shared slab containment (Rule C-2)."""
        shared_offspec = (
            EquipmentPlacement(
                tag="TK-102", name="Off-Spec", subsystem=Subsystem.OFF_SPEC,
                origin_x=5, origin_y=5, length_m=3, width_m=3, height_m=4,
                containment_type=ContainmentType.SHARED_SLAB,
            ),
        )
        result = validate_containment_separation(shared_offspec, DeploymentMode.PRODUCT)
        assert result.passed is True


class TestRunLayoutGates:
    """Test the combined gate runner."""

    def test_product_all_gates_pass(self):
        """All 4 gates should pass for product layout."""
        gates = run_layout_gates(PRODUCT_EQUIPMENT, PRODUCT_ENVELOPE, DeploymentMode.PRODUCT)
        assert len(gates) == 4
        for g in gates:
            assert g.passed is True, f"Gate '{g.name}' failed: {g.violations}"

    def test_hub_all_gates_pass(self):
        """All 4 gates should pass for hub layout."""
        gates = run_layout_gates(HUB_EQUIPMENT, HUB_ENVELOPE, DeploymentMode.HUB)
        assert len(gates) == 4
        for g in gates:
            assert g.passed is True, f"Gate '{g.name}' failed: {g.violations}"

    def test_gate_result_structure(self):
        """Gate results should have name, passed, details, violations."""
        gates = run_layout_gates(PRODUCT_EQUIPMENT, PRODUCT_ENVELOPE, DeploymentMode.PRODUCT)
        for g in gates:
            assert isinstance(g.name, str)
            assert isinstance(g.passed, bool)
            assert isinstance(g.details, str)
            assert isinstance(g.violations, list)


# =============================================================================
# CROSS-MODULE CONSISTENCY TESTS
# =============================================================================

class TestCrossModuleConsistency:
    """Verify consistency between facility_geometry and facility_design."""

    def test_deployment_mode_values_match(self):
        """DeploymentMode in geometry should have same values as design."""
        from septage_model.artifacts.facility_design import (
            DeploymentMode as DesignMode,
        )
        assert DeploymentMode.PRODUCT.value == DesignMode.PRODUCT.value
        assert DeploymentMode.HUB.value == DesignMode.HUB.value

    def test_product_pyro_tag_matches_design(self):
        """Product pyrolysis tag PY-101 should exist in both modules."""
        from septage_model.artifacts.facility_design import PRODUCT_MODE_EQUIPMENT
        design_tags = {eq.tag for eq in PRODUCT_MODE_EQUIPMENT}
        geom_pyro_tags = {eq.tag for eq in PRODUCT_EQUIPMENT if eq.subsystem == Subsystem.PYROLYSIS}
        assert "PY-101" in geom_pyro_tags
        assert "PY-101" in design_tags

    def test_hub_pyro_tag_matches_design(self):
        """Hub pyrolysis tag PY-201 should exist in both modules."""
        from septage_model.artifacts.facility_design import HUB_MODE_EQUIPMENT
        design_tags = {eq.tag for eq in HUB_MODE_EQUIPMENT}
        geom_pyro_tags = {eq.tag for eq in HUB_EQUIPMENT if eq.subsystem == Subsystem.PYROLYSIS}
        assert "PY-201" in geom_pyro_tags
        assert "PY-201" in design_tags

    def test_product_tank_tags_in_design(self):
        """Product tank tags should appear in facility_design equipment list."""
        from septage_model.artifacts.facility_design import PRODUCT_MODE_EQUIPMENT
        design_tags = {eq.tag for eq in PRODUCT_MODE_EQUIPMENT}
        for tank in PRODUCT_TANKS:
            assert tank.tag in design_tags, f"Tank {tank.tag} missing from facility_design"

    def test_hub_tank_tags_in_design(self):
        """Hub tank tags should appear in facility_design equipment list."""
        from septage_model.artifacts.facility_design import HUB_MODE_EQUIPMENT
        design_tags = {eq.tag for eq in HUB_MODE_EQUIPMENT}
        for tank in HUB_TANKS:
            assert tank.tag in design_tags, f"Tank {tank.tag} missing from facility_design"

    def test_product_dewatering_tag_matches(self):
        """DW-101 should exist in both geometry and design."""
        from septage_model.artifacts.facility_design import PRODUCT_MODE_EQUIPMENT
        design_tags = {eq.tag for eq in PRODUCT_MODE_EQUIPMENT}
        geom_tags = {eq.tag for eq in PRODUCT_EQUIPMENT}
        assert "DW-101" in geom_tags
        assert "DW-101" in design_tags

    def test_hub_dewatering_tag_matches(self):
        """DW-201 should exist in both geometry and design."""
        from septage_model.artifacts.facility_design import HUB_MODE_EQUIPMENT
        design_tags = {eq.tag for eq in HUB_MODE_EQUIPMENT}
        geom_tags = {eq.tag for eq in HUB_EQUIPMENT}
        assert "DW-201" in geom_tags
        assert "DW-201" in design_tags


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
