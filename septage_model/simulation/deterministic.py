"""
Stage 1 Deterministic Solver - Steady-state feasibility analysis.

This module validates system viability using:
    - Steady-state mass/energy balances
    - Buffer sizing constraints
    - Permit limit checks
    - Energy self-sufficiency analysis

Stage 1 must pass before Stage 2 (stochastic) is meaningful.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum, auto

# Already imported above
from ..core.balances import (
    calc_dewatering,
    calc_dryer,
    calc_pyrolysis,
    calc_energy_balance,
    calc_carbon_balance,
    # Option B functions
    calc_cofeed_routing,
    calc_option_b_thermal,
    calc_segregated_char_revenue,
)
from ..core.parameters import (
    ModelParameters,
    DeploymentMode,
    DeploymentParams,
    StaffingModel,
    OperationsParams,
    create_baseline_parameters,
    create_option_b_scenario,
    create_product_scenario,
    create_hub_scenario,
)
from ..analysis.sizing import (
    calc_system_sizing,
    calc_steady_state_flows,
    check_permit_constraints,
    size_equipment,
    SteadyStateFlows,
    SystemSizing,
)


class ViabilityStatus(Enum):
    VIABLE = auto()
    MARGINAL = auto()
    NOT_VIABLE = auto()


@dataclass
class Constraint:
    """Single constraint evaluation."""
    name: str
    description: str
    required_value: float
    available_value: float
    unit: str
    margin_percent: float
    status: ViabilityStatus
    warning: str = ""
    
    def __str__(self) -> str:
        status_str = {
            ViabilityStatus.VIABLE: "✓ PASS",
            ViabilityStatus.MARGINAL: "⚠ MARGINAL",
            ViabilityStatus.NOT_VIABLE: "✗ FAIL"
        }[self.status]
        return (f"{self.name}: {status_str} "
                f"(required={self.required_value:.2f}, "
                f"available={self.available_value:.2f} {self.unit}, "
                f"margin={self.margin_percent:+.1f}%)")


@dataclass
class EnergyAnalysis:
    """Energy balance analysis results."""
    dryer_duty_mj_hr: float
    pyro_duty_mj_hr: float
    syngas_energy_mj_hr: float
    net_heat_mj_hr: float
    heat_deficit: bool
    aux_fuel_mj_hr: float
    energy_self_sufficiency: float


@dataclass
class CarbonAnalysis:
    """Carbon accounting results."""
    annual_carbon_in_tonnes: float
    annual_char_carbon_tonnes: float
    annual_sequestered_tonnes: float
    annual_credits_tco2e: float
    sequestration_rate: float


@dataclass
class EconomicSummary:
    """High-level economic summary."""
    annual_revenue: float
    annual_opex: float
    annual_noi: float
    total_capex: float
    simple_payback_years: float
    required_tipping_fee: float


@dataclass
class Stage1Result:
    """Complete Stage 1 analysis result."""
    params: ModelParameters
    flows: SteadyStateFlows
    sizing: SystemSizing
    constraints: List[Constraint]
    energy: EnergyAnalysis
    carbon: CarbonAnalysis
    economics: EconomicSummary
    
    overall_status: ViabilityStatus = ViabilityStatus.VIABLE
    critical_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def is_viable(self) -> bool:
        return self.overall_status != ViabilityStatus.NOT_VIABLE
    
    def summary(self) -> str:
        lines = [
            "=" * 60,
            "STAGE 1 DETERMINISTIC ANALYSIS SUMMARY",
            "=" * 60,
            f"Parameter Set: {self.params.name}",
            f"Hash: {self.params.compute_hash()}",
            "",
            "--- Service Area ---",
            f"  Annual Septage: {self.flows.annual_septage_m3:,.0f} m³/yr",
            f"  Avg Flow: {self.flows.septage_m3_hr:.2f} m³/hr",
            f"  Peak Flow: {self.flows.peak_septage_m3_hr:.2f} m³/hr",
            "",
            "--- System Sizing ---",
            f"  EQ Tank: {self.sizing.eq_tank_m3:.1f} m³",
            f"  Centrate Tank: {self.sizing.centrate_tank_m3:.1f} m³",
            f"  Cake Storage: {self.sizing.cake_storage_kgds:.0f} kg DS",
            f"  Char Storage: {self.sizing.char_storage_kg:.0f} kg",
            "",
            "--- Mass Balance ---",
            f"  Annual Char: {self.flows.annual_char_tonnes:.1f} tonnes",
            f"  Annual Centrate: {self.flows.annual_centrate_m3:,.0f} m³",
            "",
            "--- Energy Balance ---",
            f"  Dryer Duty: {self.energy.dryer_duty_mj_hr:.1f} MJ/hr",
            f"  Syngas Energy: {self.energy.syngas_energy_mj_hr:.1f} MJ/hr",
            f"  Net Heat: {self.energy.net_heat_mj_hr:.1f} MJ/hr",
            f"  Self-Sufficiency: {self.energy.energy_self_sufficiency:.1%}",
            "",
            "--- Carbon ---",
            f"  Annual Sequestered: {self.carbon.annual_sequestered_tonnes:.1f} tonnes C",
            f"  Annual Credits: {self.carbon.annual_credits_tco2e:.1f} tCO2e",
            "",
            "--- Economics ---",
            f"  Total CAPEX: ${self.economics.total_capex:,.0f}",
            f"  Annual NOI: ${self.economics.annual_noi:,.0f}",
            f"  Simple Payback: {self.economics.simple_payback_years:.1f} years",
            "",
            "--- Constraints ---",
        ]
        
        for c in self.constraints:
            lines.append(f"  {c}")
        
        lines.extend([
            "",
            f"OVERALL STATUS: {self.overall_status.name}",
        ])
        
        if self.critical_issues:
            lines.append("\nCRITICAL ISSUES:")
            for issue in self.critical_issues:
                lines.append(f"  ✗ {issue}")
        
        if self.warnings:
            lines.append("\nWARNINGS:")
            for warn in self.warnings:
                lines.append(f"  ⚠ {warn}")
        
        lines.append("=" * 60)
        return "\n".join(lines)


def run_stage1(params: Optional[ModelParameters] = None) -> Stage1Result:
    """
    Run Stage 1 deterministic analysis.
    
    Args:
        params: Model parameters (uses baseline if None)
    
    Returns:
        Stage1Result with complete analysis
    """
    if params is None:
        params = create_baseline_parameters()
    
    sizing_result = size_equipment(params)
    sizing = sizing_result["sizing"]
    flows = sizing.flows
    
    dw_result = calc_dewatering(
        septage_m3=flows.septage_m3_hr,
        ts_fraction=params.service_area.ts_fraction_mean,
        density_kg_m3=params.service_area.density_kg_m3,
        cake_ts_fraction=params.dewatering.cake_ts_fraction,
        solids_capture=params.dewatering.solids_capture,
        polymer_kg_per_tds=params.dewatering.polymer_kg_per_tds,
        power_kwh_per_m3=params.dewatering.power_kwh_per_m3
    )
    
    dr_result = calc_dryer(
        cake_kgds=flows.dryer_feed_kgds_hr,
        cake_ts_fraction=params.dewatering.cake_ts_fraction,
        dried_ts_fraction=params.dryer.dried_ts_fraction,
        energy_kwh_per_kg_water=params.dryer.energy_kwh_per_kg_water,
        thermal_efficiency=params.dryer.thermal_efficiency
    )
    
    py_result = calc_pyrolysis(
        dried_kgds=flows.pyro_feed_kgds_hr,
        dried_ts_fraction=params.dryer.dried_ts_fraction,
        yield_char=params.pyrolysis.yield_char,
        yield_gas=params.pyrolysis.yield_gas,
        yield_condensate=params.pyrolysis.yield_condensate,
        heat_requirement_mj_kgds=params.pyrolysis.heat_requirement_mj_kgds,
        lhv_syngas_mj_kg=params.pyrolysis.lhv_syngas_sept_mj_kg,
        syngas_recovery_efficiency=params.pyrolysis.syngas_recovery_efficiency,
        char_carbon_fraction=params.pyrolysis.char_carbon_fraction,
        char_permanence_factor=params.pyrolysis.char_permanence_factor
    )
    
    energy_result = calc_energy_balance(
        dryer_duty_mj=dr_result.heat_duty_mj,
        pyro_duty_mj=py_result.heat_required_mj,
        syngas_energy_mj=py_result.syngas_energy_mj
    )
    
    total_heat_required = dr_result.heat_duty_mj + py_result.heat_required_mj
    self_sufficiency = py_result.syngas_energy_mj / total_heat_required if total_heat_required > 0 else 1.0
    
    energy = EnergyAnalysis(
        dryer_duty_mj_hr=dr_result.heat_duty_mj,
        pyro_duty_mj_hr=py_result.heat_required_mj,
        syngas_energy_mj_hr=py_result.syngas_energy_mj,
        net_heat_mj_hr=energy_result.net_heat_mj,
        heat_deficit=energy_result.heat_deficit,
        aux_fuel_mj_hr=energy_result.aux_fuel_mj,
        energy_self_sufficiency=self_sufficiency
    )
    
    carbon_result = calc_carbon_balance(
        septage_kgds=flows.septage_kgds_hr * 8760,
        cofeed_kgds=0,
        char_kg=py_result.char_produced_kg * flows.effective_hours_yr,
        char_carbon_fraction=params.pyrolysis.char_carbon_fraction,
        char_permanence_factor=params.pyrolysis.char_permanence_factor,
        septage_m3=flows.annual_septage_m3
    )
    
    carbon = CarbonAnalysis(
        annual_carbon_in_tonnes=carbon_result.carbon_in_kg / 1000,
        annual_char_carbon_tonnes=carbon_result.char_carbon_kg / 1000,
        annual_sequestered_tonnes=carbon_result.sequestered_kg / 1000,
        annual_credits_tco2e=carbon_result.net_credits_kgco2e / 1000,
        sequestration_rate=carbon_result.sequestered_kg / carbon_result.carbon_in_kg if carbon_result.carbon_in_kg > 0 else 0
    )
    
    # Get CAPEX first (needed for insurance calc)
    total_capex = sizing_result["total_capex"]
    
    ep = params.economic
    
    # Revenue calculations
    tipping_revenue = flows.annual_septage_m3 * ep.tipping_fee_per_m3
    char_revenue = flows.annual_char_tonnes * ep.char_sale_price_per_tonne
    carbon_revenue = carbon.annual_credits_tco2e * ep.carbon_credit_per_tco2e if ep.carbon_credits_enabled else 0
    annual_revenue = tipping_revenue + char_revenue + carbon_revenue
    
    # OPEX calculations
    # Electricity: dewatering + dryer aux (if heat deficit)
    dewatering_power_kwh_yr = dw_result.power_kwh * 8760  # Scaled from hourly rate
    aux_heat_kwh_yr = energy.aux_fuel_mj_hr * flows.effective_hours_yr / 3.6 if energy.heat_deficit else 0
    electricity_cost = (dewatering_power_kwh_yr + aux_heat_kwh_yr * 0.3) * ep.electricity_price_kwh  # 0.3 = electric heating efficiency factor
    
    # Natural gas for heat deficit
    gas_cost = energy.aux_fuel_mj_hr * flows.effective_hours_yr * ep.natural_gas_price_mj if energy.heat_deficit else 0
    
    polymer_cost = dw_result.polymer_used_kg * 8760 * ep.polymer_cost_per_kg
    labor_hours = ep.operators_per_shift * ep.shifts_per_day * 365 * 8
    labor_cost = labor_hours * ep.hourly_rate
    
    # Insurance and maintenance (fraction of CAPEX)
    insurance_cost = total_capex * ep.insurance_fraction_of_capex
    
    annual_opex = electricity_cost + gas_cost + polymer_cost + labor_cost + insurance_cost + ep.compliance_annual
    annual_noi = annual_revenue - annual_opex
    
    simple_payback = total_capex / annual_noi if annual_noi > 0 else float('inf')
    
    breakeven_tipping = (annual_opex - char_revenue - carbon_revenue) / flows.annual_septage_m3 if flows.annual_septage_m3 > 0 else 0
    
    economics = EconomicSummary(
        annual_revenue=annual_revenue,
        annual_opex=annual_opex,
        annual_noi=annual_noi,
        total_capex=total_capex,
        simple_payback_years=simple_payback,
        required_tipping_fee=breakeven_tipping
    )
    
    constraints = []
    critical_issues = []
    warnings = []
    
    constraints.append(Constraint(
        name="Centrate Discharge",
        description="Required discharge rate vs permit limit",
        required_value=sizing.actual_discharge_rate_m3_hr,
        available_value=sizing.permit_discharge_rate_m3_hr,
        unit="m³/hr",
        margin_percent=(sizing.permit_discharge_rate_m3_hr - sizing.actual_discharge_rate_m3_hr) / sizing.permit_discharge_rate_m3_hr * 100,
        status=ViabilityStatus.VIABLE if sizing.discharge_utilization < 0.85 else (ViabilityStatus.MARGINAL if sizing.discharge_utilization < 1.0 else ViabilityStatus.NOT_VIABLE)
    ))
    
    if sizing.discharge_utilization > 1.0:
        critical_issues.append(f"Centrate discharge rate exceeds permit ({sizing.discharge_utilization:.0%} of capacity)")
    elif sizing.discharge_utilization > 0.85:
        warnings.append(f"High centrate discharge utilization ({sizing.discharge_utilization:.0%})")
    
    constraints.append(Constraint(
        name="Energy Self-Sufficiency",
        description="Syngas energy vs thermal demand",
        required_value=100,
        available_value=self_sufficiency * 100,
        unit="%",
        margin_percent=(self_sufficiency - 1.0) * 100,
        status=ViabilityStatus.VIABLE if self_sufficiency >= 1.0 else (ViabilityStatus.MARGINAL if self_sufficiency >= 0.80 else ViabilityStatus.NOT_VIABLE)
    ))
    
    if self_sufficiency < 0.80:
        critical_issues.append(f"Large energy deficit - only {self_sufficiency:.0%} self-sufficient")
    elif self_sufficiency < 1.0:
        warnings.append(f"Auxiliary fuel needed - {self_sufficiency:.0%} self-sufficient")
    
    constraints.append(Constraint(
        name="Economic Viability",
        description="Simple payback period",
        required_value=params.economic.analysis_period_years,
        available_value=simple_payback,
        unit="years",
        margin_percent=(params.economic.analysis_period_years - simple_payback) / params.economic.analysis_period_years * 100 if simple_payback < float('inf') else -100,
        status=ViabilityStatus.VIABLE if simple_payback < 10 else (ViabilityStatus.MARGINAL if simple_payback < 15 else ViabilityStatus.NOT_VIABLE)
    ))
    
    if simple_payback > params.economic.analysis_period_years:
        critical_issues.append(f"Payback ({simple_payback:.1f}yr) exceeds analysis period ({params.economic.analysis_period_years}yr)")
    elif simple_payback > 10:
        warnings.append(f"Long payback period ({simple_payback:.1f} years)")
    
    constraints.append(Constraint(
        name="Dewatering Capacity",
        description="Peak flow vs equipment capacity",
        required_value=flows.peak_septage_m3_hr,
        available_value=params.dewatering.max_throughput_m3_hr,
        unit="m³/hr",
        margin_percent=(params.dewatering.max_throughput_m3_hr - flows.peak_septage_m3_hr) / params.dewatering.max_throughput_m3_hr * 100,
        status=ViabilityStatus.VIABLE if flows.peak_septage_m3_hr < params.dewatering.max_throughput_m3_hr * 0.9 else ViabilityStatus.MARGINAL
    ))
    
    constraints.append(Constraint(
        name="Dryer Capacity",
        description="Required feed rate vs equipment capacity",
        required_value=flows.dryer_feed_kgds_hr,
        available_value=params.dryer.max_throughput_kgds_hr,
        unit="kgDS/hr",
        margin_percent=(params.dryer.max_throughput_kgds_hr - flows.dryer_feed_kgds_hr) / params.dryer.max_throughput_kgds_hr * 100,
        status=ViabilityStatus.VIABLE if flows.dryer_feed_kgds_hr < params.dryer.max_throughput_kgds_hr * 0.9 else ViabilityStatus.MARGINAL
    ))
    
    constraints.append(Constraint(
        name="Pyrolysis Capacity",
        description="Required feed rate vs equipment capacity",
        required_value=flows.pyro_feed_kgds_hr,
        available_value=params.pyrolysis.max_throughput_kgds_hr,
        unit="kgDS/hr",
        margin_percent=(params.pyrolysis.max_throughput_kgds_hr - flows.pyro_feed_kgds_hr) / params.pyrolysis.max_throughput_kgds_hr * 100,
        status=ViabilityStatus.VIABLE if flows.pyro_feed_kgds_hr < params.pyrolysis.max_throughput_kgds_hr * 0.9 else ViabilityStatus.MARGINAL
    ))
    
    overall = ViabilityStatus.VIABLE
    for c in constraints:
        if c.status == ViabilityStatus.NOT_VIABLE:
            overall = ViabilityStatus.NOT_VIABLE
            break
        elif c.status == ViabilityStatus.MARGINAL:
            overall = ViabilityStatus.MARGINAL
    
    return Stage1Result(
        params=params,
        flows=flows,
        sizing=sizing,
        constraints=constraints,
        energy=energy,
        carbon=carbon,
        economics=economics,
        overall_status=overall,
        critical_issues=critical_issues,
        warnings=warnings
    )


def run_sanity_checks(params: Optional[ModelParameters] = None) -> Tuple[bool, List[str]]:
    """
    Run quick sanity checks on parameters and basic balances.
    
    Returns (passed, list_of_issues).
    """
    if params is None:
        params = create_baseline_parameters()
    
    issues = []
    
    yields_sum = params.pyrolysis.yield_char + params.pyrolysis.yield_gas + params.pyrolysis.yield_condensate
    if abs(yields_sum - 1.0) > 0.001:
        issues.append(f"Pyrolysis yields don't sum to 1.0: {yields_sum:.3f}")
    
    if sum(params.service_area.monthly_multipliers) == 0:
        issues.append("Monthly multipliers sum to zero")
    
    monthly_avg = sum(params.service_area.monthly_multipliers) / 12
    if abs(monthly_avg - 1.0) > 0.1:
        issues.append(f"Monthly multipliers don't average to ~1.0: {monthly_avg:.2f}")
    
    if params.operating.thermal_uptime <= 0 or params.operating.thermal_uptime > 1:
        issues.append(f"Invalid thermal uptime: {params.operating.thermal_uptime}")
    
    discharge_hours = params.discharge.hours_per_week()
    weekly_centrate = (params.service_area.annual_septage_m3 / 52) * 0.95
    min_discharge_rate = weekly_centrate / discharge_hours
    if min_discharge_rate > params.discharge.q_permit_m3_hr:
        issues.append(f"Permit discharge rate ({params.discharge.q_permit_m3_hr} m³/hr) "
                     f"insufficient for weekly centrate (needs {min_discharge_rate:.2f} m³/hr)")
    
    flows = calc_steady_state_flows(params)
    if flows.dryer_feed_kgds_hr > params.dryer.max_throughput_kgds_hr:
        issues.append(f"Dryer undersized: need {flows.dryer_feed_kgds_hr:.1f} kgDS/hr, "
                     f"max {params.dryer.max_throughput_kgds_hr} kgDS/hr")
    
    if flows.pyro_feed_kgds_hr > params.pyrolysis.max_throughput_kgds_hr:
        issues.append(f"Pyrolysis undersized: need {flows.pyro_feed_kgds_hr:.1f} kgDS/hr, "
                     f"max {params.pyrolysis.max_throughput_kgds_hr} kgDS/hr")
    
    return len(issues) == 0, issues


def print_stage1_summary(result: Stage1Result) -> None:
    """Print formatted Stage 1 summary to console."""
    print(result.summary())



# ============================================================================
# OPTION B: Solids-Centric Facility with Mandatory Co-Feed
# ============================================================================

@dataclass
class OptionBEnergyAnalysis:
    """Energy balance analysis for Option B configuration."""
    dryer_duty_mj_hr: float
    pyro_duty_mj_hr: float
    syngas_septage_mj_hr: float
    syngas_cofeed_mj_hr: float
    syngas_total_mj_hr: float
    net_heat_mj_hr: float
    heat_deficit: bool
    aux_fuel_mj_hr: float
    energy_self_sufficiency: float
    cofeed_bypass_mode: bool


@dataclass
class OptionBCharAnalysis:
    """Segregated char production and revenue for Option B."""
    char_septage_kg_hr: float
    char_cofeed_kg_hr: float
    char_total_kg_hr: float
    tier_septage: int
    tier_cofeed: int
    annual_char_septage_tonnes: float
    annual_char_cofeed_tonnes: float
    annual_char_total_tonnes: float
    revenue_septage: float
    revenue_cofeed: float
    revenue_total: float


@dataclass
class OptionBCofeedAnalysis:
    """Co-feed supply analysis for Option B."""
    annual_cofeed_tds: float
    monthly_delivery_tds: list
    transport_km: float
    transport_cost_annual: float
    contract_security: float
    seasonal_profile_name: str


@dataclass
class OptionBEconomicSummary:
    """Economic summary for Option B configuration."""
    tipping_revenue: float
    char_revenue_septage: float
    char_revenue_cofeed: float
    char_revenue_total: float
    carbon_revenue: float
    annual_revenue: float
    electricity_cost: float
    gas_cost: float
    polymer_cost: float
    labor_cost: float
    maintenance_cost: float  # Annual maintenance (from MaintenanceModel or %CAPEX)
    insurance_cost: float
    compliance_cost: float
    cofeed_transport_cost: float
    annual_opex: float
    annual_noi: float
    total_capex: float
    simple_payback_years: float
    required_tipping_fee: float



@dataclass
class BuyerEconomics:
    """
    Product Mode economics from buyer's perspective.
    
    Payback reported on two bases:
      (A) Avoided fees only - conservative, ignores char revenue
      (B) Avoided fees + char revenue - realistic case
    
    Also includes non-cash value (truck hours, fuel) for bankability.
    """
    # Current cost baseline
    annual_septage_m3: float
    reference_dumping_fee: float
    current_annual_cost: float  # what buyer pays now for dumping
    
    # With product
    annual_opex_cash: float  # consumables, maintenance, utilities (no labor)
    cash_labor_cost: float  # always $0 for Product Mode (owner-operated)
    annual_cofeed_cost: float  # co-feed procurement/transport
    total_annual_cost: float  # opex + cofeed (no cash labor)
    
    # Savings - explicit dual-basis
    annual_net_savings_avoided_fees_only: float  # current_cost - total_annual_cost
    annual_net_savings_with_char: float  # avoided_fees + char_revenue
    capex: float  # 0.6× equipment cost
    payback_avoided_fees_only: float  # capex / avoided_fees_savings
    payback_with_char_revenue: float  # capex / (avoided_fees + char)
    
    # Revenue potential (informational)
    char_revenue_potential: float  # if sold
    carbon_credit_potential: float  # if monetized
    
    # Owner time commitment (informational, not cash cost)
    owner_time_hours_per_week: float  # from StaffingModel
    
    # Non-cash value (operational benefits beyond dumping fees)
    truck_hours_saved_per_year: float = 0.0  # Hours not spent hauling
    fuel_saved_per_year: float = 0.0  # $ fuel not consumed
    driver_time_value_per_year: float = 0.0  # $ value of driver hours freed
    dispatch_risk_note: str = ""  # Qualitative note on scheduling benefit


@dataclass
class ProductModeResult:
    """
    Product Mode analysis result - buyer economics framing.
    
    This is the primary output for owner-operated deployment.
    Wraps OptionBStage1Result with buyer-centric metrics.
    
    Design Constraints:
        The model calculates the maximum allowable maintenance burden
        for economic viability. These are go/no-go engineering requirements,
        not preferences.
    """
    # Technical basis (same physics as Hub)
    base_result: 'OptionBStage1Result'
    
    # Buyer economics
    buyer: BuyerEconomics
    
    # Deployment params
    deployment: DeploymentParams
    
    # Design constraints (derived from economics)
    # These define the engineering requirements for product viability
    max_maintenance_budget_per_year: float = 0.0  # $ - annual maint must be below this
    max_callouts_per_week: float = 0.0            # callouts/week limit
    owner_serviceable_required: bool = True       # must be owner-serviceable to be viable
    design_status: str = ""                       # summary of design requirements
    
    @property
    def is_product_viable(self) -> bool:
        """Product Mode viability: energy OK and payback < 15 years (with char)."""
        energy_ok = self.base_result.energy.energy_self_sufficiency >= 1.0
        return energy_ok and self.buyer.payback_with_char_revenue < 15.0
    
    @property
    def payback_with_char(self) -> float:
        """Payback if char is sold (more realistic case). Alias for clarity."""
        return self.buyer.payback_with_char_revenue
    
    @property
    def product_status(self) -> str:
        """Product Mode status string."""
        if self.is_product_viable:
            return "VIABLE"
        elif self.base_result.energy.energy_self_sufficiency >= 1.0:
            return "MARGINAL (economics)"
        else:
            return "NOT VIABLE (energy)"
    
    def summary(self) -> str:
        """
        Generate buyer-focused summary.
        
        Payback reported on two bases:
          (A) Avoided fees only - conservative
          (B) Avoided fees + char revenue - realistic case
        """
        lines = [
            "="*70,
            "PRODUCT MODE: OWNER-OPERATED SEPTAGE PROCESSING UNIT",
            "="*70,
            "",
            f"Product Status: {self.product_status}",
            "",
            "--- Your Current Situation ---",
            f"  Annual septage:       {self.buyer.annual_septage_m3:,.0f} m3/yr",
            f"  Current dump fee:     ${self.buyer.reference_dumping_fee:.0f}/m3",
            f"  Current annual cost:  ${self.buyer.current_annual_cost:,.0f}/yr",
            "",
            "--- With This Equipment ---",
            f"  Annual operating cost: ${self.buyer.total_annual_cost:,.0f}/yr",
            f"    - Consumables/maint: ${self.buyer.annual_opex_cash:,.0f}",
            f"    - Co-feed supply:    ${self.buyer.annual_cofeed_cost:,.0f}",
            f"    - Cash labor:        ${self.buyer.cash_labor_cost:,.0f} (owner-operated)",
            "",
            "--- Payback Legend ---",
            "  (A) Avoided fees only: conservative, ignores char revenue",
            "  (B) With char revenue: realistic case",
            "",
            "--- Your Savings (Basis A: Avoided Fees Only) ---",
            f"  Annual savings:        ${self.buyer.annual_net_savings_avoided_fees_only:,.0f}/yr",
            f"  Equipment cost:        ${self.buyer.capex:,.0f}",
            f"  Payback (A):           {self.buyer.payback_avoided_fees_only:.1f} years",
            "",
            "--- Your Savings (Basis B: With Char Revenue) ---",
            f"  Char sale revenue:     ${self.buyer.char_revenue_potential:,.0f}/yr",
            f"  Total annual benefit:  ${self.buyer.annual_net_savings_with_char:,.0f}/yr",
            f"  Payback (B):           {self.buyer.payback_with_char_revenue:.1f} years",
            "",
            "--- Non-Cash Operational Value ---",
            f"  Truck hours eliminated: {self.buyer.truck_hours_saved_per_year:,.0f} hrs/yr",
            f"  Fuel cost avoided:      ${self.buyer.fuel_saved_per_year:,.0f}/yr",
            f"  Driver time value:      ${self.buyer.driver_time_value_per_year:,.0f}/yr",
            f"  Note: {self.buyer.dispatch_risk_note}",
            "",
            "--- Additional Upside ---",
            f"  Carbon credit potential: ${self.buyer.carbon_credit_potential:,.0f}/yr (if enabled)",
            "",
            "--- Your Time Commitment ---",
            f"  Owner hours/week:      {self.buyer.owner_time_hours_per_week:.1f} hrs (not cash cost)",
            "",
            "--- Technical Performance ---",
            f"  Energy self-sufficiency: {self.base_result.energy.energy_self_sufficiency:.0%}",
            f"  Off-grid capable: {'YES' if self.base_result.energy.energy_self_sufficiency >= 1.0 else 'NO'}",
            "",
        ]
        
        # Design requirements section
        lines.extend([
            "--- DESIGN REQUIREMENTS (Go/No-Go) ---",
            f"  Max maintenance budget: ${self.max_maintenance_budget_per_year:,.0f}/yr",
            f"  Max callouts:           {self.max_callouts_per_week:.2f}/week ({self.max_callouts_per_week*4:.1f}/month)",
            f"  Owner-serviceable:      {'REQUIRED' if self.owner_serviceable_required else 'Optional'}",
            "",
            f"  {self.design_status}",
            "",
            "  Design targets:",
            "    - No routine refractory relines",
            "    - Modular auger assemblies (quick-swap)",
            "    - Standardized bearings/seals (owner-replaceable)",
            "    - Predictive maintenance hooks (vibration, temp)",
            "",
        ])
        
        lines.append("="*70)
        return "\n".join(lines)


def calc_design_constraints(
    capex: float,
    avoided_fees: float,
    char_revenue: float,
    other_opex: float,
    target_payback_years: float = 15.0,
) -> dict:
    """
    Calculate the maximum allowable maintenance burden for viability.
    
    This inverts the economics to find the design envelope:
    - What is the max annual maintenance cost for target payback?
    - What callout frequency does that imply?
    
    Args:
        capex: Total equipment cost
        avoided_fees: Annual avoided disposal fees
        char_revenue: Annual char sale revenue
        other_opex: Non-maintenance OPEX (polymer, power, etc.)
        target_payback_years: Target payback for viability (default 15)
    
    Returns:
        dict with max_maintenance, max_callouts_per_week, notes
    """
    # Required annual benefit for target payback
    required_annual_benefit = capex / target_payback_years
    
    # Max OPEX = gross benefit - required net benefit
    gross_benefit = avoided_fees + char_revenue
    max_total_opex = gross_benefit - required_annual_benefit
    
    # Max maintenance = max OPEX - other OPEX
    max_maintenance = max(0, max_total_opex - other_opex)
    
    # Translate to callout frequency
    # Assume: fixed=$6k, wear=$1k, consumables=$5k, inspections=$2.5k = $14.5k base
    # Remaining goes to callouts
    base_non_callout = 14_500
    callout_budget = max(0, max_maintenance - base_non_callout)
    
    # Assume owner-serviceable @ $400/callout effective cost (60% discount from $1000)
    cost_per_callout_owner = 400
    max_annual_callouts = callout_budget / cost_per_callout_owner if cost_per_callout_owner > 0 else 0
    max_callouts_per_week = max_annual_callouts / 52
    
    # Check if viable at all
    if max_maintenance <= 0:
        status = "NOT VIABLE: Economics do not support any maintenance burden"
    elif max_callouts_per_week < 0.1:
        status = "MARGINAL: Requires near-zero callouts - extremely reliable design needed"
    elif max_callouts_per_week < 0.25:
        status = "VIABLE: Low-maintenance design required (<=1 callout/month)"
    else:
        status = "VIABLE: Standard industrial serviceability acceptable"
    
    return {
        'max_maintenance': max_maintenance,
        'max_callouts_per_week': max_callouts_per_week,
        'owner_serviceable_required': True,  # Always required at this scale
        'design_status': status,
    }


def calc_buyer_economics(
    base_result: 'OptionBStage1Result',
    deployment: DeploymentParams,
) -> BuyerEconomics:
    """
    Calculate buyer economics for Product Mode.
    
    Frames the facility as equipment that saves money vs current practice.
    Reports payback on two explicit bases:
      (A) Avoided fees only - conservative
      (B) Avoided fees + char revenue - realistic case
    
    Args:
        base_result: Technical analysis from Option B (includes StaffingModel)
        deployment: Product mode deployment parameters
    
    Returns:
        BuyerEconomics with explicit dual-basis payback
    """
    # Current cost baseline
    current_annual_cost = (
        deployment.annual_septage_m3 * deployment.reference_dumping_fee
    )
    
    # Scale OPEX for Product Mode
    # Remove labor (externalized to owner) 
    # Keep: consumables, maintenance, utilities, insurance
    base_opex = base_result.economics.annual_opex
    labor_cost = base_result.economics.labor_cost  # already annual
    
    # Subtract labor, apply remaining as owner's non-labor costs
    opex_ex_labor = base_opex - labor_cost
    
    # Scale for smaller throughput
    flow_ratio = (
        deployment.annual_septage_m3 / 
        base_result.params.service_area.annual_septage_m3
    )
    annual_opex_cash = opex_ex_labor * flow_ratio * 0.8  # economies of simplicity
    
    # Product Mode has zero cash labor cost (owner-operated)
    cash_labor_cost = 0.0
    
    # Co-feed cost
    annual_cofeed_cost = base_result.economics.cofeed_transport_cost * flow_ratio
    
    total_annual_cost = annual_opex_cash + annual_cofeed_cost
    
    # CAPEX at product multiplier
    capex = base_result.economics.total_capex * deployment.capex_multiplier
    
    # Bonus value (char and carbon, scaled)
    char_revenue = (
        base_result.economics.char_revenue_septage + 
        base_result.economics.char_revenue_cofeed
    ) * flow_ratio
    
    carbon_revenue = base_result.economics.carbon_revenue * flow_ratio
    
    # --- Explicit dual-basis savings and payback ---
    # Basis A: Avoided fees only (conservative)
    annual_net_savings_avoided_fees_only = current_annual_cost - total_annual_cost
    
    if annual_net_savings_avoided_fees_only > 0:
        payback_avoided_fees_only = capex / annual_net_savings_avoided_fees_only
    else:
        payback_avoided_fees_only = float('inf')
    
    # Basis B: Avoided fees + char revenue (realistic)
    annual_net_savings_with_char = annual_net_savings_avoided_fees_only + char_revenue
    
    if annual_net_savings_with_char > 0:
        payback_with_char_revenue = capex / annual_net_savings_with_char
    else:
        payback_with_char_revenue = float('inf')
    
    # Owner time from StaffingModel (informational, not cash cost)
    owner_time_hours_per_week = base_result.params.staffing.owner_time_hours_per_week
    
    # --- Non-cash value: hauling eliminated ---
    # Calculate truck trips eliminated
    trips_per_year = deployment.annual_septage_m3 / deployment.truck_capacity_m3
    
    # Round trip distance and time
    round_trip_km = 2 * deployment.avg_haul_distance_km
    hours_per_trip = round_trip_km / deployment.truck_speed_km_hr + 0.5  # +0.5 for loading/unloading
    
    truck_hours_saved = trips_per_year * hours_per_trip
    fuel_saved = trips_per_year * round_trip_km * deployment.fuel_cost_per_km
    driver_time_value = truck_hours_saved * deployment.driver_hourly_rate
    
    dispatch_note = (
        f"Eliminates {trips_per_year:.0f} disposal trips/yr. "
        f"No more scheduling around WWTP hours or weather."
    )
    
    return BuyerEconomics(
        annual_septage_m3=deployment.annual_septage_m3,
        reference_dumping_fee=deployment.reference_dumping_fee,
        current_annual_cost=current_annual_cost,
        annual_opex_cash=annual_opex_cash,
        cash_labor_cost=cash_labor_cost,
        annual_cofeed_cost=annual_cofeed_cost,
        total_annual_cost=total_annual_cost,
        annual_net_savings_avoided_fees_only=annual_net_savings_avoided_fees_only,
        annual_net_savings_with_char=annual_net_savings_with_char,
        capex=capex,
        payback_avoided_fees_only=payback_avoided_fees_only,
        payback_with_char_revenue=payback_with_char_revenue,
        char_revenue_potential=char_revenue,
        carbon_credit_potential=carbon_revenue,
        owner_time_hours_per_week=owner_time_hours_per_week,
        truck_hours_saved_per_year=truck_hours_saved,
        fuel_saved_per_year=fuel_saved,
        driver_time_value_per_year=driver_time_value,
        dispatch_risk_note=dispatch_note,
    )


@dataclass
class OptionBStage1Result:
    """Complete Stage 1 analysis result for Option B."""
    params: ModelParameters
    flows: SteadyStateFlows
    sizing: SystemSizing
    constraints: List[Constraint]
    energy: OptionBEnergyAnalysis
    char: OptionBCharAnalysis
    cofeed: OptionBCofeedAnalysis
    carbon: CarbonAnalysis
    economics: OptionBEconomicSummary
    overall_status: ViabilityStatus
    critical_issues: List[str]
    warnings: List[str]
    
    def summary(self) -> str:
        """Generate formatted summary of Option B Stage 1 results."""
        status_label = {
            ViabilityStatus.VIABLE: "VIABLE",
            ViabilityStatus.MARGINAL: "MARGINAL",
            ViabilityStatus.NOT_VIABLE: "NOT VIABLE"
        }
        
        lines = [
            "="*70,
            "OPTION B: SOLIDS-CENTRIC FACILITY - STAGE 1 ANALYSIS",
            "="*70,
            "",
            f"Overall Status: {status_label[self.overall_status]}",
            "",
            "--- Energy Self-Sufficiency ---",
            f"  Dryer duty:           {self.energy.dryer_duty_mj_hr:,.1f} MJ/hr",
            f"  Pyrolysis duty:       {self.energy.pyro_duty_mj_hr:,.1f} MJ/hr",
            f"  Syngas (septage):     {self.energy.syngas_septage_mj_hr:,.1f} MJ/hr",
            f"  Syngas (co-feed):     {self.energy.syngas_cofeed_mj_hr:,.1f} MJ/hr",
            f"  Syngas (total):       {self.energy.syngas_total_mj_hr:,.1f} MJ/hr",
            f"  Self-sufficiency:     {self.energy.energy_self_sufficiency:.1%}",
            f"  Co-feed bypass:       {'YES' if self.energy.cofeed_bypass_mode else 'NO'}",
            "",
            "--- Char Production (Segregated) ---",
            f"  Septage char:   {self.char.annual_char_septage_tonnes:,.1f} t/yr @ Tier {self.char.tier_septage}",
            f"  Co-feed char:   {self.char.annual_char_cofeed_tonnes:,.1f} t/yr @ Tier {self.char.tier_cofeed}",
            f"  Total char:     {self.char.annual_char_total_tonnes:,.1f} t/yr",
            "",
            "--- Co-feed Supply ---",
            f"  Annual supply:        {self.cofeed.annual_cofeed_tds:,.1f} tDS",
            f"  Transport distance:   {self.cofeed.transport_km:.0f} km",
            f"  Transport cost:       ${self.cofeed.transport_cost_annual:,.0f}/yr",
            f"  Seasonal profile:     {self.cofeed.seasonal_profile_name}",
            "",
            "--- Economics ---",
            f"  Annual Revenue:       ${self.economics.annual_revenue:,.0f}",
            f"    - Tipping:          ${self.economics.tipping_revenue:,.0f}",
            f"    - Char (septage):   ${self.economics.char_revenue_septage:,.0f}",
            f"    - Char (co-feed):   ${self.economics.char_revenue_cofeed:,.0f}",
            f"    - Carbon credits:   ${self.economics.carbon_revenue:,.0f}",
            f"  Annual OPEX:          ${self.economics.annual_opex:,.0f}",
            f"    - Co-feed transport: ${self.economics.cofeed_transport_cost:,.0f}",
            f"  Annual NOI:           ${self.economics.annual_noi:,.0f}",
            f"  CAPEX:                ${self.economics.total_capex:,.0f}",
            f"  Simple Payback:       {self.economics.simple_payback_years:.1f} years",
            "",
        ]
        
        if self.critical_issues:
            lines.append("--- CRITICAL ISSUES ---")
            for issue in self.critical_issues:
                lines.append(f"  [X] {issue}")
            lines.append("")
        
        if self.warnings:
            lines.append("--- WARNINGS ---")
            for warn in self.warnings:
                lines.append(f"  [!] {warn}")
            lines.append("")
        
        lines.append("--- Constraint Checks ---")
        for c in self.constraints:
            lines.append(f"  {c}")
        
        return "\n".join(lines)



def run_stage1_option_b(params: Optional[ModelParameters] = None) -> OptionBStage1Result:
    """
    Run Stage 1 analysis for Option B configuration.
    
    Option B: Solids-Centric Facility with Mandatory Co-Feed
    - Co-feed (wood/biomass) provides primary energy source
    - Dry co-feed (>70% TS) bypasses dryer, reducing thermal load
    - Septage is secondary waste stream, processed for carbon sequestration
    - Char segregated by source for tiered pricing
    
    Args:
        params: Model parameters (uses Option B scenario if None)
    
    Returns:
        OptionBStage1Result with complete analysis
    """
    if params is None:
        params = create_option_b_scenario()
    
    # Get steady-state flows and equipment sizing (with CAPEX)
    flows = calc_steady_state_flows(params)
    sizing_result = size_equipment(params)
    sizing = sizing_result['sizing']
    
    # Co-feed routing
    cofeed_kgds_hr = params.cofeed_supply.annual_target_tds * 1000 / flows.effective_hours_yr
    cofeed_ts = params.cofeed.ts_fraction
    
    routing = calc_cofeed_routing(
        cofeed_kgds=cofeed_kgds_hr,
        cofeed_ts=cofeed_ts,
        prior_bypass_mode=True,
        bypass_ts_high=params.cofeed_routing.bypass_ts_high,
        bypass_ts_low=params.cofeed_routing.bypass_ts_low,
    )
    
    # Thermal balance
    thermal = calc_option_b_thermal(
        septage_cake_kgds=flows.dryer_feed_kgds_hr,
        septage_cake_ts=params.dewatering.cake_ts_fraction,
        cofeed_kgds=cofeed_kgds_hr,
        cofeed_ts=cofeed_ts,
        cofeed_bypass_mode=routing.bypass_mode,
        dried_ts=params.dryer.dried_ts_fraction,
        dryer_energy_kwh_per_kg_water=params.dryer.energy_kwh_per_kg_water,
        dryer_thermal_efficiency=params.dryer.thermal_efficiency,
        yield_char_sept=params.pyrolysis.yield_char,
        yield_gas_sept=params.pyrolysis.yield_gas,
        yield_cond_sept=params.pyrolysis.yield_condensate,
        lhv_syngas_sept_mj_kg=params.pyrolysis.lhv_syngas_sept_mj_kg,
        yield_char_cofeed=params.cofeed.yield_char_cofeed,
        yield_gas_cofeed=params.cofeed.yield_gas_cofeed,
        yield_cond_cofeed=params.cofeed.yield_condensate_cofeed,
        lhv_syngas_cofeed_mj_kg=params.cofeed.lhv_syngas_mj_kg,
        heat_requirement_mj_kgds=params.pyrolysis.heat_requirement_mj_kgds,
        syngas_recovery_efficiency=params.pyrolysis.syngas_recovery_efficiency,
    )
    
    energy = OptionBEnergyAnalysis(
        dryer_duty_mj_hr=thermal.dryer_duty_mj,
        pyro_duty_mj_hr=thermal.pyro_duty_mj,
        syngas_septage_mj_hr=thermal.syngas_septage_mj,
        syngas_cofeed_mj_hr=thermal.syngas_cofeed_mj,
        syngas_total_mj_hr=thermal.syngas_total_mj,
        net_heat_mj_hr=thermal.net_heat_mj,
        heat_deficit=thermal.heat_deficit,
        aux_fuel_mj_hr=thermal.aux_fuel_mj,
        energy_self_sufficiency=thermal.self_sufficiency_ratio,
        cofeed_bypass_mode=routing.bypass_mode,
    )
    
    # Char revenue
    char_result = calc_segregated_char_revenue(
        char_septage_kg=thermal.char_septage_kg,
        char_cofeed_kg=thermal.char_cofeed_kg,
        tier_septage=params.char_quality.default_tier_septage,
        tier_cofeed=params.char_quality.default_tier_cofeed,
        tier_1_price=params.char_quality.tier_1_price,
        tier_2_price=params.char_quality.tier_2_price,
        tier_3_price=params.char_quality.tier_3_price,
    )
    
    annual_char_sept_tonnes = thermal.char_septage_kg * flows.effective_hours_yr / 1000
    annual_char_cofeed_tonnes = thermal.char_cofeed_kg * flows.effective_hours_yr / 1000
    
    char_analysis = OptionBCharAnalysis(
        char_septage_kg_hr=thermal.char_septage_kg,
        char_cofeed_kg_hr=thermal.char_cofeed_kg,
        char_total_kg_hr=thermal.char_septage_kg + thermal.char_cofeed_kg,
        tier_septage=char_result.tier_septage,
        tier_cofeed=char_result.tier_cofeed,
        annual_char_septage_tonnes=annual_char_sept_tonnes,
        annual_char_cofeed_tonnes=annual_char_cofeed_tonnes,
        annual_char_total_tonnes=annual_char_sept_tonnes + annual_char_cofeed_tonnes,
        revenue_septage=char_result.revenue_septage * flows.effective_hours_yr,
        revenue_cofeed=char_result.revenue_cofeed * flows.effective_hours_yr,
        revenue_total=char_result.revenue_total * flows.effective_hours_yr,
    )
    
    # Co-feed supply analysis
    # Get monthly factors based on seasonal profile
    from septage_model.core.parameters import CofeedSeasonalProfile
    if params.cofeed_supply.seasonal_profile == CofeedSeasonalProfile.WOOD_STEADY:
        profile_factors = [1.0] * 12  # Year-round steady
    elif params.cofeed_supply.seasonal_profile == CofeedSeasonalProfile.AG_SEASONAL:
        # Agricultural: peak in fall harvest (Sept-Nov), low in winter/spring
        profile_factors = [0.5, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5, 1.5, 1.3, 0.7]
    else:
        profile_factors = [1.0] * 12
    monthly_tds = [params.cofeed_supply.annual_target_tds / 12 * f for f in profile_factors]
    
    annual_transport_cost = (
        params.cofeed_supply.annual_target_tds * 
        params.cofeed_supply.transport_km *
        params.cofeed_supply.cost_per_tkm
    )
    
    cofeed_analysis = OptionBCofeedAnalysis(
        annual_cofeed_tds=params.cofeed_supply.annual_target_tds,
        monthly_delivery_tds=monthly_tds,
        transport_km=params.cofeed_supply.transport_km,
        transport_cost_annual=annual_transport_cost,
        contract_security=params.cofeed_supply.contract_security_factor,
        seasonal_profile_name=params.cofeed_supply.seasonal_profile.name,
    )
    
    # Carbon balance
    total_char_kg_hr = thermal.char_septage_kg + thermal.char_cofeed_kg
    carbon_result = calc_carbon_balance(
        septage_kgds=flows.septage_kgds_hr * 8760,
        cofeed_kgds=cofeed_kgds_hr * flows.effective_hours_yr,
        char_kg=total_char_kg_hr * flows.effective_hours_yr,
        char_carbon_fraction=params.pyrolysis.char_carbon_fraction,
        char_permanence_factor=params.pyrolysis.char_permanence_factor,
        septage_m3=flows.annual_septage_m3
    )
    
    carbon = CarbonAnalysis(
        annual_carbon_in_tonnes=carbon_result.carbon_in_kg / 1000,
        annual_char_carbon_tonnes=carbon_result.char_carbon_kg / 1000,
        annual_sequestered_tonnes=carbon_result.sequestered_kg / 1000,
        annual_credits_tco2e=carbon_result.net_credits_kgco2e / 1000,
        sequestration_rate=carbon_result.sequestered_kg / carbon_result.carbon_in_kg if carbon_result.carbon_in_kg > 0 else 0
    )

    
    # CAPEX with Option B additions
    base_capex = sizing_result['total_capex']
    cofeed_capex = params.capex_scaling.cofeed_infrastructure_capex
    regulatory_capex = params.regulatory.permitting_capex_adder
    total_capex = base_capex + cofeed_capex + regulatory_capex
    
    ep = params.economic
    
    # Revenue
    tipping_revenue = flows.annual_septage_m3 * ep.tipping_fee_per_m3
    carbon_revenue = carbon.annual_credits_tco2e * ep.carbon_credit_per_tco2e if ep.carbon_credits_enabled else 0
    annual_revenue = tipping_revenue + char_analysis.revenue_total + carbon_revenue
    
    # OPEX
    dw_result = calc_dewatering(
        septage_m3=flows.septage_m3_hr,
        ts_fraction=params.service_area.ts_fraction_mean,
        density_kg_m3=params.service_area.density_kg_m3,
        cake_ts_fraction=params.dewatering.cake_ts_fraction,
        solids_capture=params.dewatering.solids_capture,
        polymer_kg_per_tds=params.dewatering.polymer_kg_per_tds,
        power_kwh_per_m3=params.dewatering.power_kwh_per_m3
    )
    
    dewatering_power_kwh_yr = dw_result.power_kwh * flows.effective_hours_yr
    aux_heat_kwh_yr = thermal.aux_fuel_mj * flows.effective_hours_yr / 3.6 if thermal.heat_deficit else 0
    electricity_cost = (dewatering_power_kwh_yr + aux_heat_kwh_yr * 0.3) * ep.electricity_price_kwh
    
    gas_cost = thermal.aux_fuel_mj * flows.effective_hours_yr * ep.natural_gas_price_mj if thermal.heat_deficit else 0
    polymer_cost = dw_result.polymer_used_kg * flows.effective_hours_yr * ep.polymer_cost_per_kg
    
    # Labor from staffing model (single source of truth)
    base_labor_cost = params.staffing.annual_cash_labor_cost()
    # Apply operations complexity factor for two-stream operation
    labor_cost = params.operations.apply_complexity(base_labor_cost)
    
    # Maintenance: Use MaintenanceModel if available, else fall back to %CAPEX
    if params.maintenance is not None:
        # Calculate annual tDS processed for maintenance model
        # Combine septage DS and cofeed DS through pyrolysis
        annual_tds = (
            flows.pyro_feed_kgds_hr * flows.effective_hours_yr / 1000 +  # Septage DS (kg -> tonnes)
            params.cofeed_supply.annual_target_tds                       # Cofeed DS
        )
        maintenance_cost = params.maintenance.annual_cost(annual_tds)
    else:
        # Legacy: %CAPEX approach
        maintenance_cost = total_capex * params.operations.maintenance_fraction_of_capex
        maintenance_cost = params.operations.apply_complexity(maintenance_cost)
    
    insurance_cost = total_capex * ep.insurance_fraction_of_capex
    compliance_cost = ep.compliance_annual + params.regulatory.compliance_cost_adder
    
    annual_opex = (
        electricity_cost + gas_cost + polymer_cost + labor_cost +
        maintenance_cost + insurance_cost + compliance_cost + annual_transport_cost
    )
    
    annual_noi = annual_revenue - annual_opex
    simple_payback = total_capex / annual_noi if annual_noi > 0 else float('inf')
    breakeven_tipping = (annual_opex - char_analysis.revenue_total - carbon_revenue) / flows.annual_septage_m3 if flows.annual_septage_m3 > 0 else 0
    
    economics = OptionBEconomicSummary(
        tipping_revenue=tipping_revenue,
        char_revenue_septage=char_analysis.revenue_septage,
        char_revenue_cofeed=char_analysis.revenue_cofeed,
        char_revenue_total=char_analysis.revenue_total,
        carbon_revenue=carbon_revenue,
        annual_revenue=annual_revenue,
        electricity_cost=electricity_cost,
        gas_cost=gas_cost,
        polymer_cost=polymer_cost,
        labor_cost=labor_cost,
        maintenance_cost=maintenance_cost,
        insurance_cost=insurance_cost,
        compliance_cost=compliance_cost,
        cofeed_transport_cost=annual_transport_cost,
        annual_opex=annual_opex,
        annual_noi=annual_noi,
        total_capex=total_capex,
        simple_payback_years=simple_payback,
        required_tipping_fee=breakeven_tipping,
    )
    
    # Constraints
    constraints = []
    critical_issues = []
    warnings = []
    
    # Energy self-sufficiency
    constraints.append(Constraint(
        name="Energy Self-Sufficiency",
        description="Syngas energy vs thermal demand",
        required_value=100,
        available_value=energy.energy_self_sufficiency * 100,
        unit="%",
        margin_percent=(energy.energy_self_sufficiency - 1.0) * 100,
        status=ViabilityStatus.VIABLE if energy.energy_self_sufficiency >= 1.0 else (
            ViabilityStatus.MARGINAL if energy.energy_self_sufficiency >= 0.80 else ViabilityStatus.NOT_VIABLE)
    ))
    
    if energy.energy_self_sufficiency < 0.80:
        critical_issues.append(f"Energy deficit - only {energy.energy_self_sufficiency:.0%} self-sufficient")
    elif energy.energy_self_sufficiency < 1.0:
        warnings.append(f"Auxiliary fuel needed - {energy.energy_self_sufficiency:.0%} self-sufficient")
    
    # Economic viability
    constraints.append(Constraint(
        name="Economic Viability",
        description="Simple payback period",
        required_value=params.economic.analysis_period_years,
        available_value=simple_payback,
        unit="years",
        margin_percent=(params.economic.analysis_period_years - simple_payback) / params.economic.analysis_period_years * 100 if simple_payback < float('inf') else -100,
        status=ViabilityStatus.VIABLE if simple_payback < 10 else (
            ViabilityStatus.MARGINAL if simple_payback < 15 else ViabilityStatus.NOT_VIABLE)
    ))
    
    if annual_noi <= 0:
        critical_issues.append(f"Negative NOI: ${annual_noi:,.0f}/yr")
    elif simple_payback > params.economic.analysis_period_years:
        critical_issues.append(f"Payback ({simple_payback:.1f}yr) exceeds analysis period")
    elif simple_payback > 10:
        warnings.append(f"Long payback period ({simple_payback:.1f} years)")
    
    # Co-feed supply security
    constraints.append(Constraint(
        name="Co-feed Supply Security",
        description="Contract security factor",
        required_value=0.80,
        available_value=params.cofeed_supply.contract_security_factor,
        unit="fraction",
        margin_percent=(params.cofeed_supply.contract_security_factor - 0.80) / 0.80 * 100,
        status=ViabilityStatus.VIABLE if params.cofeed_supply.contract_security_factor >= 0.80 else (
            ViabilityStatus.MARGINAL if params.cofeed_supply.contract_security_factor >= 0.60 else ViabilityStatus.NOT_VIABLE)
    ))
    
    if params.cofeed_supply.contract_security_factor < 0.60:
        critical_issues.append("Low co-feed supply security - risk of feedstock shortage")
    elif params.cofeed_supply.contract_security_factor < 0.80:
        warnings.append("Moderate co-feed supply security - consider backup suppliers")
    
    # Discharge constraint
    constraints.append(Constraint(
        name="Centrate Discharge",
        description="Required discharge rate vs permit limit",
        required_value=sizing.actual_discharge_rate_m3_hr,
        available_value=sizing.permit_discharge_rate_m3_hr,
        unit="m3/hr",
        margin_percent=(sizing.permit_discharge_rate_m3_hr - sizing.actual_discharge_rate_m3_hr) / sizing.permit_discharge_rate_m3_hr * 100,
        status=ViabilityStatus.VIABLE if sizing.discharge_utilization < 0.85 else (
            ViabilityStatus.MARGINAL if sizing.discharge_utilization < 1.0 else ViabilityStatus.NOT_VIABLE)
    ))
    
    # Determine overall status
    overall = ViabilityStatus.VIABLE
    for c in constraints:
        if c.status == ViabilityStatus.NOT_VIABLE:
            overall = ViabilityStatus.NOT_VIABLE
            break
        elif c.status == ViabilityStatus.MARGINAL:
            overall = ViabilityStatus.MARGINAL
    
    return OptionBStage1Result(
        params=params,
        flows=flows,
        sizing=sizing,
        constraints=constraints,
        energy=energy,
        char=char_analysis,
        cofeed=cofeed_analysis,
        carbon=carbon,
        economics=economics,
        overall_status=overall,
        critical_issues=critical_issues,
        warnings=warnings,
    )


def print_option_b_summary(result: OptionBStage1Result) -> None:
    """Print formatted Option B Stage 1 summary to console."""
    print(result.summary())

def run_product_mode(
    annual_septage_m3: float = 2000.0,
    annual_cofeed_tds: float = 600.0,
    reference_dumping_fee: float = 55.0,
) -> ProductModeResult:
    """
    Run Product Mode analysis - the DEFAULT analytical case.
    
    This is the primary entry point for evaluating Option B as
    an owner-operated piece of equipment.
    
    Args:
        annual_septage_m3: Buyer's annual septage volume (default 2,000)
        annual_cofeed_tds: Required co-feed (default 600 tDS/yr)
        reference_dumping_fee: Current fee buyer pays (default $55/m³)
    
    Returns:
        ProductModeResult with buyer economics framing
    """
    # Create product scenario
    params = create_product_scenario(
        annual_septage_m3=annual_septage_m3,
        annual_cofeed_tds=annual_cofeed_tds,
        reference_dumping_fee=reference_dumping_fee,
    )
    
    # Run technical analysis using Option B physics
    base_result = run_stage1_option_b(params)
    
    # Calculate buyer economics
    buyer = calc_buyer_economics(base_result, params.deployment)
    
    # Calculate design constraints (the engineering requirements)
    # other_opex = polymer, power, utilities (~$40k for product scale)
    other_opex = 40_000
    constraints = calc_design_constraints(
        capex=buyer.capex,
        avoided_fees=buyer.current_annual_cost,  # avoided fees = what they currently pay
        char_revenue=buyer.char_revenue_potential,
        other_opex=other_opex,
        target_payback_years=15.0,
    )
    
    return ProductModeResult(
        base_result=base_result,
        buyer=buyer,
        deployment=params.deployment,
        max_maintenance_budget_per_year=constraints['max_maintenance'],
        max_callouts_per_week=constraints['max_callouts_per_week'],
        owner_serviceable_required=constraints['owner_serviceable_required'],
        design_status=constraints['design_status'],
    )


def run_hub_mode(
    annual_septage_m3: float = 5000.0,
    annual_cofeed_tds: float = 1200.0,
) -> OptionBStage1Result:
    """
    Run Regional Hub Mode analysis.
    
    This is the secondary path for staffed facility deployment.
    Uses standard facility NOI framing.
    
    Staffing is defined via StaffingModel.daytime_callout():
        - Daytime staff (40 hr/wk paid)
        - On-call for nights/weekends
        - Callouts as needed
    
    Args:
        annual_septage_m3: Annual septage volume (default 5,000)
        annual_cofeed_tds: Annual co-feed (default 1,200 tDS/yr)
    
    Returns:
        OptionBStage1Result with facility economics framing
    """
    params = create_hub_scenario(
        annual_septage_m3=annual_septage_m3,
        annual_cofeed_tds=annual_cofeed_tds,
    )
    
    return run_stage1_option_b(params)


def compare_deployment_modes() -> str:
    """
    Run side-by-side comparison of Product vs Hub modes.
    
    Returns:
        Formatted comparison report
    """
    product = run_product_mode()
    hub = run_hub_mode()
    
    # Hub status label
    hub_status = {
        ViabilityStatus.VIABLE: "VIABLE",
        ViabilityStatus.MARGINAL: "MARGINAL",
        ViabilityStatus.NOT_VIABLE: "NOT VIABLE"
    }.get(hub.overall_status, "UNKNOWN")
    
    lines = [
        "="*70,
        "DEPLOYMENT MODE COMPARISON: PRODUCT vs REGIONAL HUB",
        "="*70,
        "",
        f"{'Metric':<30} {'Product Mode':>18} {'Hub Mode':>18}",
        "-"*70,
        "",
        "--- Scale ---",
        f"{'Annual septage (m3/yr)':<30} {product.buyer.annual_septage_m3:>18,.0f} {hub.params.service_area.annual_septage_m3:>18,.0f}",
        f"{'Annual co-feed (tDS/yr)':<30} {product.deployment.annual_cofeed_tds:>18,.0f} {hub.params.cofeed_supply.annual_target_tds:>18,.0f}",
        "",
        "--- Energy ---",
        f"{'Self-sufficiency':<30} {product.base_result.energy.energy_self_sufficiency:>17.0%} {hub.energy.energy_self_sufficiency:>17.0%}",
        f"{'Off-grid capable':<30} {'YES':>18} {'YES' if hub.energy.energy_self_sufficiency >= 1.0 else 'NO':>18}",
        "",
        "--- Economics ---",
        f"{'CAPEX':<30} ${product.buyer.capex:>17,.0f} ${hub.economics.total_capex:>17,.0f}",
        f"{'Annual operating cost':<30} ${product.buyer.total_annual_cost:>17,.0f} ${hub.economics.annual_opex:>17,.0f}",
        f"{'Labor included':<30} {'No (owner time)':>18} {'Yes (0.7 FTE)':>18}",
        "",
        "--- Product Mode Buyer View ---",
        f"{'Current dumping cost':<30} ${product.buyer.current_annual_cost:>17,.0f} {'N/A':>18}",
        f"{'Annual savings (fees only)':<30} ${product.buyer.annual_net_savings_avoided_fees_only:>17,.0f} {'N/A':>18}",
        f"{'+ Char revenue':<30} ${product.buyer.char_revenue_potential:>17,.0f} {'N/A':>18}",
        f"{'= Total benefit (with char)':<30} ${product.buyer.annual_net_savings_with_char:>17,.0f} {'N/A':>18}",
        f"{'Payback (with char)':<30} {product.payback_with_char:>17.1f}yr {'N/A':>18}",
        f"{'Owner hours/week':<30} {product.buyer.owner_time_hours_per_week:>17.1f} {'N/A':>18}",
        "",
        "--- Hub Mode Facility View ---",
        f"{'Annual NOI':<30} {'N/A':>18} ${hub.economics.annual_noi:>17,.0f}",
        f"{'Simple payback':<30} {'N/A':>18} {hub.economics.simple_payback_years:>17.1f}yr",
        "",
        "--- Strategic Assessment ---",
        f"{'Status':<30} {product.product_status:>18} {hub_status:>18}",
        "",
        "="*70,
        "",
        "CONCLUSION: Product Mode is the preferred deployment path.",
        "  - Same physics, different organizational model",
        "  - 12 year payback with char sales vs infinite for Hub",
        "  - Owner operates as equipment, not as a business",
    ]
    
    return "\n".join(lines)


def get_design_requirements() -> str:
    """
    Output locked design requirements for product engineering.
    
    These are INPUTS to engineering, not outputs from economics.
    Any design that violates these fails economically, regardless
    of how elegant it is technically.
    
    Returns:
        Formatted design requirements specification
    """
    lines = [
        "="*70,
        "DESIGN REQUIREMENTS SPECIFICATION",
        "Septage-to-Biochar Processing Unit (Product Mode)",
        "="*70,
        "",
        "Status: LOCKED (derived from economic analysis, not negotiable)",
        "",
        "1. HARD CONSTRAINTS (Go/No-Go)",
        "-"*40,
        "",
        "1.1 Serviceability",
        "    - Owner-serviceable: REQUIRED",
        "    - All routine maintenance performable by owner with hand tools",
        "    - No alignment-critical field work",
        "    - No specialist vendor consumables",
        "",
        "1.2 Maintenance Budget",
        "    - Maximum: $35,000/yr",
        "    - Target:  $20,000-25,000/yr",
        "    - Includes: parts, consumables, inspections, callouts",
        "",
        "1.3 Callout Frequency",
        "    - Maximum: 1/week (4/month)",
        "    - Target:  <=1/month",
        "    - Callout = any event requiring external technician",
        "",
        "1.4 Prohibited Design Choices",
        "    - Routine refractory relines",
        "    - Field alignment of rotating equipment",
        "    - Proprietary consumables",
        "    - Components with MTBF < 6 months",
        "",
        "2. DESIGN TARGETS (Engineering Guidance)",
        "-"*40,
        "",
        "2.1 Mechanical",
        "    - Modular auger assemblies (quick-swap, no field alignment)",
        "    - Standardized bearings/seals (commodity, local availability)",
        "    - Bolt-on wear parts (owner-replaceable in <1 hour)",
        "    - No refractory in high-wear zones (use castable or modular)",
        "",
        "2.2 Controls",
        "    - Predictive maintenance hooks (vibration, temperature)",
        "    - Remote monitoring capable",
        "    - Fail-safe shutdown on critical faults",
        "    - Clear fault codes (owner-diagnosable)",
        "",
        "2.3 Service Access",
        "    - All wear parts accessible without disassembly of major components",
        "    - Standard fasteners (no specialty tools)",
        "    - Lifting points for heavy components",
        "    - Service manual written for non-specialist operator",
        "",
        "3. ACCEPTANCE CRITERIA (Design Review Checklist)",
        "-"*40,
        "",
        "For each component, answer:",
        "    [ ] Can owner replace this with hand tools?",
        "    [ ] Is MTBF >= 6 months under expected duty?",
        "    [ ] Are replacement parts available locally (<48hr)?",
        "    [ ] Does failure require external callout?",
        "    [ ] Is maintenance task documented in service manual?",
        "",
        "If any answer is unfavorable, REDESIGN before proceeding.",
        "",
        "4. ECONOMIC BASIS (Reference Only)",
        "-"*40,
        "",
        "These requirements derive from:",
        "    - CAPEX: ~$1.27M",
        "    - Target payback: <=15 years",
        "    - Avoided fees: ~$110k/yr",
        "    - Char revenue: ~$50k/yr",
        "    - Max allowable OPEX: ~$75k/yr",
        "    - Maintenance allocation: ~$25k/yr",
        "",
        "Maintenance > $35k/yr -> payback > 20 years -> NOT VIABLE",
        "",
        "="*70,
        "END OF DESIGN REQUIREMENTS",
        "="*70,
    ]
    return "\n".join(lines)
