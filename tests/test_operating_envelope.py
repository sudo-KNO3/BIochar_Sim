"""
Tests for Operating Envelope Specification.

Covers:
- Envelope defaults and constraint values
- Boundary condition checks (at/above/below limits)
- Throughput, temperature, TS, residence time constraints
- Overnight state allowance and temperature safety
- Energy self-sufficiency constraints
- Hard vs soft violation classification
- CI gate integration
- Custom envelope overrides
"""

import pytest
from septage_model.core.parameters import (
    OperatingEnvelope,
    OvernightState,
    OPERATING_ENVELOPE_DEFAULT,
    ModelParameters,
)
from septage_model.core.thermal_feasibility import (
    check_operating_envelope,
    EnvelopeCheckResult,
    EnvelopeViolation,
)
from septage_model.ci.gates import operating_envelope_gate


# =============================================================================
# ENVELOPE DEFAULTS
# =============================================================================

class TestEnvelopeDefaults:
    """Test that default envelope values are physically reasonable."""
    
    def test_default_throughput_range(self):
        """Throughput range should span reasonable pyrolysis capacity."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert env.min_throughput_kgds_hr == 10.0
        assert env.max_throughput_kgds_hr == 50.0
        assert env.turndown_ratio == 0.20
    
    def test_default_temperature_range(self):
        """Temperature range should cover viable pyrolysis window."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert env.min_wall_temperature_c == 450.0
        assert env.max_wall_temperature_c == 750.0
        assert env.target_wall_temperature_c == 650.0
    
    def test_default_residence_time_range(self):
        """Residence time range should ensure adequate conversion."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert env.min_residence_time_s == 600.0   # 10 min
        assert env.max_residence_time_s == 3600.0  # 60 min
        assert env.target_residence_time_s == 1200.0  # 20 min
    
    def test_default_feed_ts_range(self):
        """Feed TS range should span dryer output to dry solids."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert env.min_feed_ts == 0.60
        assert env.max_feed_ts == 0.95
        assert env.target_feed_ts == 0.75
    
    def test_default_overnight_states(self):
        """Default should allow hot hold, warm standby, and controlled cooldown."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert OvernightState.HOT_HOLD in env.allowed_overnight_states
        assert OvernightState.WARM_STANDBY in env.allowed_overnight_states
        assert OvernightState.CONTROLLED_COOLDOWN in env.allowed_overnight_states
        assert OvernightState.COLD_SHUTDOWN not in env.allowed_overnight_states
    
    def test_default_energy_constraints(self):
        """Default should require syngas self-sufficiency."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert env.min_syngas_self_sufficiency == 1.0
        assert env.max_aux_fuel_fraction == 0.20
    
    def test_default_safety_margins(self):
        """Default should include conservative safety margins."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert env.thermal_margin_pct == 20.0
        assert env.throughput_safety_factor == 0.80
    
    def test_model_parameters_includes_envelope(self):
        """ModelParameters should include envelope by default."""
        params = ModelParameters()
        assert isinstance(params.envelope, OperatingEnvelope)
        assert params.envelope.max_throughput_kgds_hr == 50.0


# =============================================================================
# ENVELOPE BOUNDARY METHODS
# =============================================================================

class TestEnvelopeBoundaryMethods:
    """Test OperatingEnvelope boundary check methods."""
    
    def test_throughput_in_range_nominal(self):
        """Nominal throughput should be in range."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert env.throughput_in_range(30.0)
    
    def test_throughput_at_boundaries(self):
        """Throughput at exact boundaries should be in range."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert env.throughput_in_range(10.0)  # min
        assert env.throughput_in_range(50.0)  # max
    
    def test_throughput_outside_range(self):
        """Throughput outside range should be rejected."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert not env.throughput_in_range(5.0)   # below min
        assert not env.throughput_in_range(60.0)  # above max
    
    def test_wall_temperature_in_range(self):
        """Nominal wall temperature should be in range."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert env.wall_temperature_in_range(650.0)
        assert env.wall_temperature_in_range(450.0)  # min
        assert env.wall_temperature_in_range(750.0)  # max
    
    def test_wall_temperature_outside_range(self):
        """Extreme wall temperatures should be rejected."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert not env.wall_temperature_in_range(400.0)  # too cold
        assert not env.wall_temperature_in_range(800.0)  # too hot
    
    def test_feed_ts_in_range(self):
        """Normal dried feed TS should be in range."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert env.feed_ts_in_range(0.75)
        assert env.feed_ts_in_range(0.60)  # min
        assert env.feed_ts_in_range(0.95)  # max
    
    def test_feed_ts_outside_range(self):
        """Wet or excessively dry feed should be rejected."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert not env.feed_ts_in_range(0.50)  # too wet
        assert not env.feed_ts_in_range(0.98)  # too dry
    
    def test_residence_time_in_range(self):
        """Normal residence time should be in range."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert env.residence_time_in_range(1200.0)  # 20 min
        assert env.residence_time_in_range(600.0)   # min
        assert env.residence_time_in_range(3600.0)  # max
    
    def test_residence_time_outside_range(self):
        """Too short or too long residence time should be rejected."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert not env.residence_time_in_range(300.0)   # 5 min, too short
        assert not env.residence_time_in_range(7200.0)  # 120 min, too long
    
    def test_overnight_state_allowed(self):
        """Allowed overnight states should pass."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert env.overnight_state_allowed(OvernightState.HOT_HOLD)
        assert env.overnight_state_allowed(OvernightState.WARM_STANDBY)
        assert env.overnight_state_allowed(OvernightState.CONTROLLED_COOLDOWN)
    
    def test_overnight_state_cold_shutdown_not_allowed(self):
        """Cold shutdown should not be in default allowed set."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert not env.overnight_state_allowed(OvernightState.COLD_SHUTDOWN)
    
    def test_overnight_temp_safe(self):
        """Temperature above minimum should be safe."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert env.overnight_temp_safe(300.0)
        assert env.overnight_temp_safe(200.0)  # exact minimum
    
    def test_overnight_temp_unsafe(self):
        """Temperature below minimum should be unsafe."""
        env = OPERATING_ENVELOPE_DEFAULT
        assert not env.overnight_temp_safe(150.0)


# =============================================================================
# ENVELOPE VALIDATION - NOMINAL CASES
# =============================================================================

class TestEnvelopeCheckNominal:
    """Test check_operating_envelope with nominal operating points."""
    
    def test_nominal_operating_point_passes(self):
        """A reasonable operating point should pass all checks."""
        result = check_operating_envelope(
            throughput_kgds_hr=30.0,
            wall_temperature_c=650.0,
            feed_ts=0.75,
        )
        assert result.within_envelope
        assert len(result.violations) == 0
    
    def test_nominal_with_all_parameters(self):
        """Fully-specified nominal point should pass."""
        result = check_operating_envelope(
            throughput_kgds_hr=30.0,
            wall_temperature_c=650.0,
            feed_ts=0.75,
            residence_time_s=1200.0,
            reactor_temperature_c=550.0,
            overnight_state=OvernightState.HOT_HOLD,
            overnight_temp_c=300.0,
            syngas_self_sufficiency=1.5,
            aux_fuel_fraction=0.0,
        )
        assert result.within_envelope
        assert len(result.violations) == 0
    
    def test_operating_point_recorded(self):
        """Check result should contain the operating point values."""
        result = check_operating_envelope(
            throughput_kgds_hr=30.0,
            wall_temperature_c=650.0,
            feed_ts=0.75,
        )
        assert result.operating_point["throughput_kgds_hr"] == 30.0
        assert result.operating_point["wall_temperature_c"] == 650.0
        assert result.operating_point["feed_ts"] == 0.75


# =============================================================================
# ENVELOPE VALIDATION - HARD VIOLATIONS
# =============================================================================

class TestEnvelopeHardViolations:
    """Test that physics-based constraints generate hard violations."""
    
    def test_excessive_throughput_hard_violation(self):
        """Throughput above max should be a hard violation."""
        result = check_operating_envelope(
            throughput_kgds_hr=80.0,
            wall_temperature_c=650.0,
            feed_ts=0.75,
        )
        assert not result.within_envelope
        assert len(result.hard_violations) == 1
        assert result.hard_violations[0].constraint == "max_throughput"
    
    def test_low_wall_temp_hard_violation(self):
        """Wall temperature below minimum should be a hard violation."""
        result = check_operating_envelope(
            throughput_kgds_hr=30.0,
            wall_temperature_c=400.0,
            feed_ts=0.75,
        )
        assert not result.within_envelope
        assert any(v.constraint == "min_wall_temperature" for v in result.hard_violations)
    
    def test_high_wall_temp_hard_violation(self):
        """Wall temperature above maximum should be a hard violation."""
        result = check_operating_envelope(
            throughput_kgds_hr=30.0,
            wall_temperature_c=800.0,
            feed_ts=0.75,
        )
        assert not result.within_envelope
        assert any(v.constraint == "max_wall_temperature" for v in result.hard_violations)
    
    def test_wet_feed_hard_violation(self):
        """Feed too wet for pyrolysis should be a hard violation."""
        result = check_operating_envelope(
            throughput_kgds_hr=30.0,
            wall_temperature_c=650.0,
            feed_ts=0.40,
        )
        assert not result.within_envelope
        assert any(v.constraint == "min_feed_ts" for v in result.hard_violations)
    
    def test_short_residence_time_hard_violation(self):
        """Residence time below minimum should be a hard violation."""
        result = check_operating_envelope(
            throughput_kgds_hr=30.0,
            wall_temperature_c=650.0,
            feed_ts=0.75,
            residence_time_s=300.0,  # 5 minutes, too short
        )
        assert not result.within_envelope
        assert any(v.constraint == "min_residence_time" for v in result.hard_violations)
    
    def test_disallowed_overnight_state_hard_violation(self):
        """Cold shutdown (not in allowed set) should be a hard violation."""
        result = check_operating_envelope(
            throughput_kgds_hr=30.0,
            wall_temperature_c=650.0,
            feed_ts=0.75,
            overnight_state=OvernightState.COLD_SHUTDOWN,
        )
        assert not result.within_envelope
        assert any(v.constraint == "overnight_state" for v in result.hard_violations)
    
    def test_low_overnight_temp_hard_violation(self):
        """Overnight temperature below safe minimum should be hard violation."""
        result = check_operating_envelope(
            throughput_kgds_hr=30.0,
            wall_temperature_c=650.0,
            feed_ts=0.75,
            overnight_temp_c=100.0,
        )
        assert not result.within_envelope
        assert any(v.constraint == "min_overnight_temperature" for v in result.hard_violations)
    
    def test_multiple_hard_violations(self):
        """Multiple physics violations should all be reported."""
        result = check_operating_envelope(
            throughput_kgds_hr=80.0,        # over max
            wall_temperature_c=400.0,       # under min
            feed_ts=0.40,                   # too wet
        )
        assert not result.within_envelope
        assert len(result.hard_violations) >= 3


# =============================================================================
# ENVELOPE VALIDATION - SOFT VIOLATIONS
# =============================================================================

class TestEnvelopeSoftViolations:
    """Test that operational warnings generate soft violations."""
    
    def test_low_throughput_soft_violation(self):
        """Below-minimum throughput is operational, not physics, so soft."""
        result = check_operating_envelope(
            throughput_kgds_hr=5.0,
            wall_temperature_c=650.0,
            feed_ts=0.75,
        )
        # Soft violations don't fail the envelope
        assert result.within_envelope
        assert len(result.soft_violations) == 1
        assert result.soft_violations[0].constraint == "min_throughput"
    
    def test_dry_feed_soft_violation(self):
        """Excessively dry feed is a handling concern, not physics."""
        result = check_operating_envelope(
            throughput_kgds_hr=30.0,
            wall_temperature_c=650.0,
            feed_ts=0.98,
        )
        assert result.within_envelope
        assert any(v.constraint == "max_feed_ts" for v in result.soft_violations)
    
    def test_long_residence_time_soft_violation(self):
        """Very long residence time degrades quality, doesn't break physics."""
        result = check_operating_envelope(
            throughput_kgds_hr=30.0,
            wall_temperature_c=650.0,
            feed_ts=0.75,
            residence_time_s=5000.0,  # 83 min, too long
        )
        assert result.within_envelope
        assert any(v.constraint == "max_residence_time" for v in result.soft_violations)
    
    def test_low_syngas_self_sufficiency_soft_violation(self):
        """Needing external fuel is economic, not physics."""
        result = check_operating_envelope(
            throughput_kgds_hr=30.0,
            wall_temperature_c=650.0,
            feed_ts=0.75,
            syngas_self_sufficiency=0.7,
        )
        assert result.within_envelope
        assert any(v.constraint == "syngas_self_sufficiency" for v in result.soft_violations)
    
    def test_high_aux_fuel_soft_violation(self):
        """Too much external fuel is economic concern."""
        result = check_operating_envelope(
            throughput_kgds_hr=30.0,
            wall_temperature_c=650.0,
            feed_ts=0.75,
            aux_fuel_fraction=0.30,
        )
        assert result.within_envelope
        assert any(v.constraint == "max_aux_fuel_fraction" for v in result.soft_violations)
    
    def test_soft_violations_include_remediation(self):
        """Soft violations should include actionable remediation."""
        result = check_operating_envelope(
            throughput_kgds_hr=5.0,
            wall_temperature_c=650.0,
            feed_ts=0.75,
        )
        assert result.soft_violations[0].remediation


# =============================================================================
# CUSTOM ENVELOPE
# =============================================================================

class TestCustomEnvelope:
    """Test custom envelope overrides for vendor-specific constraints."""
    
    def test_custom_throughput_limits(self):
        """Custom envelope can have different throughput limits."""
        custom = OperatingEnvelope(
            max_throughput_kgds_hr=100.0,
            min_throughput_kgds_hr=20.0,
        )
        result = check_operating_envelope(
            throughput_kgds_hr=80.0,
            wall_temperature_c=650.0,
            feed_ts=0.75,
            envelope=custom,
        )
        assert result.within_envelope  # 80 is within 20-100
    
    def test_custom_temperature_window(self):
        """Custom envelope can have different temperature limits."""
        custom = OperatingEnvelope(
            min_wall_temperature_c=500.0,
            max_wall_temperature_c=800.0,
        )
        result = check_operating_envelope(
            throughput_kgds_hr=30.0,
            wall_temperature_c=780.0,
            feed_ts=0.75,
            envelope=custom,
        )
        assert result.within_envelope
    
    def test_custom_overnight_with_cold_shutdown(self):
        """Vendor envelope can allow cold shutdown."""
        custom = OperatingEnvelope(
            allowed_overnight_states=(
                OvernightState.HOT_HOLD,
                OvernightState.WARM_STANDBY,
                OvernightState.CONTROLLED_COOLDOWN,
                OvernightState.COLD_SHUTDOWN,
            ),
        )
        result = check_operating_envelope(
            throughput_kgds_hr=30.0,
            wall_temperature_c=650.0,
            feed_ts=0.75,
            overnight_state=OvernightState.COLD_SHUTDOWN,
            envelope=custom,
        )
        assert result.within_envelope


# =============================================================================
# CI GATE INTEGRATION
# =============================================================================

class TestEnvelopeCIGate:
    """Test operating_envelope_gate integration with CI pattern."""
    
    def test_nominal_passes_gate(self):
        """Nominal operating point should pass gate."""
        result = operating_envelope_gate(
            throughput_kgds_hr=30.0,
            wall_temperature_c=650.0,
            feed_ts=0.75,
        )
        assert result.passed
        assert result.name == "Operating Envelope"
        assert result.value == 0.0  # 0 hard violations
    
    def test_hard_violation_fails_gate(self):
        """Hard violation should fail gate."""
        result = operating_envelope_gate(
            throughput_kgds_hr=80.0,  # over max
            wall_temperature_c=650.0,
            feed_ts=0.75,
        )
        assert not result.passed
        assert result.value > 0  # has hard violations
        assert result.remediation is not None
    
    def test_soft_violation_passes_gate(self):
        """Soft-only violations should still pass gate."""
        result = operating_envelope_gate(
            throughput_kgds_hr=5.0,  # below min (soft)
            wall_temperature_c=650.0,
            feed_ts=0.75,
        )
        assert result.passed  # soft violations don't fail
    
    def test_gate_remediation_includes_details(self):
        """Gate remediation should include violation details."""
        result = operating_envelope_gate(
            throughput_kgds_hr=80.0,
            wall_temperature_c=400.0,
            feed_ts=0.40,
        )
        assert not result.passed
        assert "max_throughput" in result.remediation
        assert "min_wall_temperature" in result.remediation
        assert "min_feed_ts" in result.remediation
    
    def test_gate_with_custom_envelope(self):
        """Gate should accept custom envelope."""
        custom = OperatingEnvelope(max_throughput_kgds_hr=100.0)
        result = operating_envelope_gate(
            throughput_kgds_hr=80.0,
            wall_temperature_c=650.0,
            feed_ts=0.75,
            envelope=custom,
        )
        assert result.passed


# =============================================================================
# OVERNIGHT STATE ENUM
# =============================================================================

class TestOvernightStateEnum:
    """Test overnight state enumeration values."""
    
    def test_overnight_state_values(self):
        """Overnight states should have clear string values."""
        assert OvernightState.HOT_HOLD.value == "hot_hold"
        assert OvernightState.WARM_STANDBY.value == "warm_standby"
        assert OvernightState.CONTROLLED_COOLDOWN.value == "controlled_cooldown"
        assert OvernightState.COLD_SHUTDOWN.value == "cold_shutdown"
    
    def test_all_four_states_exist(self):
        """Should have exactly 4 overnight states."""
        assert len(OvernightState) == 4


# =============================================================================
# EDGE CASES AND COMBINED VIOLATIONS
# =============================================================================

class TestEnvelopeEdgeCases:
    """Test boundary conditions and combined violation scenarios."""
    
    def test_exact_boundary_throughput_passes(self):
        """Throughput at exact max should pass."""
        result = check_operating_envelope(
            throughput_kgds_hr=50.0,
            wall_temperature_c=650.0,
            feed_ts=0.75,
        )
        assert result.within_envelope
    
    def test_just_over_boundary_fails(self):
        """Throughput just over max should fail."""
        result = check_operating_envelope(
            throughput_kgds_hr=50.01,
            wall_temperature_c=650.0,
            feed_ts=0.75,
        )
        assert not result.within_envelope
    
    def test_mixed_hard_and_soft_violations(self):
        """Both hard and soft violations should be reported independently."""
        result = check_operating_envelope(
            throughput_kgds_hr=5.0,     # soft: below min throughput
            wall_temperature_c=400.0,   # hard: below min wall temp
            feed_ts=0.75,
        )
        assert not result.within_envelope  # hard violation present
        assert len(result.hard_violations) == 1
        assert len(result.soft_violations) == 1
    
    def test_skipped_optional_checks(self):
        """Optional parameters (0 or None) should not generate violations."""
        result = check_operating_envelope(
            throughput_kgds_hr=30.0,
            wall_temperature_c=650.0,
            feed_ts=0.75,
            residence_time_s=0.0,        # skip
            reactor_temperature_c=0.0,   # skip
            overnight_state=None,        # skip
            overnight_temp_c=None,       # skip
        )
        assert result.within_envelope
        assert len(result.violations) == 0
    
    def test_violation_str_representation(self):
        """Violations should have readable string representation."""
        v = EnvelopeViolation(
            constraint="max_throughput",
            value=80.0,
            limit=50.0,
            direction="above",
            severity="hard",
            remediation="Reduce feed rate",
        )
        s = str(v)
        assert "HARD" in s
        assert "max_throughput" in s
        assert "80.00" in s
        assert "50.00" in s
    
    def test_result_str_representation(self):
        """Check result should have readable string representation."""
        result = check_operating_envelope(
            throughput_kgds_hr=80.0,
            wall_temperature_c=650.0,
            feed_ts=0.75,
        )
        s = str(result)
        assert "OUTSIDE ENVELOPE" in s
        assert "Violations" in s


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
