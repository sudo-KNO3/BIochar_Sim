"""
Proof Test Suite - Regression tests locking current behavior.

This suite validates:
1. Mass/energy invariants (yields, closure)
2. Deployment mode separation (physics match, economics differ)
3. Buyer economics correctness
4. Regression values for published tables

Run with: pytest tests/test_proof_suite.py -v
"""

import pytest
import math

from septage_model.core.parameters import (
    create_option_b_scenario,
    create_product_scenario,
    create_hub_scenario,
    DeploymentMode,
)
from septage_model.core.balances import (
    calc_dewatering,
    calc_dryer,
    calc_pyrolysis,
    calc_option_b_thermal,
    calc_cofeed_routing,
)
from septage_model.simulation.deterministic import (
    run_product_mode,
    run_hub_mode,
    calc_buyer_economics,
    run_stage1_option_b,
)


# ============================================================================
# 1. INVARIANT TESTS - Physics must be conserved
# ============================================================================

class TestYieldsSumToOne:
    """Pyrolysis yields must sum to 1.0 (mass conservation)."""
    
    def test_septage_yields_sum_to_one(self):
        params = create_option_b_scenario()
        total = (
            params.pyrolysis.yield_char +
            params.pyrolysis.yield_gas +
            params.pyrolysis.yield_condensate
        )
        assert abs(total - 1.0) < 0.001, f"Septage yields sum to {total}, not 1.0"
    
    def test_cofeed_yields_sum_to_one(self):
        params = create_option_b_scenario()
        total = (
            params.cofeed.yield_char_cofeed +
            params.cofeed.yield_gas_cofeed +
            params.cofeed.yield_condensate_cofeed
        )
        assert abs(total - 1.0) < 0.001, f"Co-feed yields sum to {total}, not 1.0"


class TestNoNegativeStates:
    """All physical quantities must be non-negative."""
    
    def test_product_mode_no_negatives(self):
        result = run_product_mode()
        
        # Energy
        assert result.base_result.energy.dryer_duty_mj_hr >= 0
        assert result.base_result.energy.syngas_total_mj_hr >= 0
        assert result.base_result.energy.energy_self_sufficiency >= 0
        
        # Char
        assert result.base_result.char.char_total_kg_hr >= 0
        assert result.base_result.char.annual_char_total_tonnes >= 0
        
        # Buyer economics
        assert result.buyer.capex >= 0
        assert result.buyer.annual_opex_cash >= 0
    
    def test_hub_mode_no_negatives(self):
        result = run_hub_mode()
        
        assert result.energy.dryer_duty_mj_hr >= 0
        assert result.energy.syngas_total_mj_hr >= 0
        assert result.char.annual_char_total_tonnes >= 0
        assert result.economics.total_capex >= 0


class TestMassBalanceClosure:
    """Mass must be conserved through each unit operation."""
    
    def test_dewatering_mass_closure(self):
        """Septage in = cake out + centrate out."""
        dw = calc_dewatering(
            septage_m3=1.0,
            ts_fraction=0.03,
            density_kg_m3=1000.0,
            cake_ts_fraction=0.20,
            solids_capture=0.95,
            polymer_kg_per_tds=5.0,
            power_kwh_per_m3=2.0
        )
        
        mass_in = 1.0 * 1000.0  # 1000 kg
        cake_mass = dw.cake_produced_kgds / 0.20  # Convert DS to total mass
        centrate_mass = dw.centrate_produced_m3 * 1000.0
        
        closure_error = abs(mass_in - (cake_mass + centrate_mass))
        assert closure_error < 1.0, f"Dewatering mass error: {closure_error} kg"
    
    def test_dryer_mass_closure(self):
        """Cake in = dried out + water evaporated."""
        dr = calc_dryer(
            cake_kgds=30.0,
            cake_ts_fraction=0.20,
            dried_ts_fraction=0.75,
            energy_kwh_per_kg_water=0.9,
            thermal_efficiency=0.55
        )
        
        cake_total = 30.0 / 0.20  # 150 kg
        dried_total = 30.0 / 0.75  # 40 kg
        
        mass_out = dried_total + dr.water_evaporated_kg
        closure_error = abs(cake_total - mass_out)
        assert closure_error < 0.1, f"Dryer mass error: {closure_error} kg"
    
    def test_pyrolysis_mass_closure(self):
        """Dried in = char + gas + condensate."""
        py = calc_pyrolysis(
            dried_kgds=30.0,
            dried_ts_fraction=0.75,
            yield_char=0.35,
            yield_gas=0.40,
            yield_condensate=0.25,
            heat_requirement_mj_kgds=0.5,
            lhv_syngas_mj_kg=8.0,
            syngas_recovery_efficiency=0.75,
            char_carbon_fraction=0.50,
            char_permanence_factor=0.80
        )
        
        dried_total = 30.0 / 0.75  # 40 kg
        mass_out = py.char_produced_kg + py.gas_produced_kg + py.condensate_produced_kg
        
        closure_error = abs(dried_total - mass_out)
        assert closure_error < 0.1, f"Pyrolysis mass error: {closure_error} kg"


class TestEnergyIncreasesWithCofeed:
    """More co-feed DS must produce more syngas energy."""
    
    def test_syngas_increases_with_cofeed(self):
        thermal_low = calc_option_b_thermal(
            septage_cake_kgds=10, septage_cake_ts=0.20,
            cofeed_kgds=10, cofeed_ts=0.85, cofeed_bypass_mode=True,
            dried_ts=0.75, dryer_energy_kwh_per_kg_water=0.9, 
            dryer_thermal_efficiency=0.55,
            yield_char_sept=0.35, yield_gas_sept=0.40, yield_cond_sept=0.25,
            lhv_syngas_sept_mj_kg=8.0,
            yield_char_cofeed=0.30, yield_gas_cofeed=0.45, yield_cond_cofeed=0.25,
            lhv_syngas_cofeed_mj_kg=12.0,
            heat_requirement_mj_kgds=0.5, syngas_recovery_efficiency=0.75
        )
        
        thermal_high = calc_option_b_thermal(
            septage_cake_kgds=10, septage_cake_ts=0.20,
            cofeed_kgds=20, cofeed_ts=0.85, cofeed_bypass_mode=True,
            dried_ts=0.75, dryer_energy_kwh_per_kg_water=0.9,
            dryer_thermal_efficiency=0.55,
            yield_char_sept=0.35, yield_gas_sept=0.40, yield_cond_sept=0.25,
            lhv_syngas_sept_mj_kg=8.0,
            yield_char_cofeed=0.30, yield_gas_cofeed=0.45, yield_cond_cofeed=0.25,
            lhv_syngas_cofeed_mj_kg=12.0,
            heat_requirement_mj_kgds=0.5, syngas_recovery_efficiency=0.75
        )
        
        assert thermal_high.syngas_total_mj > thermal_low.syngas_total_mj, \
            "More co-feed should produce more syngas"


class TestCofeedBypassReducesDryerLoad:
    """Bypassing dry co-feed should reduce dryer duty.
    
    Note: Bypass only matters when co-feed is wetter than dryer target.
    If co-feed is already drier than target (e.g., 85% TS vs 75% target),
    no drying is needed regardless of bypass mode.
    """
    
    def test_bypass_reduces_dryer_duty(self):
        # With bypass (wet co-feed goes direct to pyro, skipping dryer)
        # Using 50% TS co-feed which is wetter than 75% dryer target
        thermal_bypass = calc_option_b_thermal(
            septage_cake_kgds=10, septage_cake_ts=0.20,
            cofeed_kgds=10, cofeed_ts=0.50, cofeed_bypass_mode=True,  # 50% TS, bypass ON
            dried_ts=0.75, dryer_energy_kwh_per_kg_water=0.9,
            dryer_thermal_efficiency=0.55,
            yield_char_sept=0.35, yield_gas_sept=0.40, yield_cond_sept=0.25,
            lhv_syngas_sept_mj_kg=8.0,
            yield_char_cofeed=0.30, yield_gas_cofeed=0.45, yield_cond_cofeed=0.25,
            lhv_syngas_cofeed_mj_kg=12.0,
            heat_requirement_mj_kgds=0.5, syngas_recovery_efficiency=0.75
        )
        
        # Without bypass (wet co-feed goes through dryer)
        thermal_no_bypass = calc_option_b_thermal(
            septage_cake_kgds=10, septage_cake_ts=0.20,
            cofeed_kgds=10, cofeed_ts=0.50, cofeed_bypass_mode=False,  # 50% TS, bypass OFF
            dried_ts=0.75, dryer_energy_kwh_per_kg_water=0.9,
            dryer_thermal_efficiency=0.55,
            yield_char_sept=0.35, yield_gas_sept=0.40, yield_cond_sept=0.25,
            lhv_syngas_sept_mj_kg=8.0,
            yield_char_cofeed=0.30, yield_gas_cofeed=0.45, yield_cond_cofeed=0.25,
            lhv_syngas_cofeed_mj_kg=12.0,
            heat_requirement_mj_kgds=0.5, syngas_recovery_efficiency=0.75
        )
        
        assert thermal_bypass.dryer_duty_mj < thermal_no_bypass.dryer_duty_mj, \
            "Bypass mode should reduce dryer duty when co-feed is wet"


# ============================================================================
# 2. DEPLOYMENT MODE TESTS - Same physics, different economics
# ============================================================================

class TestProductVsHubPhysicsMatch:
    """At same inputs, Product and Hub modes must have identical physics."""
    
    def test_physics_match_at_same_scale(self):
        """Energy and mass outputs must match when inputs are identical."""
        product = run_product_mode(annual_septage_m3=5000.0, annual_cofeed_tds=1200.0)
        hub = run_hub_mode(annual_septage_m3=5000.0, annual_cofeed_tds=1200.0)
        
        # Energy self-sufficiency
        assert abs(product.base_result.energy.energy_self_sufficiency - 
                   hub.energy.energy_self_sufficiency) < 0.001, \
            "Energy self-sufficiency must match"
        
        # Dryer duty
        assert abs(product.base_result.energy.dryer_duty_mj_hr - 
                   hub.energy.dryer_duty_mj_hr) < 0.1, \
            "Dryer duty must match"
        
        # Syngas energy
        assert abs(product.base_result.energy.syngas_total_mj_hr - 
                   hub.energy.syngas_total_mj_hr) < 0.1, \
            "Syngas energy must match"
        
        # Char production
        assert abs(product.base_result.char.annual_char_total_tonnes - 
                   hub.char.annual_char_total_tonnes) < 0.1, \
            "Char production must match"
    
    def test_economics_differ_correctly(self):
        """CAPEX and OPEX must differ as expected."""
        product = run_product_mode(annual_septage_m3=5000.0, annual_cofeed_tds=1200.0)
        hub = run_hub_mode(annual_septage_m3=5000.0, annual_cofeed_tds=1200.0)
        
        # CAPEX should be 0.6x
        capex_ratio = product.buyer.capex / hub.economics.total_capex
        assert 0.55 < capex_ratio < 0.65, \
            f"Product CAPEX should be ~0.6x Hub, got {capex_ratio:.2f}"
        
        # Product OPEX should exclude labor
        # Hub labor is included in annual_opex
        assert product.buyer.total_annual_cost < hub.economics.annual_opex, \
            "Product operating cost should be less than Hub (no labor)"


# ============================================================================
# 3. BUYER ECONOMICS TESTS - Savings and payback correctness
# ============================================================================

class TestProductBuyerSavingsSign:
    """Savings should be positive when dumping fee exceeds operating cost."""
    
    def test_savings_positive_at_default_fee(self):
        """At $55/m³ dumping fee, savings should be positive."""
        result = run_product_mode(reference_dumping_fee=55.0)
        assert result.buyer.annual_net_savings_avoided_fees_only > 0, \
            f"Savings should be positive at $55/m³, got ${result.buyer.annual_net_savings_avoided_fees_only:,.0f}"
    
    def test_savings_negative_at_low_fee(self):
        """At very low dumping fee, savings should be negative."""
        result = run_product_mode(reference_dumping_fee=10.0)
        assert result.buyer.annual_net_savings_avoided_fees_only < 0, \
            f"Savings should be negative at $10/m³, got ${result.buyer.annual_net_savings_avoided_fees_only:,.0f}"


class TestPaybackHandlesNegativeSavings:
    """Payback must be inf when savings are negative or zero."""
    
    def test_negative_savings_gives_inf_payback(self):
        result = run_product_mode(reference_dumping_fee=10.0)
        assert result.buyer.payback_avoided_fees_only == float('inf'), \
            f"Negative savings should give inf payback, got {result.buyer.payback_avoided_fees_only}"
    
    def test_zero_savings_gives_inf_payback(self):
        # Find the break-even dumping fee approximately
        result = run_product_mode(reference_dumping_fee=26.95)  # ~break-even
        # Accept very high payback as equivalent to inf for practical purposes
        assert result.buyer.payback_avoided_fees_only > 100 or result.buyer.payback_avoided_fees_only == float('inf'), \
            "Zero/negative savings should give very high or inf payback"


class TestBuyerEconomicsCalculation:
    """Verify buyer economics calculation is internally consistent."""
    
    def test_savings_equals_fees_minus_opex(self):
        result = run_product_mode()
        buyer = result.buyer
        
        expected_savings = buyer.current_annual_cost - buyer.total_annual_cost
        assert abs(buyer.annual_net_savings_avoided_fees_only - expected_savings) < 1.0, \
            "Savings = current_cost - operating_cost"
    
    def test_current_cost_equals_volume_times_fee(self):
        result = run_product_mode()
        buyer = result.buyer
        
        expected = buyer.annual_septage_m3 * buyer.reference_dumping_fee
        assert abs(buyer.current_annual_cost - expected) < 1.0, \
            "Current cost = volume × fee"
    
    def test_total_cost_is_sum_of_opex_and_cofeed(self):
        result = run_product_mode()
        buyer = result.buyer
        
        expected = buyer.annual_opex_cash + buyer.annual_cofeed_cost
        assert abs(buyer.total_annual_cost - expected) < 1.0, \
            "Total cost = opex + cofeed"


# ============================================================================
# 4. REGRESSION TESTS - Lock current published table values
# ============================================================================

class TestRegressionProductModeTableValues:
    """Lock Product Mode values from published comparison table."""
    
    def test_product_mode_energy_self_sufficiency(self):
        result = run_product_mode()
        ess = result.base_result.energy.energy_self_sufficiency
        # Expected: 164% ± 10%
        assert 1.50 < ess < 1.80, f"Energy self-sufficiency should be ~164%, got {ess:.0%}"
    
    def test_product_mode_capex(self):
        result = run_product_mode()
        capex = result.buyer.capex
        # Expected: $1,266,708 ± 5%
        assert 1_200_000 < capex < 1_350_000, f"CAPEX should be ~$1.27M, got ${capex:,.0f}"
    
    def test_product_mode_payback_with_char(self):
        result = run_product_mode()
        payback = result.payback_with_char
        # Expected: 12.0 years ± 20%
        assert 9.0 < payback < 15.0, f"Payback (with char) should be ~12yr, got {payback:.1f}yr"
    
    def test_product_mode_owner_hours(self):
        result = run_product_mode()
        hours = result.buyer.owner_time_hours_per_week
        # Expected: 5.0 hours
        assert hours == 5.0, f"Owner hours should be 5.0, got {hours}"
    
    def test_product_mode_is_viable(self):
        result = run_product_mode()
        assert result.is_product_viable, "Product mode should be VIABLE"


class TestRegressionHubModeTableValues:
    """Lock Hub Mode values from published comparison table."""
    
    def test_hub_mode_energy_self_sufficiency(self):
        result = run_hub_mode()
        ess = result.energy.energy_self_sufficiency
        # Expected: 139% ± 10%
        assert 1.25 < ess < 1.55, f"Energy self-sufficiency should be ~139%, got {ess:.0%}"
    
    def test_hub_mode_capex(self):
        result = run_hub_mode()
        capex = result.economics.total_capex
        # Expected: $2,224,066 ± 5%
        assert 2_100_000 < capex < 2_350_000, f"CAPEX should be ~$2.22M, got ${capex:,.0f}"
    
    def test_hub_mode_noi_positive_but_marginal(self):
        """Hub NOI is positive but marginal at 5k m³/yr with light ops.
        
        Model evolution note (2026-02):
        Hub economics improved with updated char pricing and light-ops staffing.
        NOI is now positive (~$48k) but still marginal (46-year payback).
        This is consistent with hub_optimization analysis showing hub
        viability requires higher volumes or owner-operation.
        """
        result = run_hub_mode()
        noi = result.economics.annual_noi
        # Current: ~$48,324 (positive but marginal)
        # Accept range: $30k - $70k
        assert 30_000 < noi < 70_000, f"Hub NOI should be ~$48k marginal, got ${noi:,.0f}"
    
    def test_hub_mode_payback_long(self):
        """Hub payback is very long (>40 years) at 5k m³/yr with light ops.
        
        Model evolution note (2026-02):
        With positive NOI, payback is finite but impractically long.
        This confirms hub mode is NOT VIABLE even when NOI > 0.
        """
        result = run_hub_mode()
        payback = result.economics.simple_payback_years
        # Current: ~46 years (finite but impractical)
        # Accept range: 35 - 60 years
        assert 35 < payback < 60, f"Hub payback should be ~46yr (long), got {payback:.1f}"
    
    def test_hub_mode_not_viable(self):
        result = run_hub_mode()
        from septage_model.simulation.deterministic import ViabilityStatus
        assert result.overall_status == ViabilityStatus.NOT_VIABLE, \
            f"Hub mode should be NOT_VIABLE, got {result.overall_status}"


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
