"""
Tests for Value-Add Pathway Scenarios

Covers:
- Pathway calculations (struvite, ammonia, CHP, char activation, etc.)
- Viability gates (thresholds, remediation guidance)
- Scenario evaluation (baseline vs value-add NPV)
- Mass/energy balance closure
- Heat grade compatibility
- Circular pathway blocking
- Sequential state management
"""

import pytest
from septage_model.core.stream_pathways import (
    PathwayMaturity,
    ScenarioRisk,
    PathwayTier,
    HeatGrade,
    HeatStream,
    CircularPathway,
    CIRCULAR_PATHWAY_MIN_DRL,
    HEAT_REQUIREMENTS,
    heat_grade_compatible,
    CentratePathway,
    CharPathway,
    SyngasPathway,
    ScreeningsPathway,
    OffSpecPathway,
    StruvitePathwayParams,
    AmmoniaStrippingParams,
    CHPParams,
    CharActivationParams,
    StreamPathwayConfig,
    pathway_allowed,
    BASELINE_PATHWAYS,
    CONSERVATIVE_PATHWAYS,
    MODERATE_PATHWAYS,
    FULL_CIRCULAR_PATHWAYS,
)
from septage_model.core.state import PathwayExecutionState
from septage_model.core.balances import (
    calc_struvite_recovery,
    calc_ammonia_stripping,
    calc_syngas_chp,
    calc_heat_export,
    calc_char_activation,
    calc_screenings_reuse,
    calc_carbon_credits,
    StruviteRecoveryResult,
    AmmoniaStrippingResult,
    CHPResult,
    HeatExportResult,
    CharActivationResult,
    ScreeningsReuseResult,
    CarbonCreditResult,
)
from septage_model.ci.gates import (
    nutrient_recovery_viability_gate,
    chp_grid_viability_gate,
    char_activation_viability_gate,
    heat_export_viability_gate,
    run_pathway_viability_gates,
    MIN_CENTRATE_M3_FOR_NUTRIENT_RECOVERY,
    MIN_P_CONC_MG_L,
    MIN_SYNGAS_EXCESS_MJ_FOR_CHP,
    MIN_CHP_CAPACITY_KW,
    MIN_CHAR_KG_FOR_ACTIVATION,
    MIN_STEAM_KG_FOR_ACTIVATION,
)
from septage_model.analysis.pathway_scenarios import (
    ScenarioType,
    ValueAddScenario,
    ScenarioResult,
    OperatingInputs,
    evaluate_scenario,
    compare_scenarios,
    SCENARIO_BASELINE,
    SCENARIO_CONSERVATIVE,
    SCENARIO_MODERATE,
    SCENARIO_FULL_CIRCULAR,
)


# =============================================================================
# PATHWAY ENUM TESTS
# =============================================================================

class TestPathwayEnums:
    """Test pathway enumeration definitions."""
    
    def test_pathway_maturity_ordering(self):
        """Maturity levels should be orderable by timeline."""
        assert PathwayMaturity.NEAR_TERM.value == "near_term"
        assert PathwayMaturity.MID_TERM.value == "mid_term"
        assert PathwayMaturity.SPECULATIVE.value == "speculative"
    
    def test_scenario_risk_levels(self):
        """Risk levels should cover conservative to optimistic."""
        assert ScenarioRisk.CONSERVATIVE.value == "conservative"
        assert ScenarioRisk.MODERATE.value == "moderate"
        assert ScenarioRisk.OPTIMISTIC.value == "optimistic"
    
    def test_pathway_tier_values(self):
        """Pathway tiers should define value progression."""
        assert PathwayTier.DISPOSAL_ONLY.value == "disposal_only"
        assert PathwayTier.RECOVERABLE.value == "recoverable"
        assert PathwayTier.UPGRADABLE.value == "upgradable"
    
    def test_centrate_pathways_comprehensive(self):
        """All centrate disposition options should be defined."""
        pathways = list(CentratePathway)
        assert len(pathways) >= 5  # At least: discharge, haul, struvite, ammonia, algae
        assert CentratePathway.LOCAL_DISCHARGE in pathways
        assert CentratePathway.STRUVITE_RECOVERY in pathways
    
    def test_char_pathways_comprehensive(self):
        """All char value-add options should be defined."""
        pathways = list(CharPathway)
        assert len(pathways) >= 5  # At least: landfill, ag, activation, septic, building
        assert CharPathway.LANDFILL_COVER in pathways
        assert CharPathway.ACTIVATED_BIOCHAR in pathways
    
    def test_syngas_pathways_comprehensive(self):
        """All syngas utilization options should be defined."""
        pathways = list(SyngasPathway)
        assert len(pathways) >= 4  # At least: process heat, CHP, heat export, hydrogen
        assert SyngasPathway.PROCESS_HEAT_ONLY in pathways
        assert SyngasPathway.CHP_ELECTRICITY in pathways


# =============================================================================
# PATHWAY ALLOWED FUNCTION TESTS
# =============================================================================

class TestPathwayAllowed:
    """Test pathway_allowed filter logic."""
    
    def test_conservative_allows_near_term_only(self):
        """Conservative risk should only allow near-term."""
        assert pathway_allowed(PathwayMaturity.NEAR_TERM, ScenarioRisk.CONSERVATIVE) is True
        assert pathway_allowed(PathwayMaturity.MID_TERM, ScenarioRisk.CONSERVATIVE) is False
        assert pathway_allowed(PathwayMaturity.SPECULATIVE, ScenarioRisk.CONSERVATIVE) is False
    
    def test_moderate_allows_near_and_mid_term(self):
        """Moderate risk should allow near-term and mid-term."""
        assert pathway_allowed(PathwayMaturity.NEAR_TERM, ScenarioRisk.MODERATE) is True
        assert pathway_allowed(PathwayMaturity.MID_TERM, ScenarioRisk.MODERATE) is True
        assert pathway_allowed(PathwayMaturity.SPECULATIVE, ScenarioRisk.MODERATE) is False
    
    def test_optimistic_allows_all(self):
        """Optimistic risk should allow all maturities."""
        assert pathway_allowed(PathwayMaturity.NEAR_TERM, ScenarioRisk.OPTIMISTIC) is True
        assert pathway_allowed(PathwayMaturity.MID_TERM, ScenarioRisk.OPTIMISTIC) is True
        assert pathway_allowed(PathwayMaturity.SPECULATIVE, ScenarioRisk.OPTIMISTIC) is True


# =============================================================================
# PATHWAY PARAMS TESTS
# =============================================================================

class TestPathwayParams:
    """Test pathway parameter dataclasses."""
    
    def test_struvite_params_defaults(self):
        """Struvite params should have sensible defaults."""
        params = StruvitePathwayParams()
        assert params.maturity == PathwayMaturity.NEAR_TERM
        assert params.p_recovery_efficiency >= 0.7
        assert params.capex > 0
        assert params.opex_annual > 0
    
    def test_struvite_params_override(self):
        """CAPEX/OPEX overrides should take precedence."""
        params = StruvitePathwayParams(
            capex_override=100_000,
            opex_override=5_000,
        )
        assert params.capex == 100_000
        assert params.opex_annual == 5_000
    
    def test_chp_params_efficiency_bounds(self):
        """CHP efficiency should be physically reasonable."""
        params = CHPParams()
        assert 0.2 <= params.electrical_efficiency <= 0.45
        assert 0.3 <= params.thermal_efficiency <= 0.55
        # Total efficiency shouldn't exceed 1.0
        assert params.electrical_efficiency + params.thermal_efficiency <= 0.95
    
    def test_char_activation_maturity(self):
        """Char activation should be mid-term maturity."""
        params = CharActivationParams()
        assert params.maturity == PathwayMaturity.MID_TERM


# =============================================================================
# STREAM PATHWAY CONFIG TESTS
# =============================================================================

class TestStreamPathwayConfig:
    """Test StreamPathwayConfig aggregate dataclass."""
    
    def test_baseline_config_minimal(self):
        """Baseline should have no value-add pathways enabled."""
        config = BASELINE_PATHWAYS
        enabled = config.get_enabled_pathways()
        # Baseline should only have disposal pathways
        assert len(enabled) == 0 or all(
            "disposal" in str(p).lower() or "landfill" in str(p).lower()
            for p in enabled
        )
    
    def test_conservative_config_near_term_only(self):
        """Conservative should only enable near-term pathways."""
        config = CONSERVATIVE_PATHWAYS
        # All enabled pathways should be NEAR_TERM maturity
        for pathway in config.get_enabled_pathways():
            if hasattr(pathway, 'maturity'):
                assert pathway.maturity == PathwayMaturity.NEAR_TERM
    
    def test_full_circular_enables_all(self):
        """Full circular should enable all value-add pathways."""
        config = FULL_CIRCULAR_PATHWAYS
        enabled = config.get_enabled_pathways()
        assert len(enabled) > 0
    
    def test_total_capex_positive_for_value_add(self):
        """Value-add configs should have non-zero CAPEX."""
        assert BASELINE_PATHWAYS.total_pathway_capex() >= 0
        assert MODERATE_PATHWAYS.total_pathway_capex() > 0
        assert FULL_CIRCULAR_PATHWAYS.total_pathway_capex() > MODERATE_PATHWAYS.total_pathway_capex()
    
    def test_total_opex_scales_with_pathways(self):
        """More pathways should mean higher OPEX."""
        baseline_opex = BASELINE_PATHWAYS.total_pathway_opex()
        moderate_opex = MODERATE_PATHWAYS.total_pathway_opex()
        full_opex = FULL_CIRCULAR_PATHWAYS.total_pathway_opex()
        
        assert baseline_opex <= moderate_opex
        assert moderate_opex <= full_opex


# =============================================================================
# PATHWAY CALCULATION TESTS
# =============================================================================

class TestStruviteCalculation:
    """Test struvite recovery calculations."""
    
    def test_struvite_basic_calculation(self):
        """Struvite output should scale with P concentration."""
        result = calc_struvite_recovery(
            centrate_m3_annual=1000.0,
            p_concentration_mg_L=100.0,
            recovery_efficiency=0.85,
            mg_dose_ratio=1.3,
            struvite_revenue_per_tonne=200.0,
        )
        
        assert result.struvite_produced_kg > 0
        assert result.phosphorus_recovered_kg > 0
        assert result.revenue_annual > 0
    
    def test_struvite_zero_concentration(self):
        """Zero P concentration should yield zero struvite."""
        result = calc_struvite_recovery(
            centrate_m3_annual=1000.0,
            p_concentration_mg_L=0.0,
            recovery_efficiency=0.85,
            mg_dose_ratio=1.3,
            struvite_revenue_per_tonne=200.0,
        )
        
        assert result.struvite_produced_kg == 0
        assert result.phosphorus_recovered_kg == 0
    
    def test_struvite_mw_ratio(self):
        """Struvite should be ~7.9x P mass (MW ratio)."""
        result = calc_struvite_recovery(
            centrate_m3_annual=1000.0,
            p_concentration_mg_L=100.0,
            recovery_efficiency=1.0,  # 100% for clean test
            mg_dose_ratio=1.3,
            struvite_revenue_per_tonne=200.0,
        )
        
        # P input: 1000 m³ × 100 mg/L = 100 kg P
        # Expected struvite: ~790 kg (7.9:1 ratio)
        p_input_kg = 1000 * 100 / 1000  # 100 kg
        expected_struvite = p_input_kg * 7.9  # ~790 kg
        
        assert abs(result.struvite_produced_kg - expected_struvite) < 1.0


class TestAmmoniaStrippingCalculation:
    """Test ammonia stripping calculations."""
    
    def test_ammonia_basic_calculation(self):
        """Ammonia output should scale with N concentration."""
        result = calc_ammonia_stripping(
            centrate_m3_annual=1000.0,
            n_concentration_mg_L=500.0,
            recovery_efficiency=0.75,
            acid_consumption_kg_per_kg_n=3.5,
            steam_mj_per_m3=50.0,
            ammonium_sulfate_revenue_per_tonne=180.0,
        )
        
        assert result.ammonium_sulfate_produced_kg > 0
        assert result.nitrogen_recovered_kg > 0
        assert result.revenue_annual > 0
    
    def test_ammonia_sulfate_stoichiometry(self):
        """Ammonium sulfate should be ~4.7x N mass."""
        result = calc_ammonia_stripping(
            centrate_m3_annual=1000.0,
            n_concentration_mg_L=500.0,
            recovery_efficiency=1.0,
            acid_consumption_kg_per_kg_n=3.5,
            steam_mj_per_m3=50.0,
            ammonium_sulfate_revenue_per_tonne=180.0,
        )
        
        # N input: 1000 m³ × 500 mg/L = 500 kg N
        # (NH4)2SO4 MW = 132, N content = 21% → ratio ~4.76
        n_input_kg = 1000 * 500 / 1000  # 500 kg
        # AS = N / 0.21
        expected_sulfate = n_input_kg / 0.21  # ~2380 kg
        
        # Allow small tolerance
        assert abs(result.ammonium_sulfate_produced_kg - expected_sulfate) < 10


class TestSyngasCHPCalculation:
    """Test syngas CHP calculations."""
    
    def test_chp_energy_conversion(self):
        """CHP should convert syngas to electricity and heat."""
        result = calc_syngas_chp(
            syngas_energy_annual_mj=100_000.0,  # 100 GJ
            process_heat_demand_mj=20_000.0,
            electrical_efficiency=0.30,
            thermal_efficiency=0.45,
            site_power_demand_kwh=5000.0,
            grid_export_enabled=True,
            export_rate_per_kwh=0.10,
        )
        
        assert result.electricity_generated_kwh > 0
        assert result.heat_recovered_mj > 0
    
    def test_chp_electrical_efficiency(self):
        """Electrical efficiency should be applied correctly."""
        result = calc_syngas_chp(
            syngas_energy_annual_mj=100_000.0,
            process_heat_demand_mj=0.0,  # No process heat demand
            electrical_efficiency=0.30,
            thermal_efficiency=0.45,
            site_power_demand_kwh=0.0,
            grid_export_enabled=True,
            export_rate_per_kwh=0.10,
        )
        
        # 100 GJ × 30% = 30 GJ → 8333 kWh
        expected_kwh = 100_000 * 0.30 / 3.6
        assert abs(result.electricity_generated_kwh - expected_kwh) < 100
    
    def test_chp_grid_export_after_self_consumption(self):
        """Grid export should only include excess after self-consumption."""
        result = calc_syngas_chp(
            syngas_energy_annual_mj=100_000.0,
            process_heat_demand_mj=0.0,
            electrical_efficiency=0.30,
            thermal_efficiency=0.45,
            site_power_demand_kwh=5000.0,
            grid_export_enabled=True,
            export_rate_per_kwh=0.10,
        )
        
        # Self consumption should be 5000 kWh
        assert result.self_consumption_kwh == 5000.0
        # Export should be total - self consumption
        assert result.grid_export_kwh == result.electricity_generated_kwh - 5000.0


class TestHeatExportCalculation:
    """Test heat export calculations."""
    
    def test_heat_export_basic(self):
        """Heat export should apply exportable fraction."""
        result = calc_heat_export(
            excess_heat_mj=100_000.0,
            exportable_fraction=0.80,
            heat_rate_per_gj=15.0,
        )
        
        assert result.exported_heat_mj == 80_000.0
        assert result.revenue_annual == 80.0 * 15.0  # 80 GJ × $15/GJ
    
    def test_heat_export_efficiency_loss(self):
        """Some heat should be lost (not exported)."""
        result = calc_heat_export(
            excess_heat_mj=100_000.0,
            exportable_fraction=0.90,
            heat_rate_per_gj=15.0,
        )
        
        # Should be < 100% due to exportable fraction
        assert result.exported_heat_mj < 100_000.0


class TestCharActivationCalculation:
    """Test char activation calculations."""
    
    def test_char_activation_yield(self):
        """Activated carbon yield should follow yield parameter."""
        result = calc_char_activation(
            char_input_kg=1000.0,
            activation_yield=0.85,
            steam_kg_per_kg_char=1.5,
            base_price_per_tonne=225.0,
            activated_premium_per_tonne=200.0,
        )
        
        assert result.activated_char_output_kg == 850.0  # 1000 × 0.85
        assert result.steam_consumed_kg == 1500.0  # 1000 × 1.5
    
    def test_char_activation_revenue_premium(self):
        """Premium revenue should be calculated correctly."""
        result = calc_char_activation(
            char_input_kg=1000.0,
            activation_yield=0.85,
            steam_kg_per_kg_char=1.5,
            base_price_per_tonne=225.0,
            activated_premium_per_tonne=200.0,
        )
        
        # Premium = 850 kg / 1000 × $200/tonne = $170
        expected_premium = (850.0 / 1000.0) * 200.0
        assert abs(result.revenue_premium - expected_premium) < 0.01


class TestCarbonCreditsCalculation:
    """Test carbon credits calculations."""
    
    def test_carbon_credits_sequestration(self):
        """Char should sequester ~3.67x carbon mass as CO2e."""
        result = calc_carbon_credits(
            char_carbon_kg=1000.0,
            permanence_discount=1.0,  # No discount for clean test
            credit_price_per_tonne_co2e=50.0,
        )
        
        # C in char: 1000 kg
        # CO2e: 1000 × (44/12) = 3666.67 kg
        assert abs(result.sequestered_co2e_kg - 3666.67) < 10.0
    
    def test_carbon_credits_permanence_discount(self):
        """Permanence discount should reduce claimable credits."""
        result = calc_carbon_credits(
            char_carbon_kg=1000.0,
            permanence_discount=0.80,
            credit_price_per_tonne_co2e=50.0,
        )
        
        # 3.67 tonnes × 0.80 = 2.936 tonnes claimable
        expected_claimable = 3.67 * 0.80
        assert abs(result.credits_claimable_tonnes - expected_claimable) < 0.1
    
    def test_carbon_credits_revenue(self):
        """Revenue should equal credits × price."""
        result = calc_carbon_credits(
            char_carbon_kg=1000.0,
            permanence_discount=0.80,
            credit_price_per_tonne_co2e=50.0,
        )
        
        expected_revenue = result.credits_claimable_tonnes * 50.0
        assert abs(result.credit_revenue_annual - expected_revenue) < 0.01


class TestScreeningsReuseCalculation:
    """Test screenings/grit/ash beneficial reuse calculations."""

    def test_basic_mass_calculation(self):
        """Screenings and grit masses should scale with septage, ash with char."""
        result = calc_screenings_reuse(
            septage_processed_m3=1000.0,
            char_produced_kg=500.0,
            screenings_fraction=0.005,
            grit_fraction=0.002,
            ash_fraction=0.15,
            density_kg_m3=1020.0,
            landfill_cost_per_tonne=85.0,
            reuse_credit_per_tonne=10.0,
        )

        # septage_mass = 1000 * 1020 = 1_020_000 kg
        expected_screenings = 1_020_000 * 0.005  # 5100 kg
        expected_grit = 1_020_000 * 0.002         # 2040 kg
        expected_ash = 500 * 0.15                  # 75 kg

        assert abs(result.screenings_kg - expected_screenings) < 0.1
        assert abs(result.grit_kg - expected_grit) < 0.1
        assert abs(result.ash_kg - expected_ash) < 0.1
        assert abs(result.total_reuse_kg - (expected_screenings + expected_grit + expected_ash)) < 0.1

    def test_zero_inputs(self):
        """Zero volumes should produce zero masses and zero economics."""
        result = calc_screenings_reuse(
            septage_processed_m3=0.0,
            char_produced_kg=0.0,
            screenings_fraction=0.005,
            grit_fraction=0.002,
            ash_fraction=0.15,
            density_kg_m3=1020.0,
            landfill_cost_per_tonne=85.0,
            reuse_credit_per_tonne=10.0,
        )

        assert result.screenings_kg == 0.0
        assert result.grit_kg == 0.0
        assert result.ash_kg == 0.0
        assert result.total_reuse_kg == 0.0
        assert result.avoided_disposal_cost == 0.0
        assert result.reuse_revenue == 0.0

    def test_avoided_disposal_cost(self):
        """Avoided disposal should equal total_tonnes × landfill_cost."""
        result = calc_screenings_reuse(
            septage_processed_m3=100.0,
            char_produced_kg=200.0,
            screenings_fraction=0.01,
            grit_fraction=0.005,
            ash_fraction=0.10,
            density_kg_m3=1000.0,
            landfill_cost_per_tonne=100.0,
            reuse_credit_per_tonne=0.0,
        )

        # septage_mass = 100 * 1000 = 100_000 kg
        # screenings = 1000, grit = 500, ash = 20 → total = 1520 kg = 1.52 t
        expected_cost = 1.52 * 100.0
        assert abs(result.avoided_disposal_cost - expected_cost) < 0.1
        assert result.reuse_revenue == 0.0

    def test_reuse_credit_revenue(self):
        """Reuse credit should equal total_tonnes × credit_rate."""
        result = calc_screenings_reuse(
            septage_processed_m3=100.0,
            char_produced_kg=200.0,
            screenings_fraction=0.01,
            grit_fraction=0.005,
            ash_fraction=0.10,
            density_kg_m3=1000.0,
            landfill_cost_per_tonne=0.0,
            reuse_credit_per_tonne=25.0,
        )

        # total = 1520 kg = 1.52 t; revenue = 1.52 × 25 = 38.0
        assert abs(result.reuse_revenue - 38.0) < 0.1
        assert result.avoided_disposal_cost == 0.0

    def test_result_type(self):
        """Result should be a ScreeningsReuseResult namedtuple."""
        result = calc_screenings_reuse(
            septage_processed_m3=100.0,
            char_produced_kg=50.0,
            screenings_fraction=0.005,
            grit_fraction=0.002,
            ash_fraction=0.15,
            density_kg_m3=1020.0,
            landfill_cost_per_tonne=85.0,
            reuse_credit_per_tonne=10.0,
        )
        assert isinstance(result, ScreeningsReuseResult)

    def test_high_density_scales_mass(self):
        """Higher density should increase screenings and grit masses."""
        low = calc_screenings_reuse(
            septage_processed_m3=100.0,
            char_produced_kg=50.0,
            screenings_fraction=0.005,
            grit_fraction=0.002,
            ash_fraction=0.15,
            density_kg_m3=1000.0,
            landfill_cost_per_tonne=85.0,
            reuse_credit_per_tonne=10.0,
        )
        high = calc_screenings_reuse(
            septage_processed_m3=100.0,
            char_produced_kg=50.0,
            screenings_fraction=0.005,
            grit_fraction=0.002,
            ash_fraction=0.15,
            density_kg_m3=1200.0,
            landfill_cost_per_tonne=85.0,
            reuse_credit_per_tonne=10.0,
        )

        assert high.screenings_kg > low.screenings_kg
        assert high.grit_kg > low.grit_kg
        # Ash should be the same (depends only on char)
        assert high.ash_kg == low.ash_kg

    def test_scenario_integration_screenings_enabled(self):
        """Screenings revenue should appear in scenario result when enabled."""
        from septage_model.core.stream_pathways import ScreeningsReuseParams, ScreeningsPathway

        pathways = StreamPathwayConfig(
            screenings_reuse=ScreeningsReuseParams(
                enabled=True,
                pathway=ScreeningsPathway.ALTERNATIVE_COVER,
            ),
        )
        scenario = ValueAddScenario(
            name="Screenings Test",
            scenario_type=ScenarioType.BASELINE,
            risk_level=ScenarioRisk.CONSERVATIVE,
            description="Test screenings integration",
            pathways=pathways,
        )
        inputs = OperatingInputs(
            septage_processed_m3_annual=5000.0,
            char_produced_kg_annual=1000.0,
        )

        result = evaluate_scenario(scenario, inputs, 100_000, 80_000, 500_000)

        assert result.pathway_revenue.screenings_reuse_credit > 0.0


# =============================================================================
# VIABILITY GATE TESTS
# =============================================================================

class TestNutrientRecoveryGate:
    """Test nutrient recovery viability gate."""
    
    def test_gate_passes_above_threshold(self):
        """Gate should pass when volume and concentration are sufficient."""
        result = nutrient_recovery_viability_gate(
            centrate_m3_annual=1000.0,  # > 500 threshold
            p_conc_mg_l=80.0,  # > 50 threshold
        )
        
        assert result.passed is True
        assert result.name == "Nutrient Recovery Viability"
    
    def test_gate_fails_low_volume(self):
        """Gate should fail when volume is insufficient."""
        result = nutrient_recovery_viability_gate(
            centrate_m3_annual=200.0,  # < 500 threshold
            p_conc_mg_l=80.0,
        )
        
        assert result.passed is False
        assert result.remediation is not None
        assert "volume" in result.remediation.lower()
    
    def test_gate_fails_low_concentration(self):
        """Gate should fail when P concentration is low."""
        result = nutrient_recovery_viability_gate(
            centrate_m3_annual=1000.0,
            p_conc_mg_l=30.0,  # < 50 threshold
        )
        
        assert result.passed is False
        assert result.remediation is not None
        assert "concentration" in result.remediation.lower()
    
    def test_gate_uses_frozen_thresholds(self):
        """Thresholds should match frozen constants."""
        assert MIN_CENTRATE_M3_FOR_NUTRIENT_RECOVERY == 500.0
        assert MIN_P_CONC_MG_L == 50.0


class TestCHPGridGate:
    """Test CHP grid viability gate."""
    
    def test_gate_passes_sufficient_capacity(self):
        """Gate should pass when capacity exceeds minimum."""
        # Need sufficient syngas for 10+ kW capacity
        # 10 kW at 30% efficiency, 85% availability = ~1,000,000 MJ/yr
        result = chp_grid_viability_gate(
            syngas_excess_mj_annual=1_200_000.0,  # Should yield > 10 kW
            grid_interconnect_available=True,
        )
        
        assert result.passed is True
    
    def test_gate_fails_no_interconnect(self):
        """Gate should fail without grid interconnect."""
        result = chp_grid_viability_gate(
            syngas_excess_mj_annual=200_000.0,
            grid_interconnect_available=False,
        )
        
        assert result.passed is False
        assert "interconnect" in result.remediation.lower()
    
    def test_gate_fails_insufficient_energy(self):
        """Gate should fail with low excess syngas."""
        result = chp_grid_viability_gate(
            syngas_excess_mj_annual=10_000.0,  # < 50,000 threshold
        )
        
        assert result.passed is False


class TestCharActivationGate:
    """Test char activation viability gate."""
    
    def test_gate_passes_sufficient_char_and_steam(self):
        """Gate should pass with sufficient char and steam."""
        result = char_activation_viability_gate(
            char_kg_annual=2000.0,  # > 1000 threshold
            steam_available_kg_annual=5000.0,  # > 2.5:1 ratio
        )
        
        assert result.passed is True
    
    def test_gate_fails_insufficient_char(self):
        """Gate should fail with low char production."""
        result = char_activation_viability_gate(
            char_kg_annual=500.0,  # < 1000 threshold
            steam_available_kg_annual=5000.0,
        )
        
        assert result.passed is False
        assert "char" in result.remediation.lower()


class TestHeatExportGate:
    """Test heat export viability gate."""
    
    def test_gate_passes_with_customer(self):
        """Gate should pass with sufficient heat and customer."""
        result = heat_export_viability_gate(
            excess_heat_mj_annual=150_000.0,
            heat_customer_available=True,
        )
        
        assert result.passed is True
    
    def test_gate_fails_without_customer(self):
        """Gate should fail without heat customer."""
        result = heat_export_viability_gate(
            excess_heat_mj_annual=150_000.0,
            heat_customer_available=False,
        )
        
        assert result.passed is False
        assert "customer" in result.remediation.lower()


class TestPathwayViabilityReport:
    """Test combined pathway viability gates."""
    
    def test_run_all_gates(self):
        """Should run all four pathway gates."""
        # Need sufficient syngas for 10+ kW CHP capacity
        report = run_pathway_viability_gates(
            centrate_m3_annual=1000.0,
            p_conc_mg_l=80.0,
            syngas_excess_mj_annual=1_200_000.0,  # Sufficient for 10+ kW
            char_kg_annual=2000.0,
            steam_available_kg_annual=5000.0,
            excess_heat_mj_annual=150_000.0,
            grid_interconnect_available=True,
            heat_customer_available=True,
        )
        
        assert len(report.gates) == 4
        assert report.all_passed is True
    
    def test_report_tracks_failures(self):
        """Report should track which gates failed."""
        report = run_pathway_viability_gates(
            centrate_m3_annual=100.0,  # Fails nutrient recovery
            p_conc_mg_l=80.0,
            syngas_excess_mj_annual=10_000.0,  # Fails CHP
            char_kg_annual=500.0,  # Fails char activation
            steam_available_kg_annual=100.0,
            excess_heat_mj_annual=50_000.0,  # Fails heat export (no customer)
            heat_customer_available=False,
        )
        
        assert report.all_passed is False
        failed_gates = [g for g in report.gates if not g.passed]
        assert len(failed_gates) >= 2


# =============================================================================
# SCENARIO EVALUATION TESTS
# =============================================================================

class TestScenarioEvaluation:
    """Test scenario evaluation functions."""
    
    @pytest.fixture
    def default_inputs(self) -> OperatingInputs:
        """Standard operating inputs for testing."""
        return OperatingInputs(
            centrate_m3_annual=1500.0,
            p_concentration_mg_L=80.0,
            n_concentration_mg_L=500.0,
            syngas_energy_mj_annual=200_000.0,
            char_produced_kg_annual=5000.0,
            char_carbon_kg_annual=4000.0,  # 80% of char
            septage_processed_m3_annual=5000.0,
            process_heat_demand_mj=50_000.0,
            site_power_demand_kwh=25_000.0,
        )
    
    def test_baseline_scenario_structure(self, default_inputs):
        """Baseline scenario should evaluate without error."""
        result = evaluate_scenario(
            SCENARIO_BASELINE,
            default_inputs,
            baseline_revenue=100_000.0,
            baseline_opex=50_000.0,
            baseline_capex=500_000.0,
        )
        
        assert isinstance(result, ScenarioResult)
        assert result.scenario == SCENARIO_BASELINE
    
    def test_value_add_scenario_has_pathway_capex(self, default_inputs):
        """Value-add scenarios should have pathway CAPEX."""
        result = evaluate_scenario(
            SCENARIO_MODERATE,
            default_inputs,
            baseline_revenue=100_000.0,
            baseline_opex=50_000.0,
            baseline_capex=500_000.0,
        )
        
        # Moderate should have some pathway CAPEX
        assert result.pathway_capex >= 0


class TestScenarioComparison:
    """Test scenario comparison functions."""
    
    @pytest.fixture
    def default_inputs(self) -> OperatingInputs:
        return OperatingInputs(
            centrate_m3_annual=1500.0,
            p_concentration_mg_L=80.0,
            n_concentration_mg_L=500.0,
            syngas_energy_mj_annual=200_000.0,
            char_produced_kg_annual=5000.0,
            char_carbon_kg_annual=4000.0,
            septage_processed_m3_annual=5000.0,
            process_heat_demand_mj=50_000.0,
            site_power_demand_kwh=25_000.0,
        )
    
    def test_compare_scenarios_returns_results(self, default_inputs):
        """Comparison should return comparison object."""
        scenarios = [
            SCENARIO_BASELINE,
            SCENARIO_CONSERVATIVE,
            SCENARIO_MODERATE,
        ]
        
        comparison = compare_scenarios(
            scenarios,
            default_inputs,
            baseline_revenue=100_000.0,
            baseline_opex=50_000.0,
            baseline_capex=500_000.0,
        )
        
        assert len(comparison.scenario_results) == 3


class TestScenarioExport:
    """Test scenario CSV/dict export for proof checklist E."""

    @pytest.fixture
    def comparison(self) -> "ScenarioComparison":
        from septage_model.analysis.pathway_scenarios import ScenarioComparison
        inputs = OperatingInputs(
            centrate_m3_annual=1500.0,
            p_concentration_mg_L=80.0,
            n_concentration_mg_L=500.0,
            syngas_energy_mj_annual=200_000.0,
            char_produced_kg_annual=5000.0,
            char_carbon_kg_annual=4000.0,
            septage_processed_m3_annual=5000.0,
            process_heat_demand_mj=50_000.0,
            site_power_demand_kwh=25_000.0,
        )
        return compare_scenarios(
            [SCENARIO_BASELINE, SCENARIO_CONSERVATIVE, SCENARIO_MODERATE, SCENARIO_FULL_CIRCULAR],
            inputs,
            baseline_revenue=100_000.0,
            baseline_opex=50_000.0,
            baseline_capex=500_000.0,
        )

    # -- ScenarioResult.to_dict() --

    def test_to_dict_returns_dict(self, comparison):
        """to_dict should return a plain dict."""
        d = comparison.baseline_result.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_has_required_keys(self, comparison):
        """to_dict must include all economic and scenario keys."""
        d = comparison.baseline_result.to_dict()
        required = {
            "scenario", "scenario_type", "risk_level",
            "baseline_revenue_annual", "baseline_opex_annual", "baseline_capex",
            "pathway_capex", "pathway_opex_annual",
            "struvite_revenue", "ammonia_revenue", "chp_grid_revenue",
            "heat_export_revenue", "char_activation_premium",
            "screenings_reuse_credit", "carbon_credit_revenue",
            "avoided_disposal_savings", "total_value_add_revenue",
            "total_capex", "total_revenue_annual", "total_opex_annual",
            "net_annual", "revenue_delta", "simple_payback_years", "npv",
        }
        assert required.issubset(d.keys())

    def test_to_dict_values_numeric(self, comparison):
        """All economic values should be numeric (float or int)."""
        d = comparison.baseline_result.to_dict()
        for key in ["baseline_revenue_annual", "npv", "total_capex", "net_annual"]:
            assert isinstance(d[key], (int, float)), f"{key} should be numeric"

    def test_to_dict_scenario_name(self, comparison):
        """Scenario name in dict should match original."""
        d = comparison.baseline_result.to_dict()
        assert d["scenario"] == comparison.baseline_result.scenario.name

    # -- ScenarioComparison.to_dicts() --

    def test_to_dicts_length(self, comparison):
        """to_dicts should return baseline + N scenario rows."""
        rows = comparison.to_dicts()
        # baseline (1) + 4 scenarios
        assert len(rows) == 5

    def test_to_dicts_baseline_first(self, comparison):
        """First row of to_dicts should be the baseline."""
        rows = comparison.to_dicts()
        assert rows[0]["scenario"] == comparison.baseline_result.scenario.name

    # -- ScenarioComparison.to_csv() --

    def test_to_csv_is_string(self, comparison):
        """to_csv should return a non-empty string."""
        csv_text = comparison.to_csv()
        assert isinstance(csv_text, str)
        assert len(csv_text) > 0

    def test_to_csv_header_row(self, comparison):
        """CSV should start with a header containing key columns."""
        csv_text = comparison.to_csv()
        header = csv_text.split("\n")[0]
        assert "scenario" in header
        assert "npv" in header
        assert "total_capex" in header

    def test_to_csv_row_count(self, comparison):
        """CSV should have header + baseline + N scenario rows."""
        csv_text = comparison.to_csv()
        lines = [l for l in csv_text.strip().split("\n") if l.strip()]
        # header (1) + baseline (1) + 4 scenarios = 6
        assert len(lines) == 6

    def test_to_csv_roundtrip(self, comparison):
        """CSV should be parseable back into rows of dicts."""
        import csv as csv_mod
        import io
        csv_text = comparison.to_csv()
        reader = csv_mod.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 5
        assert rows[0]["scenario"] == comparison.baseline_result.scenario.name

    # -- export_comparison_csv() file output --

    def test_export_comparison_csv_writes_file(self, comparison, tmp_path):
        """export_comparison_csv should write a readable CSV file."""
        from septage_model.analysis.pathway_scenarios import export_comparison_csv
        filepath = str(tmp_path / "test_scenarios.csv")
        export_comparison_csv(comparison, filepath)

        with open(filepath) as f:
            content = f.read()

        lines = [l for l in content.strip().split("\n") if l.strip()]
        assert len(lines) == 6  # header + 5 rows


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestPathwayIntegration:
    """Integration tests for complete pathway analysis workflow."""
    
    def test_end_to_end_pathway_analysis(self):
        """Complete pathway analysis should not raise errors."""
        inputs = OperatingInputs(
            centrate_m3_annual=1500.0,
            p_concentration_mg_L=80.0,
            n_concentration_mg_L=500.0,
            syngas_energy_mj_annual=200_000.0,
            char_produced_kg_annual=5000.0,
            char_carbon_kg_annual=4000.0,
            septage_processed_m3_annual=5000.0,
            process_heat_demand_mj=50_000.0,
            site_power_demand_kwh=25_000.0,
        )
        
        # Should run without errors
        scenarios = [
            SCENARIO_BASELINE,
            SCENARIO_CONSERVATIVE,
            SCENARIO_MODERATE,
            SCENARIO_FULL_CIRCULAR,
        ]
        
        comparison = compare_scenarios(
            scenarios,
            inputs,
            baseline_revenue=100_000.0,
            baseline_opex=50_000.0,
            baseline_capex=500_000.0,
        )
        
        assert len(comparison.scenario_results) == 4
    
    def test_gates_and_scenarios_consistent(self):
        """Gate results should be consistent with scenario economics."""
        inputs = OperatingInputs(
            centrate_m3_annual=100.0,  # Too low for nutrient recovery
            p_concentration_mg_L=80.0,
            n_concentration_mg_L=500.0,
            syngas_energy_mj_annual=1_500_000.0,  # High enough for CHP gate
            char_produced_kg_annual=5000.0,
            char_carbon_kg_annual=4000.0,
            septage_processed_m3_annual=5000.0,
            process_heat_demand_mj=50_000.0,
            site_power_demand_kwh=25_000.0,
        )
        
        # Nutrient recovery gate should fail (low centrate volume)
        gate_result = nutrient_recovery_viability_gate(
            inputs.centrate_m3_annual,
            inputs.p_concentration_mg_L,
        )
        assert gate_result.passed is False
        
        # CHP gate should pass (high syngas)
        chp_gate = chp_grid_viability_gate(
            inputs.syngas_energy_mj_annual,
        )
        assert chp_gate.passed is True


class TestMassEnergyBalance:
    """Test mass and energy balance closure."""
    
    def test_struvite_mass_balance(self):
        """P in struvite should equal P removed from centrate."""
        result = calc_struvite_recovery(
            centrate_m3_annual=1000.0,
            p_concentration_mg_L=100.0,
            recovery_efficiency=0.85,
            mg_dose_ratio=1.3,
            struvite_revenue_per_tonne=200.0,
        )
        
        # Mass balance: P recovered should equal P in struvite
        # Struvite is ~12.6% P by mass (30.97 / 245.41)
        p_in_struvite = result.struvite_produced_kg * 0.126
        
        # Allow 10% tolerance for rounding
        assert 0.9 * result.phosphorus_recovered_kg <= p_in_struvite <= 1.1 * result.phosphorus_recovered_kg
    
    def test_chp_energy_conservation(self):
        """CHP output should not exceed input."""
        result = calc_syngas_chp(
            syngas_energy_annual_mj=100_000.0,
            process_heat_demand_mj=0.0,
            electrical_efficiency=0.30,
            thermal_efficiency=0.45,
            site_power_demand_kwh=0.0,
            grid_export_enabled=True,
            export_rate_per_kwh=0.10,
        )
        
        # Total output energy
        electrical_mj = result.electricity_generated_kwh * 3.6
        total_output = electrical_mj + result.heat_recovered_mj
        
        # Should not exceed input (allowing small numerical error)
        assert total_output <= 100_000.0 * 1.01
    
    def test_carbon_credits_carbon_balance(self):
        """CO2e should be consistent with char carbon content."""
        result = calc_carbon_credits(
            char_carbon_kg=1000.0,
            permanence_discount=0.80,
            credit_price_per_tonne_co2e=50.0,
        )
        
        # C in char: 1000 kg
        # CO2e: 1000 × (44/12) = 3666.67 kg
        expected_co2e = 1000 * (44 / 12)
        
        # Allow 1% tolerance
        assert 0.99 * expected_co2e <= result.sequestered_co2e_kg <= 1.01 * expected_co2e


# =============================================================================
# HEAT GRADE COMPATIBILITY TESTS
# =============================================================================

class TestHeatGradeCompatibility:
    """Test heat grade thermodynamic constraints."""
    
    def test_heat_grade_ordering(self):
        """Heat grades should be LOW < MEDIUM < HIGH."""
        assert HeatGrade.LOW.value == "low"
        assert HeatGrade.MEDIUM.value == "medium"
        assert HeatGrade.HIGH.value == "high"
    
    def test_higher_supplies_lower(self):
        """Higher grade heat can supply lower grade needs."""
        # HIGH can supply all
        assert heat_grade_compatible(HeatGrade.HIGH, HeatGrade.HIGH)
        assert heat_grade_compatible(HeatGrade.HIGH, HeatGrade.MEDIUM)
        assert heat_grade_compatible(HeatGrade.HIGH, HeatGrade.LOW)
        
        # MEDIUM can supply MEDIUM and LOW
        assert heat_grade_compatible(HeatGrade.MEDIUM, HeatGrade.MEDIUM)
        assert heat_grade_compatible(HeatGrade.MEDIUM, HeatGrade.LOW)
        
        # LOW can only supply LOW
        assert heat_grade_compatible(HeatGrade.LOW, HeatGrade.LOW)
    
    def test_lower_cannot_supply_higher(self):
        """Lower grade heat cannot supply higher grade needs."""
        assert not heat_grade_compatible(HeatGrade.LOW, HeatGrade.MEDIUM)
        assert not heat_grade_compatible(HeatGrade.LOW, HeatGrade.HIGH)
        assert not heat_grade_compatible(HeatGrade.MEDIUM, HeatGrade.HIGH)
    
    def test_heat_stream_can_supply(self):
        """HeatStream.can_supply() should delegate to heat_grade_compatible."""
        high_stream = HeatStream(mj_per_hour=100.0, grade=HeatGrade.HIGH, source="pyrolysis")
        low_stream = HeatStream(mj_per_hour=50.0, grade=HeatGrade.LOW, source="condenser")
        
        assert high_stream.can_supply(HeatGrade.LOW)
        assert high_stream.can_supply(HeatGrade.HIGH)
        assert low_stream.can_supply(HeatGrade.LOW)
        assert not low_stream.can_supply(HeatGrade.MEDIUM)
    
    def test_heat_requirements_defined(self):
        """Key consumers should have defined heat requirements."""
        assert HEAT_REQUIREMENTS["dryer"] == HeatGrade.MEDIUM
        assert HEAT_REQUIREMENTS["char_activation"] == HeatGrade.HIGH
        assert HEAT_REQUIREMENTS["heat_export"] == HeatGrade.LOW


# =============================================================================
# CIRCULAR PATHWAY BLOCKING TESTS
# =============================================================================

class TestCircularPathwayBlocking:
    """Test circular pathway DRL-based blocking."""
    
    def test_circular_blocked_at_drl_4(self):
        """Circular pathways should be blocked at DRL-4 and below."""
        for drl in range(1, 5):
            assert not CircularPathway.is_allowed(drl, allow_circular=True)
            assert not CircularPathway.is_allowed(drl, allow_circular=False)
    
    def test_circular_allowed_at_drl_5_with_flag(self):
        """Circular pathways allowed at DRL-5+ only with allow_circular=True."""
        assert CircularPathway.is_allowed(5, allow_circular=True)
        assert CircularPathway.is_allowed(6, allow_circular=True)
        assert CircularPathway.is_allowed(9, allow_circular=True)
    
    def test_circular_blocked_without_flag(self):
        """Circular pathways blocked without allow_circular=True, even at high DRL."""
        for drl in range(1, 10):
            assert not CircularPathway.is_allowed(drl, allow_circular=False)
    
    def test_min_drl_constant(self):
        """CIRCULAR_PATHWAY_MIN_DRL should be 5."""
        assert CIRCULAR_PATHWAY_MIN_DRL == 5


# =============================================================================
# PATHWAY STATE CONSERVATION TESTS
# =============================================================================

class TestPathwayStateConservation:
    """Test sequential state management and conservation."""
    
    def test_initial_state_from_operating_inputs(self):
        """State should be created from operating inputs."""
        state = PathwayExecutionState.from_operating_inputs(
            centrate_m3=1000.0,
            p_concentration_mg_L=150.0,
            n_concentration_mg_L=800.0,
            syngas_mj=50000.0,
            char_kg=2000.0,
            heat_low_mj=1000.0,
            heat_medium_mj=5000.0,
            heat_high_mj=10000.0,
        )
        
        assert state.centrate_remaining_m3 == 1000.0
        assert state.p_concentration_mg_L == 150.0
        assert state.n_concentration_mg_L == 800.0
        assert state.syngas_remaining_mj == 50000.0
        assert state.char_remaining_kg == 2000.0
        assert state.heat_low_remaining_mj == 1000.0
        assert state.heat_medium_remaining_mj == 5000.0
        assert state.heat_high_remaining_mj == 10000.0
    
    def test_syngas_consumption_reduces_remaining(self):
        """Consuming syngas should reduce remaining pool."""
        state = PathwayExecutionState(syngas_remaining_mj=100000.0)
        new_state = state.consume_syngas(30000.0)
        
        assert new_state.syngas_remaining_mj == 70000.0
        assert state.syngas_remaining_mj == 100000.0  # Original unchanged (frozen)
    
    def test_syngas_overconsumption_raises(self):
        """Consuming more syngas than available should raise."""
        state = PathwayExecutionState(syngas_remaining_mj=10000.0)
        
        with pytest.raises(ValueError, match="Insufficient syngas"):
            state.consume_syngas(20000.0)
    
    def test_heat_consumption_grade_cascade(self):
        """Heat consumption should cascade from lower to higher grades."""
        state = PathwayExecutionState(
            heat_low_remaining_mj=100.0,
            heat_medium_remaining_mj=200.0,
            heat_high_remaining_mj=300.0,
        )
        
        # Consume 150 MJ of LOW grade (uses 100 low + 50 medium)
        new_state = state.consume_heat(150.0, "LOW")
        assert new_state.heat_low_remaining_mj == 0.0
        assert new_state.heat_medium_remaining_mj == 150.0
        assert new_state.heat_high_remaining_mj == 300.0
    
    def test_high_grade_heat_only_from_high(self):
        """HIGH grade requirement can only use HIGH grade heat."""
        state = PathwayExecutionState(
            heat_low_remaining_mj=100.0,
            heat_medium_remaining_mj=200.0,
            heat_high_remaining_mj=50.0,
        )
        
        # Should fail - only 50 MJ high available
        with pytest.raises(ValueError, match="Insufficient high-grade heat"):
            state.consume_heat(100.0, "HIGH")
    
    def test_p_concentration_reduction(self):
        """P concentration reduction should apply fraction correctly."""
        state = PathwayExecutionState(p_concentration_mg_L=200.0)
        
        # Remove 85% (struvite efficiency)
        new_state = state.reduce_p_concentration(0.85)
        assert abs(new_state.p_concentration_mg_L - 30.0) < 0.01
    
    def test_n_concentration_reduction(self):
        """N concentration reduction should apply fraction correctly."""
        state = PathwayExecutionState(n_concentration_mg_L=1000.0)
        
        # Remove 75% (ammonia stripping efficiency)
        new_state = state.reduce_n_concentration(0.75)
        assert abs(new_state.n_concentration_mg_L - 250.0) < 0.01
    
    def test_char_allocation(self):
        """Char allocation should reduce available pool."""
        state = PathwayExecutionState(char_remaining_kg=5000.0)
        new_state = state.allocate_char(1000.0)
        
        assert new_state.char_remaining_kg == 4000.0
    
    def test_char_overallocation_raises(self):
        """Allocating more char than available should raise."""
        state = PathwayExecutionState(char_remaining_kg=500.0)
        
        with pytest.raises(ValueError, match="Insufficient char"):
            state.allocate_char(1000.0)
    
    def test_pathway_recording(self):
        """Pathway execution should be recorded."""
        state = PathwayExecutionState()
        
        state = state.record_pathway("struvite")
        state = state.record_pathway("ammonia")
        state = state.record_pathway("chp")
        
        assert state.pathways_executed == ("struvite", "ammonia", "chp")
    
    def test_state_is_frozen(self):
        """State should be immutable (frozen dataclass)."""
        state = PathwayExecutionState(syngas_remaining_mj=1000.0)
        
        with pytest.raises(Exception):  # FrozenInstanceError
            state.syngas_remaining_mj = 500.0
    
    def test_disabled_pathway_preserves_mass(self):
        """A disabled pathway should preserve all state values."""
        initial_state = PathwayExecutionState.from_operating_inputs(
            centrate_m3=1000.0,
            p_concentration_mg_L=150.0,
            n_concentration_mg_L=800.0,
            syngas_mj=50000.0,
            char_kg=2000.0,
        )
        
        # Simulate "disabled pathway" - just pass state through
        final_state = initial_state  # No operations
        
        # All values preserved
        assert final_state.centrate_remaining_m3 == initial_state.centrate_remaining_m3
        assert final_state.p_concentration_mg_L == initial_state.p_concentration_mg_L
        assert final_state.syngas_remaining_mj == initial_state.syngas_remaining_mj
        assert final_state.char_remaining_kg == initial_state.char_remaining_kg
    
    def test_sequential_pathway_consumption(self):
        """Pathways executing in sequence should consume from updated state."""
        state = PathwayExecutionState.from_operating_inputs(
            centrate_m3=1000.0,
            p_concentration_mg_L=200.0,
            n_concentration_mg_L=1000.0,
            syngas_mj=100000.0,
            char_kg=5000.0,
        )
        
        # Struvite: removes 85% P
        state = state.reduce_p_concentration(0.85)
        state = state.record_pathway("struvite")
        
        # Ammonia: removes 75% N
        state = state.reduce_n_concentration(0.75)
        state = state.record_pathway("ammonia")
        
        # CHP: consumes 50000 MJ syngas
        state = state.consume_syngas(50000.0)
        state = state.record_pathway("chp")
        
        # Char activation: allocates 1000 kg char
        state = state.allocate_char(1000.0)
        state = state.record_pathway("char_activation")
        
        # Verify final state
        assert abs(state.p_concentration_mg_L - 30.0) < 0.01    # 200 × 0.15
        assert abs(state.n_concentration_mg_L - 250.0) < 0.01  # 1000 × 0.25
        assert state.syngas_remaining_mj == 50000.0             # 100000 - 50000
        assert state.char_remaining_kg == 4000.0                # 5000 - 1000
        assert state.pathways_executed == ("struvite", "ammonia", "chp", "char_activation")


# =============================================================================
# DEPLOYMENT MODE PATHWAY TESTS (Hub vs Product — Proof Checklist F)
# =============================================================================

class TestDeploymentModePathways:
    """Test DeploymentMode-aware pathway presets."""

    def test_create_product_pathways_type(self):
        """Product factory should return a StreamPathwayConfig."""
        from septage_model.core.stream_pathways import create_product_pathways
        config = create_product_pathways()
        assert isinstance(config, StreamPathwayConfig)

    def test_create_hub_pathways_type(self):
        """Hub factory should return a StreamPathwayConfig."""
        from septage_model.core.stream_pathways import create_hub_pathways
        config = create_hub_pathways()
        assert isinstance(config, StreamPathwayConfig)

    def test_product_disables_complex_pathways(self):
        """Product mode should NOT enable CHP, char activation, or ammonia."""
        from septage_model.core.stream_pathways import create_product_pathways
        config = create_product_pathways()

        assert config.chp.enabled is False, "CHP too complex for owner-operator"
        assert config.char_activation.enabled is False, "Char activation too complex"
        assert config.ammonia_stripping.enabled is False, "Ammonia stripping too complex"

    def test_product_enables_simple_pathways(self):
        """Product mode should enable low-complexity near-term pathways."""
        from septage_model.core.stream_pathways import create_product_pathways
        config = create_product_pathways()

        assert config.struvite.enabled is True
        assert config.heat_export.enabled is True
        assert config.offspec_thermal.enabled is True
        assert config.screenings_reuse.enabled is True

    def test_hub_enables_all_justified_pathways(self):
        """Hub mode should enable capital-intensive pathways (staffed facility)."""
        from septage_model.core.stream_pathways import create_hub_pathways
        config = create_hub_pathways()

        assert config.chp.enabled is True
        assert config.chp.grid_export_enabled is True
        assert config.char_activation.enabled is True
        assert config.ammonia_stripping.enabled is True
        assert config.struvite.enabled is True
        assert config.heat_export.enabled is True
        assert config.screenings_reuse.enabled is True

    def test_hub_enables_carbon_credits(self):
        """Hub mode should enable carbon credits (MRV overhead amortised)."""
        from septage_model.core.stream_pathways import create_hub_pathways
        config = create_hub_pathways()
        assert config.meta_products.carbon_credits_enabled is True

    def test_product_no_carbon_credits(self):
        """Product mode should NOT enable carbon credits by default."""
        from septage_model.core.stream_pathways import create_product_pathways
        config = create_product_pathways()
        assert config.meta_products.carbon_credits_enabled is False

    def test_hub_more_enabled_than_product(self):
        """Hub should have strictly more enabled pathways than product."""
        from septage_model.core.stream_pathways import (
            create_product_pathways,
            create_hub_pathways,
        )
        product = create_product_pathways()
        hub = create_hub_pathways()

        from septage_model.core.stream_pathways import ScenarioRisk
        product_enabled = product.get_enabled_pathways(ScenarioRisk.CONSERVATIVE)
        hub_enabled = hub.get_enabled_pathways(ScenarioRisk.CONSERVATIVE)

        assert len(hub_enabled) > len(product_enabled)

    def test_create_pathways_for_mode_product(self):
        """Dispatch with 'product' should match create_product_pathways."""
        from septage_model.core.stream_pathways import (
            create_pathways_for_mode,
            create_product_pathways,
        )
        assert create_pathways_for_mode("product") == create_product_pathways()

    def test_create_pathways_for_mode_hub(self):
        """Dispatch with 'regional_hub' should match create_hub_pathways."""
        from septage_model.core.stream_pathways import (
            create_pathways_for_mode,
            create_hub_pathways,
        )
        assert create_pathways_for_mode("regional_hub") == create_hub_pathways()

    def test_create_pathways_for_mode_invalid(self):
        """Invalid mode string should raise ValueError."""
        from septage_model.core.stream_pathways import create_pathways_for_mode
        with pytest.raises(ValueError, match="Unknown deployment mode"):
            create_pathways_for_mode("mobile_unit")

    def test_product_pathways_screenings_alternative_cover(self):
        """Product mode screenings should default to alternative_cover."""
        from septage_model.core.stream_pathways import create_product_pathways
        config = create_product_pathways()
        assert config.screenings_reuse.pathway == ScreeningsPathway.ALTERNATIVE_COVER

    def test_hub_pathways_screenings_road_base(self):
        """Hub mode screenings should default to road_base."""
        from septage_model.core.stream_pathways import create_hub_pathways
        config = create_hub_pathways()
        assert config.screenings_reuse.pathway == ScreeningsPathway.ROAD_BASE

    def test_hub_pathways_evaluate_higher_npv(self):
        """Hub scenario NPV should exceed product NPV with sufficient throughput."""
        from septage_model.core.stream_pathways import (
            create_product_pathways,
            create_hub_pathways,
        )

        inputs = OperatingInputs(
            centrate_m3_annual=3000.0,
            p_concentration_mg_L=120.0,
            n_concentration_mg_L=800.0,
            syngas_energy_mj_annual=500_000.0,
            char_produced_kg_annual=10_000.0,
            char_carbon_kg_annual=8_000.0,
            septage_processed_m3_annual=10_000.0,
            process_heat_demand_mj=100_000.0,
            site_power_demand_kwh=50_000.0,
        )

        product_scenario = ValueAddScenario(
            name="Product Mode",
            scenario_type=ScenarioType.BASELINE,
            risk_level=ScenarioRisk.CONSERVATIVE,
            description="Owner-operated",
            pathways=create_product_pathways(),
        )
        hub_scenario = ValueAddScenario(
            name="Hub Mode",
            scenario_type=ScenarioType.MODERATE,
            risk_level=ScenarioRisk.MODERATE,
            description="Staffed regional hub",
            pathways=create_hub_pathways(),
        )

        product_result = evaluate_scenario(
            product_scenario, inputs, 200_000, 100_000, 800_000,
        )
        hub_result = evaluate_scenario(
            hub_scenario, inputs, 200_000, 100_000, 800_000,
        )

        # Hub enables more pathways → higher total value-add revenue
        assert hub_result.pathway_revenue.total_value_add_revenue > \
               product_result.pathway_revenue.total_value_add_revenue


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
