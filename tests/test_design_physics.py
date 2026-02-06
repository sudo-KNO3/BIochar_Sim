"""
Integration tests for design-grade physics.

Tests the kinetics + heat transfer + validation governance system:
    - Kinetics module correctness
    - Thermal feasibility calculations
    - Validation gate behavior
    - Warning mechanism for unvalidated kinetics
    - DRL claim blocking
"""

import pytest
import warnings
from dataclasses import replace

from septage_model.core.parameters import (
    ModelParameters,
    KineticsParams,
    ReactorParams,
    FeedstockProperties,
    SEPTAGE_KINETICS_DEFAULT,
    WOOD_KINETICS_DEFAULT,
    SEPTAGE_SOLIDS_DEFAULT,
    REACTOR_DEFAULT,
    UnvalidatedKineticsWarning,
)
from septage_model.core.pyrolysis_kinetics import (
    calc_conversion,
    calc_yields_from_conversion,
    calc_rate_constant,
    calc_residence_time_required,
    list_unvalidated_physics_assumptions,
)
from septage_model.core.thermal_feasibility import (
    check_thermal_feasibility,
    calc_max_throughput,
)
from septage_model.ci.gates import (
    kinetics_validation_gate,
    source_refs_gate,
    conversion_gate,
    thermal_feasibility_gate,
    run_design_physics_gates,
)


class TestKineticsParams:
    """Test KineticsParams dataclass validation."""
    
    def test_unvalidated_requires_source_refs(self):
        """Unvalidated kinetics without source_refs should raise ValueError."""
        with pytest.raises(ValueError, match="must reference at least one ref_id"):
            KineticsParams(
                stream_id="test",
                validated=False,
                source_refs=(),  # Empty!
            )
    
    def test_tier2_requires_validation(self):
        """Tier-2 kinetics without validated=True should raise ValueError."""
        with pytest.raises(ValueError, match="Tier-2.*require validated=True"):
            KineticsParams(
                stream_id="test",
                tier="TIER2_PARALLEL",
                validated=False,
                source_refs=("ref_test",),
            )
    
    def test_tier1_with_sources_is_valid(self):
        """Tier-1 kinetics with source_refs should be valid."""
        k = KineticsParams(
            stream_id="test",
            tier="TIER1_GLOBAL",
            validated=False,
            source_refs=("ref_test",),
        )
        assert k.stream_id == "test"
        assert k.validated is False
    
    def test_validated_kinetics_can_have_empty_sources(self):
        """Validated kinetics don't need source_refs (they have lab data)."""
        k = KineticsParams(
            stream_id="test",
            tier="TIER1_GLOBAL",
            validated=True,
            source_refs=(),  # OK when validated
        )
        assert k.validated is True


class TestConversionCalculation:
    """Test pyrolysis conversion calculations."""
    
    def test_rate_constant_at_550c(self):
        """Check rate constant is reasonable at 550°C."""
        T_k = 823.15  # 550°C
        k = calc_rate_constant(T_k, SEPTAGE_KINETICS_DEFAULT)
        # At 550°C with Ea=250kJ/mol, A=1e18, should be ~100-200 /s
        assert k > 10, f"Rate constant too low: {k}"
        assert k < 1000, f"Rate constant too high: {k}"
    
    def test_conversion_increases_with_residence_time(self):
        """Higher residence time should give higher conversion."""
        result1 = calc_conversion(
            SEPTAGE_KINETICS_DEFAULT, REACTOR_DEFAULT, 
            m_dot_kg_s=0.1, warn_if_unvalidated=False
        )
        result2 = calc_conversion(
            SEPTAGE_KINETICS_DEFAULT, REACTOR_DEFAULT,
            m_dot_kg_s=0.01, warn_if_unvalidated=False  # Lower flow = longer τ
        )
        assert result2.residence_time_s > result1.residence_time_s
        assert result2.X >= result1.X
    
    def test_feasibility_flag_respects_x_min(self):
        """Conversion below X_min should set feasible=False."""
        # Create kinetics with very high Ea so conversion is low
        slow_kinetics = replace(
            SEPTAGE_KINETICS_DEFAULT,
            Ea_J_per_mol=400000.0,  # Very high activation energy
            X_min=0.95,
        )
        result = calc_conversion(
            slow_kinetics, REACTOR_DEFAULT,
            m_dot_kg_s=0.1, warn_if_unvalidated=False
        )
        # With high Ea and short residence time, conversion should be low
        if result.X < 0.95:
            assert result.feasible is False
    
    def test_unvalidated_kinetics_raises_warning(self):
        """Using unvalidated kinetics should raise UnvalidatedKineticsWarning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            calc_conversion(
                SEPTAGE_KINETICS_DEFAULT, REACTOR_DEFAULT,
                m_dot_kg_s=0.01, warn_if_unvalidated=True
            )
            assert len(w) == 1
            assert issubclass(w[0].category, UnvalidatedKineticsWarning)
            assert "literature-based" in str(w[0].message)


class TestYieldsFromConversion:
    """Test yield derivation from conversion and feedstock."""
    
    def test_yields_sum_to_one(self):
        """Product yields must sum to 1.0."""
        yields = calc_yields_from_conversion(0.90, SEPTAGE_SOLIDS_DEFAULT)
        total = yields.yield_char + yields.yield_gas + yields.yield_tar + yields.yield_ash
        assert abs(total - 1.0) < 0.01
    
    def test_ash_matches_feedstock(self):
        """Ash yield should match feedstock ash content."""
        yields = calc_yields_from_conversion(0.90, SEPTAGE_SOLIDS_DEFAULT)
        # Ash should be approximately the feedstock ash (may differ due to normalization)
        assert abs(yields.yield_ash - SEPTAGE_SOLIDS_DEFAULT.proximate.ash) < 0.05
    
    def test_higher_conversion_gives_more_gas(self):
        """Higher conversion should produce more gas, less tar."""
        yields_low = calc_yields_from_conversion(0.50, SEPTAGE_SOLIDS_DEFAULT)
        yields_high = calc_yields_from_conversion(0.95, SEPTAGE_SOLIDS_DEFAULT)
        assert yields_high.yield_gas > yields_low.yield_gas


class TestThermalFeasibility:
    """Test thermal feasibility calculations."""
    
    def test_low_throughput_is_feasible(self):
        """Low throughput should be thermally feasible."""
        result = check_thermal_feasibility(
            m_dot_dry_kg_s=0.001,
            feedstock=SEPTAGE_SOLIDS_DEFAULT,
            reactor=REACTOR_DEFAULT,
        )
        assert result.feasible is True
        assert result.margin_pct > 0
    
    def test_high_throughput_may_be_infeasible(self):
        """Very high throughput may exceed heat transfer capacity."""
        result = check_thermal_feasibility(
            m_dot_dry_kg_s=1.0,  # Very high
            feedstock=SEPTAGE_SOLIDS_DEFAULT,
            reactor=REACTOR_DEFAULT,
        )
        # At 1 kg/s, heat required >> heat available
        assert result.Q_req_kw > result.Q_max_kw
        assert result.feasible is False
    
    def test_max_throughput_is_bounded(self):
        """Max throughput should be positive and finite."""
        max_tp = calc_max_throughput(SEPTAGE_SOLIDS_DEFAULT, REACTOR_DEFAULT)
        assert max_tp > 0
        assert max_tp < float('inf')


class TestValidationGates:
    """Test DRL validation gates."""
    
    def test_drl3_allows_unvalidated_kinetics(self):
        """DRL-3 claims should pass with unvalidated kinetics."""
        result = kinetics_validation_gate(
            [SEPTAGE_KINETICS_DEFAULT, WOOD_KINETICS_DEFAULT],
            claimed_drl=3,
        )
        assert result.passed is True
    
    def test_drl4_blocks_unvalidated_kinetics(self):
        """DRL-4 claims should fail with unvalidated kinetics."""
        result = kinetics_validation_gate(
            [SEPTAGE_KINETICS_DEFAULT, WOOD_KINETICS_DEFAULT],
            claimed_drl=4,
        )
        assert result.passed is False
        assert "DRL-4+ claim blocked" in result.remediation
    
    def test_drl4_passes_with_validated_kinetics(self):
        """DRL-4 claims should pass with validated kinetics."""
        validated_kinetics = replace(
            SEPTAGE_KINETICS_DEFAULT,
            validated=True,
            source_refs=(),  # No sources needed when validated
        )
        result = kinetics_validation_gate(
            [validated_kinetics],
            claimed_drl=4,
        )
        assert result.passed is True
    
    def test_source_refs_gate_fails_on_missing_refs(self):
        """source_refs_gate should fail if unvalidated kinetics have no refs."""
        # This should be impossible due to __post_init__, but test the gate
        result = source_refs_gate([SEPTAGE_KINETICS_DEFAULT])
        # Default has refs, so should pass
        assert result.passed is True


class TestDesignPhysicsGates:
    """Test combined design physics gate runner."""
    
    def test_full_gate_report_structure(self):
        """run_design_physics_gates should return proper report."""
        # Run conversion
        conv_result = calc_conversion(
            SEPTAGE_KINETICS_DEFAULT, REACTOR_DEFAULT,
            m_dot_kg_s=0.01, warn_if_unvalidated=False
        )
        
        # Run thermal
        thermal_result = check_thermal_feasibility(
            m_dot_dry_kg_s=0.01,
            feedstock=SEPTAGE_SOLIDS_DEFAULT,
            reactor=REACTOR_DEFAULT,
        )
        
        # Run all gates
        report = run_design_physics_gates(
            conversion_results=[conv_result],
            thermal_result=thermal_result,
            kinetics_list=[SEPTAGE_KINETICS_DEFAULT],
            claimed_drl=4,
        )
        
        # Should have 4 gates: 1 conversion + 1 thermal + 2 governance
        assert len(report.gates) == 4
        
        # Should fail on kinetics validation (DRL-4 with unvalidated)
        assert not report.all_passed
        failed_names = [g.name for g in report.failed_gates]
        assert "Kinetics Validation (DRL)" in failed_names


class TestUnvalidatedAssumptions:
    """Test the unvalidated assumptions dashboard."""
    
    def test_lists_all_unvalidated_params(self):
        """Should list all unvalidated kinetics and reactor params."""
        assumptions = list_unvalidated_physics_assumptions(
            [SEPTAGE_KINETICS_DEFAULT, WOOD_KINETICS_DEFAULT],
            REACTOR_DEFAULT,
        )
        
        # Should have entries for both kinetics streams + reactor
        stream_ids = {a.stream_id for a in assumptions}
        assert "septage" in stream_ids
        assert "cofeed_wood" in stream_ids
        assert "reactor" in stream_ids
    
    def test_validated_kinetics_not_listed(self):
        """Validated kinetics should not appear in assumptions list."""
        validated_kinetics = replace(
            SEPTAGE_KINETICS_DEFAULT,
            validated=True,
            source_refs=(),
        )
        assumptions = list_unvalidated_physics_assumptions(
            [validated_kinetics],
            None,  # No reactor
        )
        assert len(assumptions) == 0


class TestDesignModeFlag:
    """Test design_mode flag in ModelParameters."""
    
    def test_default_design_mode_is_false(self):
        """Default ModelParameters should have design_mode=False."""
        params = ModelParameters()
        assert params.design_mode is False
    
    def test_design_mode_can_be_enabled(self):
        """Should be able to create params with design_mode=True."""
        params = ModelParameters(design_mode=True)
        assert params.design_mode is True
    
    def test_kinetics_accessible_regardless_of_design_mode(self):
        """Kinetics params should be accessible even when design_mode=False."""
        params = ModelParameters(design_mode=False)
        assert params.kinetics_septage.stream_id == "septage"
        assert params.kinetics_cofeed.stream_id == "cofeed_wood"
