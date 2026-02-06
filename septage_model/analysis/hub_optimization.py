"""
hub_optimization.py

Exploratory strategic analysis tool.
Not part of core simulation or sensitivity workflows.
Outputs decision artifacts (CSV) only.

Purpose:
    Parametric exploration of hub mode viability across:
    - Catchment radius and aggregation volume
    - Staffing regimes (including $0-labor theoretical bound)
    - Tipping fee market conditions ($35-$75/m³)
    - Co-feed supply strategies

    Answers: "Under what conditions, if any, is hub mode viable?"

Usage:
    python -m septage_model.analysis.hub_optimization
    python -m septage_model.analysis.hub_optimization --out sensitivity/hub_viability_sweep.csv
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, replace, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import argparse

from septage_model.core.parameters import (
    ModelParameters,
    StaffingModel,
    MaintenanceModel,
    EconomicParams,
    create_hub_scenario,
)
from septage_model.simulation.deterministic import run_stage1_option_b


# =============================================================================
# Failure Mode Classification
# =============================================================================

class FailureMode(Enum):
    """Dominant failure mode for hub viability."""
    STRUCTURALLY_VIABLE = "viable"
    LABOR_DOMINATED = "labor_dominated"
    VOLUME_STARVED = "volume_starved"
    ENERGY_DEFICIT = "energy_deficit"
    CAPEX_PROHIBITIVE = "capex_prohibitive"
    THEORETICAL_BOUND_ONLY = "theoretical_bound_only"


# =============================================================================
# Catchment Model
# =============================================================================

@dataclass(frozen=True)
class CatchmentModel:
    """
    Service territory model for hub aggregation economics.
    
    Calculates capturable septage volume based on:
    - Geographic radius and population density
    - Septic system prevalence
    - Hauler capacity constraints
    - Participation/adoption rate (key calibration knob)
    
    Calibration anchors (rural Ontario baseline):
        rural_small:  ~3,000 m³/yr
        rural_medium: ~5,000 m³/yr
        rural_large:  ~8,000 m³/yr
    """
    name: str = "default"
    radius_km: float = 50.0
    population_density_per_km2: float = 10.0  # Rural Ontario: 5-20/km²
    septage_l_per_capita_day: float = 5.0     # Standard assumption
    septic_system_fraction: float = 0.35      # Rural: 30-50% on septic
    
    # Participation rate: fraction of theoretical volume actually captured
    # This is THE calibration knob - encapsulates:
    #   - hauler adoption
    #   - competition from WWTPs
    #   - awareness/marketing
    #   - distance decay effects
    participation_rate: float = 0.10  # Calibrated to hit target volumes
    
    # Hauler constraints (capacity ceiling)
    haulers_in_territory: int = 5
    avg_truck_capacity_m3: float = 12.0
    loads_per_hauler_per_day: float = 2.5
    operating_days_per_year: int = 250
    
    # Calibration metadata
    is_calibrated: bool = True
    calibration_anchor: str = ""  # e.g., "rural_ontario_base_5k"
    is_optimistic_bound: bool = False
    
    def calc_theoretical_volume_m3_yr(self) -> float:
        """Theoretical septage generation in territory (100% capture)."""
        area_km2 = math.pi * self.radius_km ** 2
        population = area_km2 * self.population_density_per_km2
        septic_pop = population * self.septic_system_fraction
        daily_l = septic_pop * self.septage_l_per_capita_day
        return daily_l * 365 / 1000
    
    def calc_capturable_volume_m3_yr(self) -> float:
        """
        Volume hub can realistically capture.
        
        Uses participation_rate as the primary calibration factor,
        with hauler capacity as a hard ceiling.
        """
        theoretical = self.calc_theoretical_volume_m3_yr()
        
        # Apply participation rate (the calibrated knob)
        captured = theoretical * self.participation_rate
        
        # Hauler capacity constraint (hard ceiling)
        hauler_capacity = (
            self.haulers_in_territory *
            self.avg_truck_capacity_m3 *
            self.loads_per_hauler_per_day *
            self.operating_days_per_year
        )
        
        return min(captured, hauler_capacity)
    
    def calc_avg_haul_distance_km(self) -> float:
        """Average haul distance (2/3 of radius)."""
        return self.radius_km * 0.67
    
    def calc_implied_population(self) -> float:
        """Population within catchment radius."""
        area_km2 = math.pi * self.radius_km ** 2
        return area_km2 * self.population_density_per_km2
    
    def calibration_report(self) -> str:
        """Generate calibration diagnostics."""
        area = math.pi * self.radius_km ** 2
        pop = self.calc_implied_population()
        septic_pop = pop * self.septic_system_fraction
        theoretical = self.calc_theoretical_volume_m3_yr()
        captured = self.calc_capturable_volume_m3_yr()
        
        # Sanity checks
        warnings = []
        if pop > 200_000 and "rural" in self.name.lower():
            warnings.append(f"WARNING: {pop:,.0f} people is high for 'rural' scenario")
        if self.participation_rate > 0.50:
            warnings.append(f"WARNING: {self.participation_rate:.0%} participation is optimistic")
        
        lines = [
            f"Catchment: {self.name}",
            f"  Radius: {self.radius_km:.0f} km ({area:,.0f} km²)",
            f"  Population density: {self.population_density_per_km2:.1f}/km²",
            f"  Implied population: {pop:,.0f}",
            f"  Septic users: {septic_pop:,.0f} ({self.septic_system_fraction:.0%})",
            f"  Theoretical volume: {theoretical:,.0f} m³/yr",
            f"  Participation rate: {self.participation_rate:.1%}",
            f"  Captured volume: {captured:,.0f} m³/yr",
            f"  Calibration anchor: {self.calibration_anchor or 'none'}",
            f"  Optimistic bound: {self.is_optimistic_bound}",
        ]
        if warnings:
            lines.extend([""] + warnings)
        
        return "\n".join(lines)
    
    # =========================================================================
    # CALIBRATED FACTORY METHODS (rural Ontario baseline)
    # =========================================================================
    
    @classmethod
    def rural_small(cls) -> CatchmentModel:
        """
        Small rural catchment: ~3,000 m³/yr.
        
        Calibrated to rural Ontario conditions:
        - 35 km radius, low density (8/km²)
        - 15% participation (realistic adoption)
        """
        return cls(
            name="rural_small",
            radius_km=35.0,
            population_density_per_km2=8.0,
            septic_system_fraction=0.35,
            participation_rate=0.153,  # Calibrated: 3,000 / 19,666 theoretical
            haulers_in_territory=3,
            is_calibrated=True,
            calibration_anchor="rural_ontario_low_3k",
        )
    
    @classmethod
    def rural_medium(cls) -> CatchmentModel:
        """
        Medium rural catchment: ~5,000 m³/yr.
        
        Baseline scenario for hub analysis.
        - 50 km radius, moderate density (10/km²)
        - 10% participation
        """
        return cls(
            name="rural_medium",
            radius_km=50.0,
            population_density_per_km2=10.0,
            septic_system_fraction=0.35,
            participation_rate=0.100,  # Calibrated: 5,000 / 50,167 theoretical
            haulers_in_territory=5,
            is_calibrated=True,
            calibration_anchor="rural_ontario_base_5k",
        )
    
    @classmethod
    def rural_large(cls) -> CatchmentModel:
        """
        Large rural catchment: ~8,000 m³/yr.
        
        Aggressive aggregation within realistic bounds.
        - 60 km radius, moderate density (12/km²)
        - 9% participation
        """
        return cls(
            name="rural_large",
            radius_km=60.0,
            population_density_per_km2=12.0,
            septic_system_fraction=0.35,
            participation_rate=0.092,  # Calibrated: 8,000 / 86,689 theoretical
            haulers_in_territory=6,
            is_calibrated=True,
            calibration_anchor="rural_ontario_high_8k",
        )
    
    @classmethod
    def suburban_fringe(cls) -> CatchmentModel:
        """
        Suburban fringe: ~12,000 m³/yr.
        
        Higher density area on municipal boundary.
        - 40 km radius, higher density (35/km²)
        - 15% participation (more haulers, bigger market)
        """
        return cls(
            name="suburban_fringe",
            radius_km=40.0,
            population_density_per_km2=35.0,
            septic_system_fraction=0.25,  # Lower - more sewered
            participation_rate=0.150,  # Calibrated: 12,000 / 80,268 theoretical
            haulers_in_territory=10,
            is_calibrated=True,
            calibration_anchor="suburban_fringe_12k",
        )
    
    # =========================================================================
    # OPTIMISTIC BOUND FACTORY METHODS (upper bound only)
    # =========================================================================
    
    @classmethod
    def optimistic_rural_medium(cls) -> CatchmentModel:
        """
        OPTIMISTIC BOUND: High-capture rural scenario.
        
        NOT for baseline viability claims.
        Use as upper bound only, like $0 labor.
        
        Assumes:
        - 25% participation (dominant market position)
        - Aggressive hauler outreach
        - Weak WWTP competition
        """
        return cls(
            name="optimistic_rural_medium",
            radius_km=50.0,
            population_density_per_km2=15.0,
            septic_system_fraction=0.40,
            participation_rate=0.25,  # OPTIMISTIC
            haulers_in_territory=8,
            is_calibrated=False,
            calibration_anchor="OPTIMISTIC_BOUND",
            is_optimistic_bound=True,
        )
    
    @classmethod
    def optimistic_rural_large(cls) -> CatchmentModel:
        """
        OPTIMISTIC BOUND: Maximum realistic aggregation.
        
        NOT for baseline viability claims.
        Represents theoretical ceiling for rural hub.
        """
        return cls(
            name="optimistic_rural_large",
            radius_km=75.0,
            population_density_per_km2=18.0,
            septic_system_fraction=0.40,
            participation_rate=0.30,  # VERY OPTIMISTIC
            haulers_in_territory=10,
            is_calibrated=False,
            calibration_anchor="OPTIMISTIC_BOUND",
            is_optimistic_bound=True,
        )


# =============================================================================
# Staffing Scenarios
# =============================================================================

@dataclass(frozen=True)
class HubStaffingScenario:
    """
    Pre-defined staffing scenario for hub optimization.
    
    Wraps StaffingModel with metadata for optimization sweeps.
    """
    name: str
    staffing: StaffingModel
    is_theoretical_bound: bool = False
    description: str = ""
    
    def annual_labor_cost(self) -> float:
        """Total annual labor cost for this scenario."""
        return self.staffing.annual_cash_labor_cost()
    
    @classmethod
    def owner_operated_baseline(cls) -> HubStaffingScenario:
        """
        THEORETICAL BOUND: $0 paid labor.
        
        Answers: "If labor were free, would the hub still fail?"
        Must be excluded from viability claims.
        """
        return cls(
            name="OWNER_OPERATED_BASELINE",
            staffing=StaffingModel.owner_op(owner_hours=0.0),
            is_theoretical_bound=True,
            description="Theoretical upper bound - $0 labor assumption"
        )
    
    @classmethod
    def owner_operated_realistic(cls) -> HubStaffingScenario:
        """Owner-operated with realistic 10 hrs/wk commitment."""
        return cls(
            name="owner_operated_realistic",
            staffing=StaffingModel.owner_op(owner_hours=10.0),
            is_theoretical_bound=False,
            description="Owner commits 10 hrs/wk unpaid"
        )
    
    @classmethod
    def remote_monitored(cls) -> HubStaffingScenario:
        """Remote monitoring with on-call technician."""
        # Custom staffing: 8 hrs/wk paid + on-call allowance
        staffing = StaffingModel(
            mode="remote_monitored",
            paid_hours_per_week=8.0,
            base_wage_per_hr=40.0,
            burden_multiplier=1.35,
            on_call_allowance_weekly=320.0,  # ~$8/hr on-call for 40 hrs
            expected_callouts_per_week=1.5,
            callout_hours_per_event=3.0,
            owner_time_hours_per_week=2.0,
        )
        return cls(
            name="remote_monitored",
            staffing=staffing,
            description="Remote monitoring + on-call response"
        )
    
    @classmethod
    def shared_operator(cls) -> HubStaffingScenario:
        """Shared operator across multiple facilities (50% allocation)."""
        base = StaffingModel.hub_light_ops()
        # Halve the effective hours for shared model
        staffing = replace(base, 
                          mode="shared_operator",
                          paid_hours_per_week=base.paid_hours_per_week * 0.5)
        return cls(
            name="shared_operator",
            staffing=staffing,
            description="Operator shared across 2 facilities"
        )
    
    @classmethod
    def light_ops(cls) -> HubStaffingScenario:
        """Standard light operations (40 hr/wk + on-call)."""
        return cls(
            name="light_ops",
            staffing=StaffingModel.hub_light_ops(),
            description="40 hr/wk + on-call coverage"
        )
    
    @classmethod
    def fully_staffed(cls) -> HubStaffingScenario:
        """Full staffing (112 hr/wk coverage)."""
        return cls(
            name="fully_staffed",
            staffing=StaffingModel.hub_staffed(),
            description="Full 7-day coverage"
        )


# =============================================================================
# Co-feed Supply Scenarios
# =============================================================================

@dataclass(frozen=True)
class CofeedScenario:
    """
    Co-feed supply strategy scenario.
    
    Models procurement cost, reliability, and risk-adjusted economics.
    """
    name: str
    base_cost_per_tds: float
    transport_km: float
    transport_cost_per_tds_km: float
    supply_reliability: float  # 0-1, probability of full supply
    seasonal_variation_factor: float  # >1 means higher winter costs
    enabled: bool = True
    
    def delivered_cost_per_tds(self) -> float:
        """Total delivered cost per tonne dry solids."""
        if not self.enabled:
            return 0.0
        return self.base_cost_per_tds + self.transport_km * self.transport_cost_per_tds_km
    
    def risk_adjusted_cost_per_tds(self) -> float:
        """Cost adjusted for supply reliability risk."""
        if not self.enabled:
            return 0.0
        # Unreliable supply requires backup at premium
        reliability_penalty = 1.0 + (1.0 - self.supply_reliability) * 0.30
        return self.delivered_cost_per_tds() * reliability_penalty
    
    @classmethod
    def contracted_wood(cls) -> CofeedScenario:
        """Long-term contract with sawmill/forestry operation."""
        return cls(name="contracted_wood", base_cost_per_tds=75.0,
                   transport_km=30.0, transport_cost_per_tds_km=0.12,
                   supply_reliability=0.95, seasonal_variation_factor=1.1)
    
    @classmethod
    def spot_wood(cls) -> CofeedScenario:
        """Spot market wood waste procurement."""
        return cls(name="spot_wood", base_cost_per_tds=50.0,
                   transport_km=45.0, transport_cost_per_tds_km=0.15,
                   supply_reliability=0.70, seasonal_variation_factor=1.4)
    
    @classmethod
    def ag_residue(cls) -> CofeedScenario:
        """Agricultural residue (seasonal, low cost, high risk)."""
        return cls(name="ag_residue", base_cost_per_tds=30.0,
                   transport_km=25.0, transport_cost_per_tds_km=0.10,
                   supply_reliability=0.60, seasonal_variation_factor=2.0)
    
    @classmethod
    def no_cofeed(cls) -> CofeedScenario:
        """Septage-only operation (no co-feed)."""
        return cls(name="no_cofeed", base_cost_per_tds=0.0,
                   transport_km=0.0, transport_cost_per_tds_km=0.0,
                   supply_reliability=1.0, seasonal_variation_factor=1.0,
                   enabled=False)


# =============================================================================
# Hub Viability Result
# =============================================================================

@dataclass
class HubViabilityResult:
    """Single scenario result from hub optimization sweep."""
    # Scenario identifiers
    catchment_name: str
    catchment_radius_km: float
    population_density: float
    staffing_regime: str
    cofeed_strategy: str
    tipping_fee: float
    
    # Volume and throughput
    annual_volume_m3: float
    annual_cofeed_tds: float
    
    # Economics
    annual_revenue: float
    annual_opex: float
    labor_cost: float
    noi: float
    capex: float
    payback_years: float
    
    # Feasibility
    energy_self_sufficient: bool
    viable: bool
    is_theoretical_bound: bool
    
    # Classification
    dominant_failure_mode: FailureMode
    binding_constraint: str
    
    def to_csv_row(self) -> Dict[str, Any]:
        """Convert to CSV row dictionary."""
        return {
            'catchment_name': self.catchment_name,
            'catchment_radius_km': self.catchment_radius_km,
            'population_density': self.population_density,
            'tipping_fee': self.tipping_fee,
            'staffing_regime': self.staffing_regime,
            'cofeed_strategy': self.cofeed_strategy,
            'annual_volume_m3': self.annual_volume_m3,
            'annual_cofeed_tds': self.annual_cofeed_tds,
            'annual_opex': self.annual_opex,
            'annual_revenue': self.annual_revenue,
            'labor_cost': self.labor_cost,
            'noi': self.noi,
            'capex': self.capex,
            'payback_years': self.payback_years if self.payback_years != float('inf') else 'inf',
            'energy_self_sufficient': self.energy_self_sufficient,
            'viable': self.viable,
            'is_theoretical_bound': self.is_theoretical_bound,
            'dominant_failure_mode': self.dominant_failure_mode.value,
            'binding_constraint': self.binding_constraint,
        }


# =============================================================================
# Hub Viability Analysis (Aggregate Result)
# =============================================================================

@dataclass
class HubViabilityAnalysis:
    """Complete hub optimization sweep result."""
    results: List[HubViabilityResult]
    viable_scenarios: List[HubViabilityResult]
    theoretical_bounds: List[HubViabilityResult]
    best_scenario: Optional[HubViabilityResult]
    
    # Breakeven analysis
    min_viable_volume_m3: Optional[float]
    min_viable_tipping_fee: Optional[float]
    max_viable_labor_cost: Optional[float]
    
    # Failure mode distribution
    failure_mode_counts: Dict[FailureMode, int]
    
    def summary(self) -> str:
        """Generate text summary of hub viability analysis."""
        lines = [
            "=" * 70,
            "HUB VIABILITY ANALYSIS",
            "=" * 70,
            "",
            f"Total scenarios evaluated: {len(self.results)}",
            f"  Theoretical bounds: {len(self.theoretical_bounds)}",
            f"  Realistic scenarios: {len(self.results) - len(self.theoretical_bounds)}",
            f"  Viable (realistic): {len(self.viable_scenarios)}",
            "",
        ]
        
        # Failure mode breakdown
        lines.append("FAILURE MODE DISTRIBUTION:")
        for mode, count in sorted(self.failure_mode_counts.items(), 
                                  key=lambda x: -x[1]):
            pct = 100 * count / len(self.results) if self.results else 0
            lines.append(f"  {mode.value:25s}: {count:4d} ({pct:5.1f}%)")
        lines.append("")
        
        # Theoretical bound analysis
        bound_viable = [r for r in self.theoretical_bounds if r.noi > 0]
        if bound_viable:
            best_bound = max(bound_viable, key=lambda r: r.noi)
            lines.extend([
                "THEORETICAL UPPER BOUND ($0 labor):",
                f"  Best NOI at $0 labor: ${best_bound.noi:,.0f}",
                f"  Payback at $0 labor: {best_bound.payback_years:.1f} years",
                f"  Scenario: {best_bound.catchment_name} / {best_bound.cofeed_strategy}",
                "",
            ])
            
            if not self.viable_scenarios:
                lines.append("  ⚠ Hub fails even with zero labor — STRUCTURAL failure")
                lines.append("")
        else:
            lines.extend([
                "THEORETICAL UPPER BOUND ($0 labor):",
                "  ⚠ Hub fails even with zero labor — STRUCTURAL failure",
                "  No staffing optimization can rescue hub mode.",
                "",
            ])
        
        # Best viable scenario
        if self.best_scenario:
            b = self.best_scenario
            lines.extend([
                "BEST VIABLE SCENARIO:",
                f"  Catchment: {b.catchment_name} ({b.catchment_radius_km:.0f} km radius)",
                f"  Staffing: {b.staffing_regime}",
                f"  Co-feed: {b.cofeed_strategy}",
                f"  Tipping fee: ${b.tipping_fee:.0f}/m³",
                f"  Volume: {b.annual_volume_m3:,.0f} m³/yr",
                f"  Revenue: ${b.annual_revenue:,.0f}",
                f"  OPEX: ${b.annual_opex:,.0f}",
                f"  NOI: ${b.noi:,.0f}",
                f"  Payback: {b.payback_years:.1f} years",
                "",
            ])
        else:
            lines.extend([
                "NO VIABLE SCENARIOS FOUND",
                "",
                "Hub mode is not viable under any tested configuration.",
                "",
            ])
        
        # Breakeven thresholds
        lines.append("BREAKEVEN THRESHOLDS:")
        if self.min_viable_volume_m3:
            lines.append(f"  Minimum volume for viability: {self.min_viable_volume_m3:,.0f} m³/yr")
        else:
            lines.append("  Minimum volume for viability: NOT ACHIEVABLE")
        
        if self.min_viable_tipping_fee:
            lines.append(f"  Minimum tipping fee: ${self.min_viable_tipping_fee:.0f}/m³")
        else:
            lines.append("  Minimum tipping fee: NOT ACHIEVABLE (>$75/m³)")
        
        if self.max_viable_labor_cost:
            lines.append(f"  Maximum labor cost: ${self.max_viable_labor_cost:,.0f}/yr")
        else:
            lines.append("  Maximum labor cost: $0 (only theoretical bound viable)")
        
        lines.append("")
        lines.append("=" * 70)
        
        return "\n".join(lines)


# =============================================================================
# Failure Mode Classification
# =============================================================================

def classify_failure_mode(
    result: HubViabilityResult,
    labor_fraction_threshold: float = 0.50,
    volume_threshold_m3: float = 3000.0,
) -> Tuple[FailureMode, str]:
    """
    Classify the dominant failure mode for a hub scenario.
    
    Returns:
        (FailureMode, binding_constraint_description)
    """
    if result.is_theoretical_bound:
        if result.viable or result.noi > 0:
            return FailureMode.THEORETICAL_BOUND_ONLY, "Viable only at $0 labor"
        else:
            return FailureMode.CAPEX_PROHIBITIVE, "Fails even at $0 labor - structural"
    
    if result.viable:
        return FailureMode.STRUCTURALLY_VIABLE, "None"
    
    # Check energy first
    if not result.energy_self_sufficient:
        return FailureMode.ENERGY_DEFICIT, "Insufficient syngas for thermal demand"
    
    # Check volume
    if result.annual_volume_m3 < volume_threshold_m3:
        return FailureMode.VOLUME_STARVED, f"Volume {result.annual_volume_m3:.0f} < {volume_threshold_m3:.0f} m³/yr"
    
    # Check labor dominance
    if result.annual_opex > 0:
        labor_fraction = result.labor_cost / result.annual_opex
        if labor_fraction > labor_fraction_threshold:
            return FailureMode.LABOR_DOMINATED, f"Labor is {labor_fraction:.0%} of OPEX"
    
    # Default to CAPEX
    return FailureMode.CAPEX_PROHIBITIVE, f"Payback {result.payback_years:.1f} yr exceeds threshold"


# =============================================================================
# Core Optimization Sweep
# =============================================================================

def evaluate_single_scenario(
    catchment: CatchmentModel,
    staffing: HubStaffingScenario,
    cofeed: CofeedScenario,
    tipping_fee: float,
    max_payback_years: float = 20.0,
) -> HubViabilityResult:
    """
    Evaluate hub viability for a single scenario combination.
    
    Uses the existing simulation engine (run_hub_option_b_stage1).
    """
    # Calculate volumes
    septage_m3 = catchment.calc_capturable_volume_m3_yr()
    
    # Co-feed sizing: 1:1 ratio with septage dry solids
    ts_fraction = 0.03
    density = 1000.0
    septage_tds = septage_m3 * density * ts_fraction / 1000
    cofeed_tds = septage_tds if cofeed.enabled else 0.0
    
    # Create hub scenario with these parameters
    params = create_hub_scenario(
        annual_septage_m3=septage_m3,
        annual_cofeed_tds=cofeed_tds,
    )
    
    # Override staffing
    params = replace(params, staffing=staffing.staffing)
    
    # Override tipping fee
    new_economic = replace(params.economic, tipping_fee_per_m3=tipping_fee)
    params = replace(params, economic=new_economic)
    
    # Run simulation
    sim_result = run_stage1_option_b(params)
    
    # Extract economics
    labor_cost = staffing.annual_labor_cost()
    annual_revenue = sim_result.economics.annual_revenue
    annual_opex = sim_result.economics.annual_opex
    noi = sim_result.economics.annual_noi
    capex = sim_result.economics.total_capex
    payback = sim_result.economics.simple_payback_years
    
    # Energy self-sufficiency
    energy_ok = sim_result.energy.energy_self_sufficiency >= 1.0
    
    # Viability check (exclude theoretical bounds from "viable" status)
    viable = (
        payback <= max_payback_years and 
        noi > 0 and 
        not staffing.is_theoretical_bound
    )
    
    # Build result
    result = HubViabilityResult(
        catchment_name=catchment.name,
        catchment_radius_km=catchment.radius_km,
        population_density=catchment.population_density_per_km2,
        staffing_regime=staffing.name,
        cofeed_strategy=cofeed.name,
        tipping_fee=tipping_fee,
        annual_volume_m3=septage_m3,
        annual_cofeed_tds=cofeed_tds,
        annual_revenue=annual_revenue,
        annual_opex=annual_opex,
        labor_cost=labor_cost,
        noi=noi,
        capex=capex,
        payback_years=payback,
        energy_self_sufficient=energy_ok,
        viable=viable,
        is_theoretical_bound=staffing.is_theoretical_bound,
        dominant_failure_mode=FailureMode.STRUCTURALLY_VIABLE,  # Placeholder
        binding_constraint="",
    )
    
    # Classify failure mode
    failure_mode, constraint = classify_failure_mode(result)
    result = replace(result, 
                     dominant_failure_mode=failure_mode,
                     binding_constraint=constraint)
    
    return result


def run_hub_optimization(
    catchments: Optional[List[CatchmentModel]] = None,
    staffing_scenarios: Optional[List[HubStaffingScenario]] = None,
    cofeed_scenarios: Optional[List[CofeedScenario]] = None,
    tipping_fees: Optional[List[float]] = None,
    max_payback_years: float = 20.0,
    include_theoretical_bound: bool = True,
) -> HubViabilityAnalysis:
    """
    Run parametric hub optimization sweep.
    
    Args:
        catchments: Territory models to evaluate
        staffing_scenarios: Staffing regimes to test
        cofeed_scenarios: Co-feed strategies to test
        tipping_fees: Tipping fee values ($35-$75/m³ recommended)
        max_payback_years: Viability threshold
        include_theoretical_bound: Include $0 labor baseline
    
    Returns:
        HubViabilityAnalysis with complete results and summary
    """
    # Default catchments
    if catchments is None:
        catchments = [
            CatchmentModel.rural_small(),
            CatchmentModel.rural_medium(),
            CatchmentModel.rural_large(),
            CatchmentModel.suburban_fringe(),
        ]
    
    # Default staffing scenarios
    if staffing_scenarios is None:
        staffing_scenarios = [
            HubStaffingScenario.owner_operated_realistic(),
            HubStaffingScenario.remote_monitored(),
            HubStaffingScenario.shared_operator(),
            HubStaffingScenario.light_ops(),
        ]
        if include_theoretical_bound:
            staffing_scenarios.insert(0, HubStaffingScenario.owner_operated_baseline())
    
    # Default co-feed scenarios
    if cofeed_scenarios is None:
        cofeed_scenarios = [
            CofeedScenario.contracted_wood(),
            CofeedScenario.spot_wood(),
            CofeedScenario.no_cofeed(),
        ]
    
    # Default tipping fee sweep: $35-$75/m³ in $2.50 increments
    if tipping_fees is None:
        tipping_fees = [35.0 + i * 2.5 for i in range(17)]  # 35, 37.5, ..., 75
    
    # Run sweep
    all_results: List[HubViabilityResult] = []
    
    total = len(catchments) * len(staffing_scenarios) * len(cofeed_scenarios) * len(tipping_fees)
    print(f"Running hub optimization sweep: {total} scenarios...")
    
    for catchment in catchments:
        for staffing in staffing_scenarios:
            for cofeed in cofeed_scenarios:
                for tipping_fee in tipping_fees:
                    result = evaluate_single_scenario(
                        catchment=catchment,
                        staffing=staffing,
                        cofeed=cofeed,
                        tipping_fee=tipping_fee,
                        max_payback_years=max_payback_years,
                    )
                    all_results.append(result)
    
    print(f"Completed {len(all_results)} scenarios.")
    
    # Separate theoretical bounds
    theoretical_bounds = [r for r in all_results if r.is_theoretical_bound]
    realistic_results = [r for r in all_results if not r.is_theoretical_bound]
    
    # Filter viable (realistic only)
    viable = [r for r in realistic_results if r.viable]
    
    # Find best (shortest payback among viable)
    best = min(viable, key=lambda r: r.payback_years) if viable else None
    
    # Breakeven analysis
    min_volume = min((r.annual_volume_m3 for r in viable), default=None)
    min_tipping = min((r.tipping_fee for r in viable), default=None)
    max_labor = max((r.labor_cost for r in viable), default=None)
    
    # Failure mode distribution
    failure_counts: Dict[FailureMode, int] = {}
    for r in all_results:
        failure_counts[r.dominant_failure_mode] = failure_counts.get(r.dominant_failure_mode, 0) + 1
    
    return HubViabilityAnalysis(
        results=all_results,
        viable_scenarios=viable,
        theoretical_bounds=theoretical_bounds,
        best_scenario=best,
        min_viable_volume_m3=min_volume,
        min_viable_tipping_fee=min_tipping,
        max_viable_labor_cost=max_labor,
        failure_mode_counts=failure_counts,
    )


# =============================================================================
# CSV Export
# =============================================================================

CSV_COLUMNS = [
    'catchment_name',
    'catchment_radius_km',
    'population_density',
    'tipping_fee',
    'staffing_regime',
    'cofeed_strategy',
    'annual_volume_m3',
    'annual_cofeed_tds',
    'annual_opex',
    'annual_revenue',
    'labor_cost',
    'noi',
    'capex',
    'payback_years',
    'energy_self_sufficient',
    'viable',
    'is_theoretical_bound',
    'dominant_failure_mode',
    'binding_constraint',
]


def export_to_csv(analysis: HubViabilityAnalysis, filepath: Path) -> None:
    """
    Export hub optimization results to CSV.
    
    Args:
        analysis: Complete analysis result
        filepath: Output CSV path
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    with open(filepath, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        
        for result in analysis.results:
            writer.writerow(result.to_csv_row())
    
    print(f"Exported {len(analysis.results)} rows to {filepath}")


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Hub mode viability optimization sweep",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m septage_model.analysis.hub_optimization
  python -m septage_model.analysis.hub_optimization --out results.csv
  python -m septage_model.analysis.hub_optimization --max-payback 15
        """
    )
    parser.add_argument(
        '--out', '-o',
        type=Path,
        default=Path('sensitivity/hub_viability_sweep.csv'),
        help='Output CSV path (default: sensitivity/hub_viability_sweep.csv)'
    )
    parser.add_argument(
        '--max-payback',
        type=float,
        default=20.0,
        help='Maximum payback years for viability (default: 20)'
    )
    parser.add_argument(
        '--no-theoretical-bound',
        action='store_true',
        help='Skip $0 labor theoretical bound scenarios'
    )
    parser.add_argument(
        '--summary-only',
        action='store_true',
        help='Print summary only, skip CSV export'
    )
    
    args = parser.parse_args()
    
    # Run optimization
    analysis = run_hub_optimization(
        max_payback_years=args.max_payback,
        include_theoretical_bound=not args.no_theoretical_bound,
    )
    
    # Print summary
    print()
    print(analysis.summary())
    
    # Export CSV
    if not args.summary_only:
        export_to_csv(analysis, args.out)


if __name__ == "__main__":
    main()
