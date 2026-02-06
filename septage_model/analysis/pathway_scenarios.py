"""
Pathway Scenarios Module - Value-Add Scenario Configuration and Analysis.

This module provides scenario infrastructure for comparing disposal-only
baseline economics against value-add pathway configurations.

Scenario Types:
    - BASELINE: Disposal-only, no value-add pathways
    - CONSERVATIVE: Near-term pathways only (low risk)
    - MODERATE: Near-term + mid-term pathways
    - OPTIMISTIC: All pathways including speculative
    - Custom: User-defined pathway combinations

Integration:
    - Works with StreamPathwayConfig from stream_pathways.py
    - Uses balance functions from balances.py for revenue calculations
    - Integrates with sensitivity.py sweep infrastructure
"""

from dataclasses import dataclass, replace, field
from typing import List, Optional, Tuple, Dict, Any, Callable
from enum import Enum
import csv
import io

from septage_model.core.stream_pathways import (
    PathwayMaturity,
    ScenarioRisk,
    PathwayTier,
    pathway_allowed,
    StreamPathwayConfig,
    CentratePathway,
    CharPathway,
    SyngasPathway,
    ScreeningsPathway,
    OffSpecPathway,
    StruvitePathwayParams,
    AmmoniaStrippingParams,
    NutrientConcentrateParams,
    CHPParams,
    HeatExportParams,
    CharActivationParams,
    SepticMediaParams,
    ScreeningsReuseParams,
    OffSpecThermalParams,
    CircularLoopParams,
    MetaProductParams,
    BASELINE_PATHWAYS,
    CONSERVATIVE_PATHWAYS,
    MODERATE_PATHWAYS,
    FULL_CIRCULAR_PATHWAYS,
)

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


# =============================================================================
# Scenario Definitions
# =============================================================================

class ScenarioType(Enum):
    """Pre-defined scenario types."""
    BASELINE = "baseline"
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    OPTIMISTIC = "optimistic"
    NUTRIENT_RECOVERY = "nutrient_recovery"
    ENERGY_EXPORT = "energy_export"
    CHAR_UPGRADE = "char_upgrade"
    FULL_CIRCULAR = "full_circular"
    CUSTOM = "custom"


@dataclass(frozen=True)
class ValueAddScenario:
    """Complete scenario definition for pathway analysis."""
    name: str
    scenario_type: ScenarioType
    risk_level: ScenarioRisk
    description: str
    
    # Pathway configuration
    pathways: StreamPathwayConfig
    
    # Scenario-level flags (convenience for quick enable/disable)
    enable_struvite: bool = False
    enable_ammonia_stripping: bool = False
    enable_chp: bool = False
    enable_heat_export: bool = False
    enable_char_activation: bool = False
    enable_carbon_credits: bool = False
    enable_circular_loop: bool = False
    
    # Economic assumptions
    discount_rate: float = 0.08          # NPV discount rate
    analysis_years: int = 15             # Project lifetime
    
    def total_capex(self) -> float:
        """Sum of CAPEX for all enabled pathways."""
        return self.pathways.total_pathway_capex(self.risk_level)
    
    def total_annual_opex(self) -> float:
        """Sum of annual OPEX for all enabled pathways."""
        return self.pathways.total_pathway_opex(self.risk_level)


# =============================================================================
# Pre-defined Scenarios
# =============================================================================

SCENARIO_BASELINE = ValueAddScenario(
    name="Baseline (Disposal Only)",
    scenario_type=ScenarioType.BASELINE,
    risk_level=ScenarioRisk.CONSERVATIVE,
    description="No value-add pathways; disposal-only economics",
    pathways=BASELINE_PATHWAYS,
)

SCENARIO_CONSERVATIVE = ValueAddScenario(
    name="Conservative Value-Add",
    scenario_type=ScenarioType.CONSERVATIVE,
    risk_level=ScenarioRisk.CONSERVATIVE,
    description="Near-term proven pathways only",
    pathways=CONSERVATIVE_PATHWAYS,
    enable_struvite=True,
    enable_heat_export=True,
)

SCENARIO_NUTRIENT_RECOVERY = ValueAddScenario(
    name="Nutrient Recovery Focus",
    scenario_type=ScenarioType.NUTRIENT_RECOVERY,
    risk_level=ScenarioRisk.CONSERVATIVE,
    description="Focus on struvite and ammonia recovery from centrate",
    pathways=StreamPathwayConfig(
        struvite=StruvitePathwayParams(enabled=True),
        ammonia_stripping=AmmoniaStrippingParams(enabled=True),
    ),
    enable_struvite=True,
    enable_ammonia_stripping=True,
)

SCENARIO_ENERGY_EXPORT = ValueAddScenario(
    name="Energy Export Focus",
    scenario_type=ScenarioType.ENERGY_EXPORT,
    risk_level=ScenarioRisk.CONSERVATIVE,
    description="CHP and heat export from excess syngas",
    pathways=StreamPathwayConfig(
        chp=CHPParams(enabled=True, grid_export_enabled=True),
        heat_export=HeatExportParams(enabled=True),
    ),
    enable_chp=True,
    enable_heat_export=True,
)

SCENARIO_CHAR_UPGRADE = ValueAddScenario(
    name="Char Upgrade Focus",
    scenario_type=ScenarioType.CHAR_UPGRADE,
    risk_level=ScenarioRisk.MODERATE,
    description="Char activation and premium market pathways",
    pathways=StreamPathwayConfig(
        char_activation=CharActivationParams(enabled=True),
        septic_media=SepticMediaParams(enabled=True),
    ),
    enable_char_activation=True,
)

SCENARIO_MODERATE = ValueAddScenario(
    name="Moderate Value-Add",
    scenario_type=ScenarioType.MODERATE,
    risk_level=ScenarioRisk.MODERATE,
    description="Near-term + mid-term pathways",
    pathways=MODERATE_PATHWAYS,
    enable_struvite=True,
    enable_ammonia_stripping=True,
    enable_chp=True,
    enable_heat_export=True,
    enable_char_activation=True,
)

SCENARIO_FULL_CIRCULAR = ValueAddScenario(
    name="Full Circular Economy",
    scenario_type=ScenarioType.FULL_CIRCULAR,
    risk_level=ScenarioRisk.OPTIMISTIC,
    description="All pathways including speculative circular loops",
    pathways=FULL_CIRCULAR_PATHWAYS,
    enable_struvite=True,
    enable_ammonia_stripping=True,
    enable_chp=True,
    enable_heat_export=True,
    enable_char_activation=True,
    enable_carbon_credits=True,
    enable_circular_loop=True,
)

# Lookup for easy access
PREDEFINED_SCENARIOS = {
    ScenarioType.BASELINE: SCENARIO_BASELINE,
    ScenarioType.CONSERVATIVE: SCENARIO_CONSERVATIVE,
    ScenarioType.NUTRIENT_RECOVERY: SCENARIO_NUTRIENT_RECOVERY,
    ScenarioType.ENERGY_EXPORT: SCENARIO_ENERGY_EXPORT,
    ScenarioType.CHAR_UPGRADE: SCENARIO_CHAR_UPGRADE,
    ScenarioType.MODERATE: SCENARIO_MODERATE,
    ScenarioType.FULL_CIRCULAR: SCENARIO_FULL_CIRCULAR,
}


# =============================================================================
# Scenario Results
# =============================================================================

@dataclass
class PathwayRevenueBreakdown:
    """Revenue breakdown by pathway."""
    struvite_revenue: float = 0.0
    ammonia_revenue: float = 0.0
    chp_grid_revenue: float = 0.0
    heat_export_revenue: float = 0.0
    char_activation_premium: float = 0.0
    screenings_reuse_credit: float = 0.0
    carbon_credit_revenue: float = 0.0
    avoided_disposal_savings: float = 0.0
    
    @property
    def total_value_add_revenue(self) -> float:
        """Total additional revenue from value-add pathways."""
        return (
            self.struvite_revenue +
            self.ammonia_revenue +
            self.chp_grid_revenue +
            self.heat_export_revenue +
            self.char_activation_premium +
            self.screenings_reuse_credit +
            self.carbon_credit_revenue +
            self.avoided_disposal_savings
        )


@dataclass
class ScenarioResult:
    """Complete result from scenario analysis."""
    scenario: ValueAddScenario
    
    # Baseline economics (from core model)
    baseline_revenue_annual: float
    baseline_opex_annual: float
    baseline_capex: float
    
    # Pathway economics
    pathway_capex: float
    pathway_opex_annual: float
    pathway_revenue: PathwayRevenueBreakdown
    
    # Net economics
    @property
    def total_capex(self) -> float:
        return self.baseline_capex + self.pathway_capex
    
    @property
    def total_revenue_annual(self) -> float:
        return self.baseline_revenue_annual + self.pathway_revenue.total_value_add_revenue
    
    @property
    def total_opex_annual(self) -> float:
        return self.baseline_opex_annual + self.pathway_opex_annual
    
    @property
    def net_annual(self) -> float:
        return self.total_revenue_annual - self.total_opex_annual
    
    @property
    def revenue_delta(self) -> float:
        """Additional revenue vs baseline (pathway revenue minus pathway opex)."""
        return self.pathway_revenue.total_value_add_revenue - self.pathway_opex_annual
    
    @property
    def simple_payback_years(self) -> float:
        """Simple payback for pathway investment."""
        if self.revenue_delta <= 0:
            return float('inf')
        return self.pathway_capex / self.revenue_delta
    
    def npv(self, discount_rate: float = 0.08, years: int = 15) -> float:
        """Calculate NPV of scenario vs baseline."""
        annual_delta = self.revenue_delta
        
        # NPV = -CAPEX + sum(annual_delta / (1+r)^t)
        pv_cash_flows = sum(
            annual_delta / ((1 + discount_rate) ** t)
            for t in range(1, years + 1)
        )
        
        return -self.pathway_capex + pv_cash_flows

    def to_dict(self, discount_rate: float = 0.08, years: int = 15) -> Dict[str, Any]:
        """Export scenario result as a flat dictionary for CSV/table output.

        Args:
            discount_rate: Discount rate for NPV calculation.
            years: Analysis horizon for NPV calculation.

        Returns:
            Dictionary with all key economic metrics.
        """
        rev = self.pathway_revenue
        return {
            "scenario": self.scenario.name,
            "scenario_type": self.scenario.scenario_type.value,
            "risk_level": self.scenario.risk_level.value,
            "baseline_revenue_annual": round(self.baseline_revenue_annual, 2),
            "baseline_opex_annual": round(self.baseline_opex_annual, 2),
            "baseline_capex": round(self.baseline_capex, 2),
            "pathway_capex": round(self.pathway_capex, 2),
            "pathway_opex_annual": round(self.pathway_opex_annual, 2),
            "struvite_revenue": round(rev.struvite_revenue, 2),
            "ammonia_revenue": round(rev.ammonia_revenue, 2),
            "chp_grid_revenue": round(rev.chp_grid_revenue, 2),
            "heat_export_revenue": round(rev.heat_export_revenue, 2),
            "char_activation_premium": round(rev.char_activation_premium, 2),
            "screenings_reuse_credit": round(rev.screenings_reuse_credit, 2),
            "carbon_credit_revenue": round(rev.carbon_credit_revenue, 2),
            "avoided_disposal_savings": round(rev.avoided_disposal_savings, 2),
            "total_value_add_revenue": round(rev.total_value_add_revenue, 2),
            "total_capex": round(self.total_capex, 2),
            "total_revenue_annual": round(self.total_revenue_annual, 2),
            "total_opex_annual": round(self.total_opex_annual, 2),
            "net_annual": round(self.net_annual, 2),
            "revenue_delta": round(self.revenue_delta, 2),
            "simple_payback_years": round(self.simple_payback_years, 4),
            "npv": round(self.npv(discount_rate, years), 2),
        }


@dataclass
class ScenarioComparison:
    """Comparison of multiple scenarios against baseline."""
    baseline_result: ScenarioResult
    scenario_results: List[ScenarioResult]
    
    def get_npv_ranking(self, discount_rate: float = 0.08, years: int = 15) -> List[Tuple[str, float]]:
        """Return scenarios ranked by NPV."""
        rankings = [
            (r.scenario.name, r.npv(discount_rate, years))
            for r in self.scenario_results
        ]
        return sorted(rankings, key=lambda x: x[1], reverse=True)
    
    def get_best_scenario(self) -> ScenarioResult:
        """Return scenario with highest NPV."""
        return max(self.scenario_results, key=lambda r: r.npv())

    def to_dicts(self, discount_rate: float = 0.08, years: int = 15) -> List[Dict[str, Any]]:
        """Export all scenario results as list of flat dictionaries.

        Includes the baseline result as the first entry followed by all
        comparison scenarios.
        """
        rows = [self.baseline_result.to_dict(discount_rate, years)]
        rows.extend(r.to_dict(discount_rate, years) for r in self.scenario_results)
        return rows

    def to_csv(self, discount_rate: float = 0.08, years: int = 15) -> str:
        """Export comparison as a CSV string.

        Returns:
            CSV-formatted string with header row and one row per scenario.
        """
        rows = self.to_dicts(discount_rate, years)
        if not rows:
            return ""
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()


# =============================================================================
# Scenario Evaluation
# =============================================================================

@dataclass
class OperatingInputs:
    """Annual operating inputs for scenario evaluation."""
    # Volumes
    centrate_m3_annual: float = 0.0
    char_produced_kg_annual: float = 0.0
    syngas_energy_mj_annual: float = 0.0
    septage_processed_m3_annual: float = 0.0
    
    # Concentrations (centrate)
    p_concentration_mg_L: float = 150.0    # Phosphorus
    n_concentration_mg_L: float = 800.0    # Ammonia-N
    
    # Energy demands
    process_heat_demand_mj: float = 0.0
    site_power_demand_kwh: float = 50_000.0  # Annual
    
    # Char properties
    char_carbon_kg_annual: float = 0.0


def evaluate_scenario(
    scenario: ValueAddScenario,
    inputs: OperatingInputs,
    baseline_revenue: float,
    baseline_opex: float,
    baseline_capex: float,
) -> ScenarioResult:
    """
    Evaluate a value-add scenario against operating inputs.
    
    Args:
        scenario: Scenario to evaluate
        inputs: Annual operating volumes and concentrations
        baseline_revenue: Baseline annual revenue (no value-add)
        baseline_opex: Baseline annual OPEX
        baseline_capex: Baseline CAPEX
    
    Returns:
        ScenarioResult with full economics
    """
    pathways = scenario.pathways
    revenue = PathwayRevenueBreakdown()
    
    # --- Struvite Recovery ---
    if pathways.struvite.enabled and pathway_allowed(pathways.struvite.maturity, scenario.risk_level):
        result = calc_struvite_recovery(
            centrate_m3_annual=inputs.centrate_m3_annual,
            p_concentration_mg_L=inputs.p_concentration_mg_L,
            recovery_efficiency=pathways.struvite.p_recovery_efficiency,
            mg_dose_ratio=pathways.struvite.mg_dose_ratio,
            struvite_revenue_per_tonne=pathways.struvite.struvite_revenue_per_tonne,
        )
        revenue.struvite_revenue = result.revenue_annual
    
    # --- Ammonia Stripping ---
    if pathways.ammonia_stripping.enabled and pathway_allowed(pathways.ammonia_stripping.maturity, scenario.risk_level):
        result = calc_ammonia_stripping(
            centrate_m3_annual=inputs.centrate_m3_annual,
            n_concentration_mg_L=inputs.n_concentration_mg_L,
            recovery_efficiency=pathways.ammonia_stripping.n_recovery_efficiency,
            acid_consumption_kg_per_kg_n=pathways.ammonia_stripping.acid_consumption_kg_per_kg_n,
            steam_mj_per_m3=50.0,  # Typical steam requirement
            ammonium_sulfate_revenue_per_tonne=pathways.ammonia_stripping.ammonium_sulfate_revenue_per_tonne,
        )
        revenue.ammonia_revenue = result.revenue_annual
    
    # --- CHP ---
    if pathways.chp.enabled and pathway_allowed(pathways.chp.maturity, scenario.risk_level):
        result = calc_syngas_chp(
            syngas_energy_annual_mj=inputs.syngas_energy_mj_annual,
            process_heat_demand_mj=inputs.process_heat_demand_mj,
            electrical_efficiency=pathways.chp.electrical_efficiency,
            thermal_efficiency=pathways.chp.thermal_efficiency,
            site_power_demand_kwh=inputs.site_power_demand_kwh,
            grid_export_enabled=pathways.chp.grid_export_enabled,
            export_rate_per_kwh=pathways.chp.export_rate_per_kwh,
        )
        revenue.chp_grid_revenue = result.grid_revenue_annual
    
    # --- Heat Export ---
    if pathways.heat_export.enabled and pathway_allowed(pathways.heat_export.maturity, scenario.risk_level):
        # Calculate excess heat (simplified)
        excess_heat = max(0, inputs.syngas_energy_mj_annual * 0.3 - inputs.process_heat_demand_mj * 0.2)
        result = calc_heat_export(
            excess_heat_mj=excess_heat,
            exportable_fraction=pathways.heat_export.exportable_fraction,
            heat_rate_per_gj=pathways.heat_export.heat_rate_per_gj,
        )
        revenue.heat_export_revenue = result.revenue_annual
    
    # --- Char Activation ---
    if pathways.char_activation.enabled and pathway_allowed(pathways.char_activation.maturity, scenario.risk_level):
        # Assume activating 30% of char production
        char_to_activate = inputs.char_produced_kg_annual * 0.30
        result = calc_char_activation(
            char_input_kg=char_to_activate,
            activation_yield=pathways.char_activation.activation_yield,
            steam_kg_per_kg_char=1.5,  # Typical steam ratio
            base_price_per_tonne=225.0,  # Tier-2 price
            activated_premium_per_tonne=pathways.char_activation.activated_char_premium_per_tonne,
        )
        revenue.char_activation_premium = result.revenue_premium
    
    # --- Screenings Reuse ---
    if pathways.screenings_reuse.enabled and pathway_allowed(pathways.screenings_reuse.maturity, scenario.risk_level):
        result = calc_screenings_reuse(
            septage_processed_m3=inputs.septage_processed_m3_annual,
            char_produced_kg=inputs.char_produced_kg_annual,
            screenings_fraction=pathways.screenings_reuse.screenings_fraction_of_feed,
            grit_fraction=pathways.screenings_reuse.grit_fraction_of_feed,
            ash_fraction=pathways.screenings_reuse.ash_fraction_of_char,
            density_kg_m3=1020.0,
            landfill_cost_per_tonne=pathways.screenings_reuse.landfill_cost_per_tonne,
            reuse_credit_per_tonne=pathways.screenings_reuse.reuse_credit_per_tonne,
        )
        revenue.screenings_reuse_credit = result.avoided_disposal_cost + result.reuse_revenue
    
    # --- Carbon Credits ---
    if pathways.meta_products.carbon_credits_enabled:
        result = calc_carbon_credits(
            char_carbon_kg=inputs.char_carbon_kg_annual,
            permanence_discount=pathways.meta_products.permanence_discount,
            credit_price_per_tonne_co2e=pathways.meta_products.carbon_credit_price_per_tonne_co2e,
        )
        revenue.carbon_credit_revenue = result.credit_revenue_annual
    
    # --- Off-Spec Thermal Destruction ---
    if pathways.offspec_thermal.enabled:
        # Avoided haul-off cost (assume 5% of load is off-spec, 50% can be thermally destroyed)
        offspec_volume = inputs.septage_processed_m3_annual * 0.05 * 0.50
        revenue.avoided_disposal_savings = offspec_volume * pathways.offspec_thermal.haul_off_cost_per_m3
    
    return ScenarioResult(
        scenario=scenario,
        baseline_revenue_annual=baseline_revenue,
        baseline_opex_annual=baseline_opex,
        baseline_capex=baseline_capex,
        pathway_capex=scenario.total_capex(),
        pathway_opex_annual=scenario.total_annual_opex(),
        pathway_revenue=revenue,
    )


def compare_scenarios(
    scenarios: List[ValueAddScenario],
    inputs: OperatingInputs,
    baseline_revenue: float,
    baseline_opex: float,
    baseline_capex: float,
) -> ScenarioComparison:
    """
    Compare multiple scenarios against baseline.
    
    Args:
        scenarios: List of scenarios to evaluate
        inputs: Operating inputs
        baseline_revenue: Baseline annual revenue
        baseline_opex: Baseline annual OPEX
        baseline_capex: Baseline CAPEX
    
    Returns:
        ScenarioComparison with all results
    """
    baseline_result = evaluate_scenario(
        SCENARIO_BASELINE, inputs, baseline_revenue, baseline_opex, baseline_capex
    )
    
    results = [
        evaluate_scenario(s, inputs, baseline_revenue, baseline_opex, baseline_capex)
        for s in scenarios
    ]
    
    return ScenarioComparison(
        baseline_result=baseline_result,
        scenario_results=results,
    )


def export_comparison_csv(
    comparison: ScenarioComparison,
    filepath: str,
    discount_rate: float = 0.08,
    years: int = 15,
) -> None:
    """Write scenario comparison to a CSV file.

    Args:
        comparison: ScenarioComparison to export.
        filepath: Destination file path (e.g. ``sensitivity/scenarios.csv``).
        discount_rate: Discount rate for NPV calculation.
        years: Analysis horizon.
    """
    csv_text = comparison.to_csv(discount_rate, years)
    with open(filepath, "w", newline="") as f:
        f.write(csv_text)


# =============================================================================
# Sensitivity Integration
# =============================================================================

def create_pathway_sweep_setter(
    pathway_name: str,
    param_name: str,
) -> Callable[[ValueAddScenario, float], ValueAddScenario]:
    """
    Create a setter function for sweeping pathway parameters.
    
    Args:
        pathway_name: Name of pathway (e.g., 'struvite', 'chp')
        param_name: Parameter to sweep (e.g., 'struvite_revenue_per_tonne')
    
    Returns:
        Setter function compatible with sensitivity sweep infrastructure
    """
    def setter(scenario: ValueAddScenario, value: float) -> ValueAddScenario:
        pathways = scenario.pathways
        
        if pathway_name == 'struvite':
            old_params = pathways.struvite
            if param_name == 'struvite_revenue_per_tonne':
                new_params = replace(old_params, struvite_revenue_per_tonne=value)
            elif param_name == 'p_recovery_efficiency':
                new_params = replace(old_params, p_recovery_efficiency=value)
            else:
                raise ValueError(f"Unknown param: {param_name}")
            new_pathways = replace(pathways, struvite=new_params)
        
        elif pathway_name == 'chp':
            old_params = pathways.chp
            if param_name == 'export_rate_per_kwh':
                new_params = replace(old_params, export_rate_per_kwh=value)
            elif param_name == 'electrical_efficiency':
                new_params = replace(old_params, electrical_efficiency=value)
            else:
                raise ValueError(f"Unknown param: {param_name}")
            new_pathways = replace(pathways, chp=new_params)
        
        elif pathway_name == 'char_activation':
            old_params = pathways.char_activation
            if param_name == 'activated_char_premium_per_tonne':
                new_params = replace(old_params, activated_char_premium_per_tonne=value)
            else:
                raise ValueError(f"Unknown param: {param_name}")
            new_pathways = replace(pathways, char_activation=new_params)
        
        else:
            raise ValueError(f"Unknown pathway: {pathway_name}")
        
        return replace(scenario, pathways=new_pathways)
    
    return setter


def sweep_pathway_1d(
    scenario: ValueAddScenario,
    inputs: OperatingInputs,
    baseline_revenue: float,
    baseline_opex: float,
    baseline_capex: float,
    pathway_name: str,
    param_name: str,
    values: List[float],
) -> List[Tuple[float, float]]:
    """
    1D sensitivity sweep over a pathway parameter.
    
    Returns list of (param_value, NPV) tuples.
    """
    setter = create_pathway_sweep_setter(pathway_name, param_name)
    results = []
    
    for value in values:
        modified_scenario = setter(scenario, value)
        result = evaluate_scenario(
            modified_scenario, inputs, baseline_revenue, baseline_opex, baseline_capex
        )
        results.append((value, result.npv()))
    
    return results
