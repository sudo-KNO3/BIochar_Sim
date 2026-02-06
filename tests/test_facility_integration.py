"""
Tests for Facility XYZ Integration — Vendor Cut-Sheet Pipeline,
Overnight ↔ Geometry Bridge, GATE-04 Programmatic Enforcement,
and Module Export Integrity.

Covers:
- Vendor cut-sheet reconciliation: valid, invalid, smaller/larger than conservative
- Overnight hot zone: multipliers, continuous heat override, geometry gate
- GATE-04 enforcement: DRL screening vs DRL-4+ blocking, philosophy checks
- Site concept gates: programmatic runner for Product and Hub
- Module exports: all new types accessible from septage_model.artifacts
"""

import pytest

from septage_model.artifacts.facility_geometry import (
    # Core types
    DeploymentMode,
    BoundingBox,
    FacilityEnvelope,
    ReactorEnvelopeParams,
    EquipmentPlacement,
    LayoutGateResult,
    # Vendor cut-sheet pipeline
    VendorCutSheetData,
    CutSheetReconciliation,
    derive_envelope_from_vendor_cut_sheet,
    # Overnight bridge
    OVERNIGHT_HOT_ZONE_MULTIPLIERS,
    get_overnight_hot_zone_exclusion,
    validate_overnight_geometry,
    # Constants
    PRODUCT_REACTOR_ENVELOPE,
    HUB_REACTOR_ENVELOPE,
    PRODUCT_EQUIPMENT,
    HUB_EQUIPMENT,
)

from septage_model.artifacts.facility_design import (
    DeploymentMode as FD_DeploymentMode,
    GateCheckResult,
    SiteConceptGate,
    SITE_CONCEPT_GATES,
    check_gate04_unattended_safety,
    check_site_concept_gates_programmatic,
    get_applicable_gates,
)


# =============================================================================
# VENDOR CUT-SHEET DATA VALIDATION
# =============================================================================

class TestVendorCutSheetData:
    """Test VendorCutSheetData validation and structure."""

    def _make_valid_cutsheet(self, **overrides) -> VendorCutSheetData:
        defaults = dict(
            vendor_id="vendor-A",
            model_number="RX-100",
            skid_length_m=5.5,
            skid_width_m=2.2,
            skid_height_m=4.5,
            clearance_inlet_m=1.3,
            clearance_outlet_m=1.8,
            clearance_overhead_m=0.8,
            hot_zone_exclusion_m=1.2,
            drawing_ref="DWG-001",
            date_received="2025-07-15",
        )
        defaults.update(overrides)
        return VendorCutSheetData(**defaults)

    def test_valid_cutsheet_no_issues(self):
        """Valid cut-sheet should have no validation issues."""
        cs = self._make_valid_cutsheet()
        assert cs.validate() == []

    def test_vendor_id_stored(self):
        """Vendor ID should be accessible."""
        cs = self._make_valid_cutsheet(vendor_id="pyro-tech-9000")
        assert cs.vendor_id == "pyro-tech-9000"

    def test_negative_length_fails(self):
        """Negative skid length should produce validation error."""
        cs = self._make_valid_cutsheet(skid_length_m=-1.0)
        issues = cs.validate()
        assert len(issues) == 1
        assert "skid_length_m" in issues[0]

    def test_zero_width_fails(self):
        """Zero skid width should produce validation error."""
        cs = self._make_valid_cutsheet(skid_width_m=0.0)
        issues = cs.validate()
        assert len(issues) == 1
        assert "skid_width_m" in issues[0]

    def test_negative_clearance_fails(self):
        """Negative clearance should produce validation error."""
        cs = self._make_valid_cutsheet(clearance_inlet_m=-0.5)
        issues = cs.validate()
        assert len(issues) == 1
        assert "clearance_inlet_m" in issues[0]

    def test_negative_hot_zone_fails(self):
        """Negative hot zone exclusion should produce validation error."""
        cs = self._make_valid_cutsheet(hot_zone_exclusion_m=-1.0)
        issues = cs.validate()
        assert len(issues) == 1
        assert "hot_zone_exclusion_m" in issues[0]

    def test_multiple_issues_reported(self):
        """Multiple dimension errors should all be reported."""
        cs = self._make_valid_cutsheet(
            skid_length_m=-1.0,
            skid_width_m=-2.0,
            skid_height_m=-3.0,
        )
        issues = cs.validate()
        assert len(issues) == 3

    def test_zero_clearance_valid(self):
        """Zero clearance is allowed (butted against wall)."""
        cs = self._make_valid_cutsheet(clearance_inlet_m=0.0, clearance_outlet_m=0.0)
        assert cs.validate() == []


# =============================================================================
# DERIVE ENVELOPE FROM VENDOR CUT-SHEET
# =============================================================================

class TestDeriveEnvelopeFromVendorCutSheet:
    """Test vendor cut-sheet → ReactorEnvelopeParams pipeline."""

    def _make_cutsheet(self, **overrides) -> VendorCutSheetData:
        defaults = dict(
            vendor_id="vendor-A",
            model_number="RX-100",
            skid_length_m=5.5,
            skid_width_m=2.2,
            skid_height_m=4.5,
            clearance_inlet_m=1.3,
            clearance_outlet_m=1.8,
            clearance_overhead_m=0.8,
            hot_zone_exclusion_m=1.2,
        )
        defaults.update(overrides)
        return VendorCutSheetData(**defaults)

    def test_valid_cutsheet_returns_validated_envelope(self):
        """Derived envelope should have validated_by_vendor=True."""
        cs = self._make_cutsheet()
        env, rec = derive_envelope_from_vendor_cut_sheet(cs, PRODUCT_REACTOR_ENVELOPE)
        assert env.validated_by_vendor is True
        assert env.vendor_id == "vendor-A"

    def test_dimensions_match_cutsheet(self):
        """Derived envelope dimensions should match cut-sheet."""
        cs = self._make_cutsheet(skid_length_m=5.5, skid_width_m=2.2, skid_height_m=4.5)
        env, _ = derive_envelope_from_vendor_cut_sheet(cs, PRODUCT_REACTOR_ENVELOPE)
        assert env.footprint_L_m == 5.5
        assert env.footprint_W_m == 2.2
        assert env.height_m == 4.5

    def test_clearances_match_cutsheet(self):
        """Derived envelope clearances should match cut-sheet."""
        cs = self._make_cutsheet(clearance_inlet_m=1.3, clearance_outlet_m=1.8)
        env, _ = derive_envelope_from_vendor_cut_sheet(cs, PRODUCT_REACTOR_ENVELOPE)
        assert env.service_clearance_inlet_m == 1.3
        assert env.service_clearance_outlet_m == 1.8

    def test_smaller_vendor_fits_conservative(self):
        """Vendor smaller than conservative should fit and not require revalidation."""
        cs = self._make_cutsheet(
            skid_length_m=5.0,  # < 6.0 conservative
            skid_width_m=2.0,   # < 2.5 conservative
            skid_height_m=4.0,  # < 5.0 conservative
            hot_zone_exclusion_m=1.0,  # < 1.5 conservative
        )
        _, rec = derive_envelope_from_vendor_cut_sheet(cs, PRODUCT_REACTOR_ENVELOPE)
        assert rec.fits_conservative_footprint is True
        assert rec.requires_layout_revalidation is False

    def test_larger_vendor_requires_revalidation(self):
        """Vendor larger than conservative should flag revalidation."""
        cs = self._make_cutsheet(
            skid_length_m=7.0,  # > 6.0 conservative
            skid_width_m=3.0,   # > 2.5 conservative
            skid_height_m=6.0,  # > 5.0 conservative
        )
        _, rec = derive_envelope_from_vendor_cut_sheet(cs, PRODUCT_REACTOR_ENVELOPE)
        assert rec.fits_conservative_footprint is False
        assert rec.requires_layout_revalidation is True

    def test_larger_hot_zone_requires_revalidation(self):
        """Vendor with larger hot zone should require revalidation even if fits footprint."""
        cs = self._make_cutsheet(
            skid_length_m=5.0,  # smaller
            skid_width_m=2.0,   # smaller
            skid_height_m=4.0,  # smaller
            hot_zone_exclusion_m=2.0,  # > 1.5 conservative
        )
        _, rec = derive_envelope_from_vendor_cut_sheet(cs, PRODUCT_REACTOR_ENVELOPE)
        assert rec.fits_conservative_footprint is True
        assert rec.requires_layout_revalidation is True  # Hot zone grew

    def test_deltas_computed_correctly(self):
        """Reconciliation deltas should be vendor - conservative."""
        cs = self._make_cutsheet(
            skid_length_m=7.0,
            skid_width_m=3.0,
            skid_height_m=4.0,
            hot_zone_exclusion_m=2.0,
        )
        _, rec = derive_envelope_from_vendor_cut_sheet(cs, PRODUCT_REACTOR_ENVELOPE)
        assert rec.delta_length_m == pytest.approx(1.0, abs=0.01)   # 7.0 - 6.0
        assert rec.delta_width_m == pytest.approx(0.5, abs=0.01)    # 3.0 - 2.5
        assert rec.delta_height_m == pytest.approx(-1.0, abs=0.01)  # 4.0 - 5.0
        assert rec.delta_hot_zone_m == pytest.approx(0.5, abs=0.01) # 2.0 - 1.5

    def test_invalid_cutsheet_raises_valueerror(self):
        """Invalid cut-sheet should raise ValueError."""
        cs = self._make_cutsheet(skid_length_m=-1.0)
        with pytest.raises(ValueError, match="Vendor cut-sheet validation failed"):
            derive_envelope_from_vendor_cut_sheet(cs, PRODUCT_REACTOR_ENVELOPE)

    def test_hub_envelope_reconciliation(self):
        """Hub reconciliation should use HUB_REACTOR_ENVELOPE as baseline."""
        cs = self._make_cutsheet(
            skid_length_m=8.0,   # < 9.0 hub conservative
            skid_width_m=2.5,    # < 3.0 hub conservative
            skid_height_m=5.5,   # < 6.0 hub conservative
            hot_zone_exclusion_m=1.5,  # < 2.0 hub conservative
        )
        _, rec = derive_envelope_from_vendor_cut_sheet(cs, HUB_REACTOR_ENVELOPE)
        assert rec.fits_conservative_footprint is True
        assert rec.requires_layout_revalidation is False
        assert rec.delta_length_m == pytest.approx(-1.0, abs=0.01)

    def test_exact_match_fits(self):
        """Vendor matching conservative exactly should fit without revalidation."""
        cs = self._make_cutsheet(
            skid_length_m=6.0,
            skid_width_m=2.5,
            skid_height_m=5.0,
            clearance_inlet_m=1.5,
            clearance_outlet_m=2.0,
            clearance_overhead_m=1.0,
            hot_zone_exclusion_m=1.5,
        )
        _, rec = derive_envelope_from_vendor_cut_sheet(cs, PRODUCT_REACTOR_ENVELOPE)
        assert rec.fits_conservative_footprint is True
        assert rec.requires_layout_revalidation is False
        assert rec.delta_length_m == 0.0


# =============================================================================
# OVERNIGHT HOT ZONE MULTIPLIERS
# =============================================================================

class TestOvernightHotZoneMultipliers:
    """Test overnight hot zone exclusion calculations."""

    def test_hold_mode_full_exclusion(self):
        """Hold mode should maintain full hot zone."""
        assert get_overnight_hot_zone_exclusion(2.0, "hold") == 2.0

    def test_controlled_cooldown_reduced(self):
        """Controlled cooldown should reduce to 75%."""
        result = get_overnight_hot_zone_exclusion(2.0, "controlled_cooldown")
        assert result == pytest.approx(1.5, abs=0.01)

    def test_full_shutdown_halved(self):
        """Full shutdown should reduce to 50%."""
        result = get_overnight_hot_zone_exclusion(2.0, "full_shutdown")
        assert result == pytest.approx(1.0, abs=0.01)

    def test_unknown_conservative(self):
        """Unknown mode should use conservative (full) exclusion."""
        assert get_overnight_hot_zone_exclusion(2.0, "unknown") == 2.0

    def test_continuous_heat_overrides_mode(self):
        """Continuous heat required should always use full exclusion."""
        assert get_overnight_hot_zone_exclusion(2.0, "full_shutdown", continuous_heat_required=True) == 2.0
        assert get_overnight_hot_zone_exclusion(2.0, "controlled_cooldown", continuous_heat_required=True) == 2.0

    def test_zero_base_returns_zero(self):
        """Zero base exclusion should return zero regardless of mode."""
        assert get_overnight_hot_zone_exclusion(0.0, "hold") == 0.0

    def test_multiplier_dict_keys(self):
        """All expected modes should be in the multiplier dict."""
        expected = {"hold", "controlled_cooldown", "full_shutdown", "unknown"}
        assert set(OVERNIGHT_HOT_ZONE_MULTIPLIERS.keys()) == expected

    def test_all_multipliers_in_range(self):
        """All multipliers should be between 0 and 1 inclusive."""
        for mode, mult in OVERNIGHT_HOT_ZONE_MULTIPLIERS.items():
            assert 0 <= mult <= 1.0, f"{mode} multiplier {mult} out of range"

    def test_unrecognized_mode_conservative(self):
        """Unrecognized mode should default to conservative (1.0)."""
        result = get_overnight_hot_zone_exclusion(2.0, "some_future_mode")
        assert result == 2.0  # Falls back to 1.0 multiplier


# =============================================================================
# VALIDATE OVERNIGHT GEOMETRY GATE
# =============================================================================

class TestValidateOvernightGeometry:
    """Test overnight hot zone geometry validation gate."""

    def test_product_hold_mode_passes(self):
        """Product layout should pass overnight hot zone check in hold mode."""
        result = validate_overnight_geometry(PRODUCT_EQUIPMENT, "hold")
        assert isinstance(result, LayoutGateResult)
        assert result.passed is True
        assert result.name == "Overnight Hot Zone Clearance"

    def test_hub_hold_mode_passes(self):
        """Hub layout should pass overnight hot zone check in hold mode."""
        result = validate_overnight_geometry(HUB_EQUIPMENT, "hold")
        assert result.passed is True

    def test_product_full_shutdown_passes(self):
        """Product in full shutdown should have reduced exclusion, should pass."""
        result = validate_overnight_geometry(PRODUCT_EQUIPMENT, "full_shutdown")
        assert result.passed is True

    def test_hub_full_shutdown_passes(self):
        """Hub in full shutdown should pass (reduced exclusion)."""
        result = validate_overnight_geometry(HUB_EQUIPMENT, "full_shutdown")
        assert result.passed is True

    def test_unknown_mode_conservative(self):
        """Unknown mode should use conservative (full) exclusion."""
        result = validate_overnight_geometry(PRODUCT_EQUIPMENT, "unknown")
        assert result.passed is True
        assert "unknown (conservative)" in result.details

    def test_continuous_heat_noted_in_details(self):
        """Continuous heat flag should appear in gate details."""
        result = validate_overnight_geometry(PRODUCT_EQUIPMENT, "hold", continuous_heat_required=True)
        assert "heat_required: True" in result.details

    def test_overlapping_equipment_fails(self):
        """Equipment placed inside another's hot zone should fail."""
        # Create equipment where non-pyro is inside pyro's hot zone
        pyro = EquipmentPlacement(
            tag="PY-TEST",
            name="Test Pyrolysis",
            subsystem=DeploymentMode.PRODUCT,  # doesn't matter for this test
            origin_x=5.0,
            origin_y=5.0,
            length_m=3.0,
            width_m=2.0,
            height_m=4.0,
            hot_zone_exclusion_m=3.0,  # Large hot zone
        )
        # Place tank inside the hot zone
        tank = EquipmentPlacement(
            tag="TK-TEST",
            name="Test Tank",
            subsystem=DeploymentMode.PRODUCT,
            origin_x=6.0,  # Inside pyro's hot zone (5-3=2 to 8+3=11)
            origin_y=6.0,
            length_m=1.0,
            width_m=1.0,
            height_m=2.0,
            hot_zone_exclusion_m=0.0,  # Not a hot source
        )
        result = validate_overnight_geometry((pyro, tank), "hold")
        assert result.passed is False
        assert len(result.violations) == 1
        assert "TK-TEST" in result.violations[0]

    def test_empty_equipment_passes(self):
        """Empty equipment list should pass trivially."""
        result = validate_overnight_geometry((), "hold")
        assert result.passed is True
        assert len(result.violations) == 0


# =============================================================================
# GATE-04 UNATTENDED SAFETY
# =============================================================================

class TestGate04UnattendedSafety:
    """Test GATE-04 programmatic enforcement."""

    def test_gate04_exists_in_site_concept_gates(self):
        """GATE-04 should exist in SITE_CONCEPT_GATES."""
        gate_ids = {g.id for g in SITE_CONCEPT_GATES}
        assert "GATE-04" in gate_ids

    def test_gate04_hub_only(self):
        """GATE-04 should apply only to Hub mode."""
        gate = next(g for g in SITE_CONCEPT_GATES if g.id == "GATE-04")
        assert FD_DeploymentMode.HUB in gate.applies_to
        assert len(gate.applies_to) == 1  # Hub only

    def test_drl3_always_passes(self):
        """DRL-3 should always pass GATE-04 (screening level)."""
        result = check_gate04_unattended_safety(
            overnight_mode="unknown",
            overnight_status="unknown",
            shutdown_philosophy="unknown",
            claimed_drl=3,
        )
        assert isinstance(result, GateCheckResult)
        assert result.passed is True
        assert result.gate_id == "GATE-04"

    def test_drl3_with_warnings(self):
        """DRL-3 pass should include warnings for unvalidated fields."""
        result = check_gate04_unattended_safety(
            overnight_mode="unknown",
            overnight_status="unknown",
            shutdown_philosophy="unknown",
            claimed_drl=3,
        )
        assert "advisory" in result.details.lower() or "screening" in result.details.lower()

    def test_drl4_unknown_blocks(self):
        """DRL-4 with unknown overnight status should BLOCK."""
        result = check_gate04_unattended_safety(
            overnight_mode="unknown",
            overnight_status="unknown",
            shutdown_philosophy="unknown",
            claimed_drl=4,
        )
        assert result.passed is False
        assert result.remediation is not None
        assert "GATE-04" in result.remediation

    def test_drl4_validated_passes(self):
        """DRL-4 with validated overnight and proper shutdown should pass."""
        result = check_gate04_unattended_safety(
            overnight_mode="hold",
            overnight_status="validated",
            shutdown_philosophy="auto_shutdown",
            claimed_drl=4,
        )
        assert result.passed is True
        assert result.remediation is None

    def test_drl5_validated_passes(self):
        """DRL-5 with validated overnight should pass."""
        result = check_gate04_unattended_safety(
            overnight_mode="controlled_cooldown",
            overnight_status="validated",
            shutdown_philosophy="auto_rampdown",
            claimed_drl=5,
        )
        assert result.passed is True

    def test_drl4_partial_status_blocks(self):
        """DRL-4 with partial status should block."""
        result = check_gate04_unattended_safety(
            overnight_mode="hold",
            overnight_status="partial",
            shutdown_philosophy="auto_shutdown",
            claimed_drl=4,
        )
        assert result.passed is False
        assert "overnight_status" in result.remediation

    def test_drl4_unknown_philosophy_blocks(self):
        """DRL-4 with unknown shutdown philosophy should block."""
        result = check_gate04_unattended_safety(
            overnight_mode="hold",
            overnight_status="validated",
            shutdown_philosophy="unknown",
            claimed_drl=4,
        )
        assert result.passed is False
        assert "shutdown_philosophy" in result.remediation

    def test_continuous_heat_alarm_only_blocks(self):
        """Continuous heat + alarm_only should block (no auto safe state)."""
        result = check_gate04_unattended_safety(
            overnight_mode="hold",
            overnight_status="validated",
            shutdown_philosophy="alarm_only",
            claimed_drl=4,
            continuous_heat_required=True,
        )
        assert result.passed is False
        assert "continuous_heat_required" in result.remediation

    def test_continuous_heat_auto_shutdown_passes(self):
        """Continuous heat + auto_shutdown should pass (automatic safe state)."""
        result = check_gate04_unattended_safety(
            overnight_mode="hold",
            overnight_status="validated",
            shutdown_philosophy="auto_shutdown",
            claimed_drl=4,
            continuous_heat_required=True,
        )
        assert result.passed is True

    def test_continuous_heat_hybrid_passes(self):
        """Continuous heat + hybrid philosophy should pass."""
        result = check_gate04_unattended_safety(
            overnight_mode="hold",
            overnight_status="validated",
            shutdown_philosophy="hybrid",
            claimed_drl=4,
            continuous_heat_required=True,
        )
        assert result.passed is True

    def test_drl2_always_passes(self):
        """DRL-2 should pass regardless of inputs."""
        result = check_gate04_unattended_safety(
            overnight_mode="unknown",
            overnight_status="unknown",
            shutdown_philosophy="unknown",
            claimed_drl=2,
        )
        assert result.passed is True

    def test_drl1_always_passes(self):
        """DRL-1 should pass regardless."""
        result = check_gate04_unattended_safety(
            overnight_mode="unknown",
            overnight_status="unknown",
            shutdown_philosophy="unknown",
            claimed_drl=1,
        )
        assert result.passed is True


# =============================================================================
# SITE CONCEPT GATES PROGRAMMATIC RUNNER
# =============================================================================

class TestSiteConceptGatesProgrammatic:
    """Test the programmatic site concept gate runner."""

    def test_hub_mode_returns_gate04(self):
        """Hub mode should include GATE-04 result."""
        results = check_site_concept_gates_programmatic(
            mode=FD_DeploymentMode.HUB,
            claimed_drl=4,
            overnight_mode="hold",
            overnight_status="validated",
            shutdown_philosophy="auto_shutdown",
        )
        gate_ids = [r.gate_id for r in results]
        assert "GATE-04" in gate_ids

    def test_product_mode_no_gate04(self):
        """Product mode should NOT include GATE-04 (it's Hub-only)."""
        results = check_site_concept_gates_programmatic(
            mode=FD_DeploymentMode.PRODUCT,
            claimed_drl=4,
        )
        gate_ids = [r.gate_id for r in results]
        assert "GATE-04" not in gate_ids

    def test_hub_drl3_all_pass(self):
        """Hub at DRL-3 should pass all programmatic gates."""
        results = check_site_concept_gates_programmatic(
            mode=FD_DeploymentMode.HUB,
            claimed_drl=3,
        )
        for r in results:
            assert r.passed is True

    def test_hub_drl4_unvalidated_blocks(self):
        """Hub at DRL-4 with defaults should block on GATE-04."""
        results = check_site_concept_gates_programmatic(
            mode=FD_DeploymentMode.HUB,
            claimed_drl=4,
        )
        gate04 = [r for r in results if r.gate_id == "GATE-04"]
        assert len(gate04) == 1
        assert gate04[0].passed is False

    def test_results_are_gate_check_results(self):
        """All results should be GateCheckResult instances."""
        results = check_site_concept_gates_programmatic(
            mode=FD_DeploymentMode.HUB,
            claimed_drl=4,
        )
        for r in results:
            assert isinstance(r, GateCheckResult)


# =============================================================================
# MODULE EXPORT INTEGRITY
# =============================================================================

class TestModuleExports:
    """Verify all new types are accessible from septage_model.artifacts."""

    def test_vendor_cutsheet_importable(self):
        """VendorCutSheetData should be importable from artifacts."""
        from septage_model.artifacts import VendorCutSheetData as VCS
        assert VCS is not None

    def test_cut_sheet_reconciliation_importable(self):
        """CutSheetReconciliation should be importable from artifacts."""
        from septage_model.artifacts import CutSheetReconciliation as CSR
        assert CSR is not None

    def test_derive_envelope_importable(self):
        """derive_envelope_from_vendor_cut_sheet should be importable."""
        from septage_model.artifacts import derive_envelope_from_vendor_cut_sheet as fn
        assert callable(fn)

    def test_overnight_multipliers_importable(self):
        """OVERNIGHT_HOT_ZONE_MULTIPLIERS should be importable."""
        from septage_model.artifacts import OVERNIGHT_HOT_ZONE_MULTIPLIERS as mult
        assert isinstance(mult, dict)

    def test_overnight_exclusion_fn_importable(self):
        """get_overnight_hot_zone_exclusion should be importable."""
        from septage_model.artifacts import get_overnight_hot_zone_exclusion as fn
        assert callable(fn)

    def test_validate_overnight_geometry_importable(self):
        """validate_overnight_geometry should be importable."""
        from septage_model.artifacts import validate_overnight_geometry as fn
        assert callable(fn)

    def test_gate_check_result_importable(self):
        """GateCheckResult should be importable."""
        from septage_model.artifacts import GateCheckResult as GCR
        assert GCR is not None

    def test_check_gate04_importable(self):
        """check_gate04_unattended_safety should be importable."""
        from septage_model.artifacts import check_gate04_unattended_safety as fn
        assert callable(fn)

    def test_check_programmatic_gates_importable(self):
        """check_site_concept_gates_programmatic should be importable."""
        from septage_model.artifacts import check_site_concept_gates_programmatic as fn
        assert callable(fn)

    def test_existing_exports_still_work(self):
        """Existing exports should still be accessible (no regression)."""
        from septage_model.artifacts import (
            FailureMode,
            SemanticVersion,
            ValidationTask,
            VendorPacket,
            Vendor,
            DecisionSnapshot,
        )
        assert FailureMode is not None
        assert SemanticVersion is not None

    def test_all_list_includes_new_exports(self):
        """__all__ should contain new export names."""
        from septage_model.artifacts import __all__ as all_exports
        new_names = [
            "VendorCutSheetData",
            "CutSheetReconciliation",
            "derive_envelope_from_vendor_cut_sheet",
            "OVERNIGHT_HOT_ZONE_MULTIPLIERS",
            "get_overnight_hot_zone_exclusion",
            "validate_overnight_geometry",
            "GateCheckResult",
            "check_gate04_unattended_safety",
            "check_site_concept_gates_programmatic",
        ]
        for name in new_names:
            assert name in all_exports, f"{name} missing from __all__"


# =============================================================================
# CROSS-MODULE INTEGRATION
# =============================================================================

class TestCrossModuleIntegration:
    """Test interactions between geometry, design, and overnight systems."""

    def test_vendor_envelope_produces_valid_equipment_box(self):
        """Vendor-derived envelope should produce valid BoundingBox."""
        cs = VendorCutSheetData(
            vendor_id="vendor-B",
            model_number="RX-200",
            skid_length_m=5.0,
            skid_width_m=2.0,
            skid_height_m=4.0,
            clearance_inlet_m=1.0,
            clearance_outlet_m=1.5,
            clearance_overhead_m=0.5,
            hot_zone_exclusion_m=1.0,
        )
        env, _ = derive_envelope_from_vendor_cut_sheet(cs, PRODUCT_REACTOR_ENVELOPE)
        box = env.get_equipment_box(1.0, 2.0)
        assert box.x_min == 1.0
        assert box.y_min == 2.0
        assert box.length == 5.0
        assert box.width == 2.0
        assert isinstance(box, BoundingBox)

    def test_overnight_gate_with_hold_mode_product(self):
        """Product layout under hold mode should pass overnight geometry gate."""
        result = validate_overnight_geometry(PRODUCT_EQUIPMENT, "hold")
        assert result.passed is True

    def test_overnight_gate_with_hold_mode_hub(self):
        """Hub layout under hold mode should pass overnight geometry gate."""
        result = validate_overnight_geometry(HUB_EQUIPMENT, "hold")
        assert result.passed is True

    def test_gate04_plus_overnight_geometry_consistency(self):
        """If GATE-04 passes, overnight geometry should also pass for real layouts."""
        # Scenario: validated hub, DRL-4, hold mode
        gate_result = check_gate04_unattended_safety(
            overnight_mode="hold",
            overnight_status="validated",
            shutdown_philosophy="auto_shutdown",
            claimed_drl=4,
        )
        geom_result = validate_overnight_geometry(HUB_EQUIPMENT, "hold")
        
        # Both should pass for the real hub layout
        assert gate_result.passed is True
        assert geom_result.passed is True

    def test_conservative_envelope_fits_real_equipment(self):
        """Product pyro equipment should fit within PRODUCT_REACTOR_ENVELOPE."""
        pyro = next(eq for eq in PRODUCT_EQUIPMENT if eq.tag == "PY-101")
        # Equipment placement must fit inside conservative envelope
        assert pyro.length_m <= PRODUCT_REACTOR_ENVELOPE.footprint_L_m
        assert pyro.width_m <= PRODUCT_REACTOR_ENVELOPE.footprint_W_m
        assert pyro.height_m <= PRODUCT_REACTOR_ENVELOPE.height_m

    def test_hub_conservative_envelope_matches_real_equipment(self):
        """Hub pyro equipment should match HUB_REACTOR_ENVELOPE dimensions."""
        pyro = next(eq for eq in HUB_EQUIPMENT if eq.tag == "PY-201")
        assert pyro.length_m == HUB_REACTOR_ENVELOPE.footprint_L_m
        assert pyro.width_m == HUB_REACTOR_ENVELOPE.footprint_W_m
        assert pyro.height_m == HUB_REACTOR_ENVELOPE.height_m


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
