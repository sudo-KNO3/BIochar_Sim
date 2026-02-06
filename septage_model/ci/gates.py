"""
CI Design Gates - Automated product viability checks.

These gates encode the frozen engineering constraints.
Any change that breaks viability fails CI immediately.

Frozen constraints (do not modify without explicit decision):
    - max_maintenance_budget_per_year = 35_000
    - max_callouts_per_week = 1.0
    - owner_serviceable_required = True
    - max_payback_years = 15.0

Gate Philosophy:
    - Every gate returns structured data, not bare assertions
    - Failed gates include actionable remediation guidance
    - Gates are design coaches, not just blockers
"""

from dataclasses import dataclass
from typing import List, Optional


# =============================================================================
# Frozen Constants (from locked economic analysis)
# =============================================================================

MAX_MAINTENANCE_BUDGET = 35_000  # $/year
MAX_CALLOUTS_PER_WEEK = 1.0
MAX_PAYBACK_YEARS = 15.0
OWNER_SERVICEABLE_REQUIRED = True


# =============================================================================
# Gate Result Structure
# =============================================================================

@dataclass
class GateResult:
    """
    Result of a single design gate check.
    
    Every gate returns structured data, not bare assertions.
    Failed gates include actionable remediation guidance.
    """
    name: str
    passed: bool
    value: float
    threshold: float
    remediation: Optional[str] = None
    
    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        s = f"[{status}] {self.name}: {self.value:,.0f} (threshold: {self.threshold:,.0f})"
        if not self.passed and self.remediation:
            s += f"\n       Remediation: {self.remediation}"
        return s


@dataclass  
class GateReport:
    """Aggregated results from all design gates."""
    gates: List[GateResult]
    
    @property
    def all_passed(self) -> bool:
        return all(g.passed for g in self.gates)
    
    @property
    def failed_gates(self) -> List[GateResult]:
        return [g for g in self.gates if not g.passed]
    
    @property
    def passed_gates(self) -> List[GateResult]:
        return [g for g in self.gates if g.passed]
    
    def __str__(self) -> str:
        lines = ["=" * 60, "DESIGN GATE REPORT", "=" * 60, ""]
        for g in self.gates:
            lines.append(str(g))
        lines.append("")
        if self.all_passed:
            lines.append("RESULT: ALL GATES PASSED")
        else:
            lines.append(f"RESULT: {len(self.failed_gates)} GATE(S) FAILED")
        lines.append("=" * 60)
        return "\n".join(lines)


# =============================================================================
# Individual Gates
# =============================================================================

def maintenance_budget_gate(result) -> GateResult:
    """
    Gate: Annual maintenance cost must be <= $35,000.
    
    This is the primary governing constraint for product viability.
    Maintenance budget directly ties engineering decisions to economics.
    
    Args:
        result: ProductModeResult or OptionBStage1Result with economics
    
    Returns:
        GateResult with pass/fail and remediation if failed
    """
    threshold = MAX_MAINTENANCE_BUDGET
    
    # Extract maintenance cost from result
    # Handle both ProductModeResult and OptionBStage1Result
    if hasattr(result, 'base_result'):
        # ProductModeResult
        value = result.base_result.economics.maintenance_cost
    else:
        # OptionBStage1Result directly
        value = result.economics.maintenance_cost
    
    # Sanity check: maintenance should never be negative
    # Guards against future refactors accidentally double-subtracting
    if value < 0:
        raise ValueError(f"Maintenance cost is negative ({value}). Check calculation logic.")
    
    passed = value <= threshold
    
    remediation = None
    if not passed:
        remediation = (
            "Annual maintenance cost exceeds viable product envelope. "
            "Reduce callout frequency or planned maintenance burden. "
            "Focus on owner-serviceable wear parts (augers, bearings, seals), "
            "eliminate contractor-only maintenance tasks, "
            "and reduce MTTR through modularization. "
            "Do NOT attempt to fix via revenue assumptions."
        )
    
    return GateResult(
        name="Maintenance Budget",
        passed=passed,
        value=value,
        threshold=threshold,
        remediation=remediation
    )


def payback_gate(result) -> GateResult:
    """
    Gate: Payback (with char) must be <= 15 years.
    
    Args:
        result: ProductModeResult or OptionBStage1Result
    
    Returns:
        GateResult with pass/fail and remediation if failed
    """
    threshold = MAX_PAYBACK_YEARS
    
    if hasattr(result, 'buyer'):
        # ProductModeResult
        value = result.buyer.payback_with_char_revenue
    else:
        # OptionBStage1Result
        value = result.economics.simple_payback_years
    
    passed = value <= threshold
    
    remediation = None
    if not passed:
        remediation = (
            "Payback exceeds viable threshold. "
            "Focus on reducing maintenance cost, not increasing revenue assumptions. "
            "Check MaintenanceModel parameters and callout frequency. "
            "Verify owner-serviceable design is maintained."
        )
    
    return GateResult(
        name="Payback Period",
        passed=passed,
        value=value,
        threshold=threshold,
        remediation=remediation
    )


def callout_frequency_gate(result) -> GateResult:
    """
    Gate: Callouts must be <= 1/week.
    
    This requires MaintenanceModel to be attached to params.
    
    Args:
        result: ProductModeResult with params containing MaintenanceModel
    
    Returns:
        GateResult with pass/fail and remediation if failed
    """
    threshold = MAX_CALLOUTS_PER_WEEK
    
    # Extract callout frequency from MaintenanceModel
    if hasattr(result, 'base_result'):
        params = result.base_result.params
    else:
        params = result.params
    
    if params.maintenance is not None:
        callouts_per_year = params.maintenance.callouts_per_year
        value = callouts_per_year / 52.0  # Convert to per-week
    else:
        # Legacy %CAPEX mode - estimate from typical values
        value = 0.25  # Assume compliant if no explicit model
    
    passed = value <= threshold
    
    remediation = None
    if not passed:
        remediation = (
            "Callout frequency exceeds viable threshold. "
            "Improve MTBF through better component selection, "
            "add redundancy for critical subsystems, "
            "implement predictive maintenance (vibration, temp monitoring), "
            "and ensure all routine tasks are owner-serviceable."
        )
    
    return GateResult(
        name="Callout Frequency",
        passed=passed,
        value=value,
        threshold=threshold,
        remediation=remediation
    )


def physics_sanity_gate(result) -> GateResult:
    """
    Gate: System must be energy-positive (self-sufficient).
    
    Args:
        result: ProductModeResult or OptionBStage1Result
    
    Returns:
        GateResult with pass/fail
    """
    threshold = 1.0  # 100% self-sufficiency
    
    if hasattr(result, 'base_result'):
        value = result.base_result.energy.energy_self_sufficiency
    else:
        value = result.energy.energy_self_sufficiency
    
    passed = value >= threshold
    
    remediation = None
    if not passed:
        remediation = (
            "System is not energy self-sufficient. "
            "Check co-feed ratio, dryer efficiency, and syngas recovery. "
            "Verify cofeed_bypass_mode is correctly configured. "
            "This is a physics failure, not an economic one."
        )
    
    return GateResult(
        name="Energy Self-Sufficiency",
        passed=passed,
        value=value,
        threshold=threshold,
        remediation=remediation
    )


# =============================================================================
# Gate Runner
# =============================================================================

def run_design_gates(result, fmea=None) -> GateReport:
    """
    Run all design gates against a result.
    
    Args:
        result: ProductModeResult from run_product_mode()
        fmea: Optional list of FailureMode (for FMEA gate - future)
    
    Returns:
        GateReport with all results
    """
    gates = [
        maintenance_budget_gate(result),
        payback_gate(result),
        callout_frequency_gate(result),
        physics_sanity_gate(result),
        # Future gates:
        # fmea_criticality_gate(fmea),
    ]
    
    return GateReport(gates=gates)


def check_gates_or_fail(result, fmea=None) -> None:
    """
    Run all gates and raise AssertionError if any fail.
    
    Use this in CI tests for hard failure behavior.
    
    Args:
        result: ProductModeResult from run_product_mode()
        fmea: Optional list of FailureMode
    
    Raises:
        AssertionError: If any gate fails, with remediation guidance
    """
    report = run_design_gates(result, fmea)
    
    if not report.all_passed:
        msgs = []
        for g in report.failed_gates:
            msgs.append(
                f"{g.name}: {g.value:,.0f} > {g.threshold:,.0f}\n"
                f"Remediation: {g.remediation}"
            )
        raise AssertionError(
            f"DESIGN GATES FAILED\n\n" + "\n\n".join(msgs)
        )


# =============================================================================
# Design-Grade Physics Gates (DRL-4+ requirements)
# =============================================================================

def conversion_gate(
    conversion_result,  # ConversionResult from pyrolysis_kinetics
) -> GateResult:
    """
    Gate: Pyrolysis conversion must meet minimum threshold.
    
    If X(τ,T) < X_min, the reactor cannot achieve the required conversion
    regardless of other design parameters.
    
    Args:
        conversion_result: ConversionResult from calc_conversion()
    
    Returns:
        GateResult with conversion feasibility
    """
    value = conversion_result.X * 100  # As percentage
    threshold = conversion_result.X_min * 100
    passed = conversion_result.feasible
    
    remediation = None
    if not passed:
        deficit = threshold - value
        remediation = (
            f"Conversion deficit: {deficit:.1f}%. "
            f"Options: (1) Increase residence time (reduce throughput or increase holdup), "
            f"(2) Raise reactor temperature, "
            f"(3) Use different reactor type with better RTD."
        )
    
    return GateResult(
        name=f"Conversion ({conversion_result.stream_id})",
        passed=passed,
        value=value,
        threshold=threshold,
        remediation=remediation,
    )


def thermal_feasibility_gate(
    thermal_result,  # ThermalFeasibilityResult from thermal_feasibility
) -> GateResult:
    """
    Gate: Heat transfer capacity must exceed heat requirement.
    
    If Q_req > Q_max, the reactor cannot physically supply the required
    heat rate. This is the hardest physical constraint.
    
    Args:
        thermal_result: ThermalFeasibilityResult from check_thermal_feasibility()
    
    Returns:
        GateResult with thermal feasibility
    """
    value = thermal_result.Q_req_kw
    threshold = thermal_result.Q_max_kw
    passed = thermal_result.feasible
    
    remediation = None
    if not passed:
        deficit = thermal_result.deficit_kw
        remediation = (
            f"Heat deficit: {deficit:.1f} kW. "
            f"Options: (1) Reduce throughput to {thermal_result.Q_max_kw / thermal_result.heat_requirement.heat_intensity_kw_per_kg:.3f} kg/s, "
            f"(2) Increase heat transfer area, "
            f"(3) Improve U (agitation, wall contact), "
            f"(4) Raise wall temperature."
        )
    
    return GateResult(
        name="Thermal Feasibility",
        passed=passed,
        value=value,
        threshold=threshold,
        remediation=remediation,
    )


def kinetics_validation_gate(
    kinetics_list,  # List[KineticsParams]
    claimed_drl: int,
) -> GateResult:
    """
    Gate: DRL-4+ claims require validated kinetics.
    
    This gate enforces scientific honesty. Literature-based kinetics
    are acceptable for screening (DRL-3) but not for design claims.
    
    Args:
        kinetics_list: List of KineticsParams for all streams
        claimed_drl: DRL level being claimed for the design
    
    Returns:
        GateResult blocking DRL-4+ if kinetics are unvalidated
    """
    # DRL-3 or below: no validation required
    if claimed_drl <= 3:
        return GateResult(
            name="Kinetics Validation",
            passed=True,
            value=claimed_drl,
            threshold=3,
            remediation=None,
        )
    
    # Check all kinetics
    unvalidated = [k for k in kinetics_list if not k.validated]
    passed = len(unvalidated) == 0
    
    remediation = None
    if not passed:
        streams = ", ".join(k.stream_id for k in unvalidated)
        remediation = (
            f"DRL-4+ claim blocked: kinetic parameter sets for [{streams}] "
            f"are literature-based and unvalidated. "
            f"Provide lab or vendor kinetic data and mark validated=True."
        )
    
    return GateResult(
        name="Kinetics Validation (DRL)",
        passed=passed,
        value=len(unvalidated),
        threshold=0,
        remediation=remediation,
    )


def overnight_mode_validation_gate(
    overnight_params,  # OvernightModeParams
    claimed_drl: int,
) -> GateResult:
    """
    Gate: DRL-4+ claims require validated overnight mode parameters.
    
    This gate enforces vendor-validated operational assumptions.
    Unvalidated overnight assumptions are acceptable for screening (DRL-3)
    but not for design claims or vendor engagement.
    
    Validation rule:
        - ≥2 consistent vendor responses required for VALIDATED status
        - 1 response = PARTIAL (informative, but blocks DRL-4)
        - 0 responses = UNKNOWN (blocks DRL-4)
    
    Consistency rules (per VendorValidationPolicy):
        - overnight_mode: exact enum match required
        - restart_time: bucketed comparison (<1hr, 1-4hr, >4hr)
        - thermal_hold: boolean match required
    
    Args:
        overnight_params: OvernightModeParams from validate_overnight_responses()
        claimed_drl: DRL level being claimed for the design
    
    Returns:
        GateResult blocking DRL-4+ if overnight mode is unvalidated
    """
    from septage_model.core.parameters import OvernightModeStatus
    
    # DRL-3 or below: no validation required (emit warning, allow screening)
    if claimed_drl <= 3:
        # Still provide information about unvalidated assumptions
        unvalidated = overnight_params.get_unvalidated_assumptions()
        remediation = None
        if unvalidated:
            remediation = (
                f"DRL-3 warning: Unvalidated overnight assumptions will be listed. "
                f"Assumptions: {'; '.join(unvalidated)}"
            )
        return GateResult(
            name="Overnight Mode Validation",
            passed=True,
            value=claimed_drl,
            threshold=3,
            remediation=remediation,
        )
    
    # DRL-4+: HARD BLOCK unless VALIDATED
    status = overnight_params.status
    passed = status == OvernightModeStatus.VALIDATED
    
    remediation = None
    if not passed:
        vendor_count = overnight_params.vendor_count
        min_required = overnight_params.policy.min_vendors
        mode = overnight_params.mode.value
        
        if status == OvernightModeStatus.UNKNOWN:
            remediation = (
                f"DRL-4+ claim blocked: overnight_mode is UNKNOWN. "
                f"No vendor responses received. "
                f"Await ≥{min_required} consistent vendor responses to lift block. "
                f"Parse responses via VendorOvernightData → validate_overnight_responses(policy)."
            )
        elif status == OvernightModeStatus.PARTIAL:
            remediation = (
                f"DRL-4+ claim blocked: overnight_mode is PARTIAL. "
                f"Received {vendor_count} vendor response(s), require ≥{min_required} consistent. "
                f"Current mode assumption: {mode}. "
                f"Await additional consistent vendor responses to lift block."
            )
    
    return GateResult(
        name="Overnight Mode Validation (DRL)",
        passed=passed,
        value=overnight_params.vendor_count,
        threshold=overnight_params.policy.min_vendors,
        remediation=remediation,
    )


def source_refs_gate(
    kinetics_list,  # List[KineticsParams]
) -> GateResult:
    """
    Gate: Unvalidated kinetics must have literature references.
    
    Every unvalidated physics parameter must reference at least one
    ref_id from references.json. This enables audit and traceability.
    
    Args:
        kinetics_list: List of KineticsParams for all streams
    
    Returns:
        GateResult failing if unreferenced assumptions exist
    """
    # Find any unvalidated kinetics without source_refs
    unreferenced = [
        k for k in kinetics_list
        if not k.validated and len(k.source_refs) == 0
    ]
    
    passed = len(unreferenced) == 0
    
    remediation = None
    if not passed:
        streams = ", ".join(k.stream_id for k in unreferenced)
        remediation = (
            f"Unreferenced assumptions for [{streams}]. "
            f"Add source_refs pointing to ref_ids in references.json."
        )
    
    return GateResult(
        name="Literature References",
        passed=passed,
        value=len(unreferenced),
        threshold=0,
        remediation=remediation,
    )


def run_design_physics_gates(
    conversion_results: list,  # List[ConversionResult]
    thermal_result,  # ThermalFeasibilityResult
    kinetics_list: list,  # List[KineticsParams]
    claimed_drl: int = 4,
    overnight_params=None,  # Optional[OvernightModeParams]
) -> GateReport:
    """
    Run all design-grade physics gates.
    
    These gates are only relevant when design_mode=True.
    
    Args:
        conversion_results: List of ConversionResult (one per stream)
        thermal_result: ThermalFeasibilityResult
        kinetics_list: List of KineticsParams
        claimed_drl: DRL level being claimed
        overnight_params: OvernightModeParams for vendor validation gate
    
    Returns:
        GateReport with all design physics gates
    """
    gates = []
    
    # Conversion gates (one per stream)
    for conv in conversion_results:
        gates.append(conversion_gate(conv))
    
    # Thermal feasibility
    gates.append(thermal_feasibility_gate(thermal_result))
    
    # Governance gates
    gates.append(kinetics_validation_gate(kinetics_list, claimed_drl))
    gates.append(source_refs_gate(kinetics_list))
    
    # Vendor validation gates (DRL-4+ only)
    if overnight_params is not None:
        gates.append(overnight_mode_validation_gate(overnight_params, claimed_drl))
    
    return GateReport(gates=gates)


# ==============================================================================
# OPERATING ENVELOPE GATE
# ==============================================================================
# Validates that the proposed operating point falls within the allowable
# operating region defined by OperatingEnvelope.

def operating_envelope_gate(
    throughput_kgds_hr: float,
    wall_temperature_c: float,
    feed_ts: float,
    residence_time_s: float = 0.0,
    reactor_temperature_c: float = 0.0,
    overnight_state: 'OvernightState | None' = None,
    overnight_temp_c: float | None = None,
    syngas_self_sufficiency: float = 1.0,
    aux_fuel_fraction: float = 0.0,
    envelope: 'OperatingEnvelope | None' = None,
) -> GateResult:
    """
    Gate: Operating point must fall within the operating envelope.
    
    This gate wraps check_operating_envelope() into the GateResult pattern
    for CI integration. Only hard violations (physics constraints) cause
    failure; soft violations generate warnings.
    
    Args:
        throughput_kgds_hr: Dry solids throughput (kg DS/hr)
        wall_temperature_c: Reactor wall temperature (°C)
        feed_ts: Feed total solids fraction (0-1)
        residence_time_s: Residence time (s), 0 to skip
        reactor_temperature_c: Reactor temperature (°C), 0 to skip
        overnight_state: Planned overnight state
        overnight_temp_c: Overnight hold temperature (°C)
        syngas_self_sufficiency: Syngas/heat demand ratio
        aux_fuel_fraction: External fuel fraction
        envelope: Operating envelope (default: OPERATING_ENVELOPE_DEFAULT)
        
    Returns:
        GateResult with pass/fail and remediation
    """
    from ..core.thermal_feasibility import check_operating_envelope
    from ..core.parameters import OperatingEnvelope, OPERATING_ENVELOPE_DEFAULT
    
    env = envelope or OPERATING_ENVELOPE_DEFAULT
    
    result = check_operating_envelope(
        throughput_kgds_hr=throughput_kgds_hr,
        wall_temperature_c=wall_temperature_c,
        feed_ts=feed_ts,
        residence_time_s=residence_time_s,
        reactor_temperature_c=reactor_temperature_c,
        overnight_state=overnight_state,
        overnight_temp_c=overnight_temp_c,
        syngas_self_sufficiency=syngas_self_sufficiency,
        aux_fuel_fraction=aux_fuel_fraction,
        envelope=env,
    )
    
    # Build remediation string from violations
    remediation = None
    if result.violations:
        violation_strs = [str(v) for v in result.violations]
        remediation = "Envelope violations:\n" + "\n".join(f"  - {s}" for s in violation_strs)
    
    # Value = number of hard violations (0 = pass)
    hard_count = len(result.hard_violations)
    
    return GateResult(
        name="Operating Envelope",
        passed=result.within_envelope,
        value=float(hard_count),
        threshold=0.0,
        remediation=remediation,
    )


# ==============================================================================
# PATHWAY VIABILITY GATES
# ==============================================================================
# These gates validate that value-add pathways have sufficient feedstock volume
# and supporting infrastructure to be economically viable.

# Pathway viability thresholds (frozen)
MIN_CENTRATE_M3_FOR_NUTRIENT_RECOVERY: float = 500.0  # m³/yr minimum for struvite/ammonia
MIN_P_CONC_MG_L: float = 50.0  # mg/L PO4-P for struvite viability
MIN_SYNGAS_EXCESS_MJ_FOR_CHP: float = 50_000.0  # MJ/yr excess for CHP investment
MIN_CHP_CAPACITY_KW: float = 10.0  # kW minimum for grid interconnect
MIN_CHAR_KG_FOR_ACTIVATION: float = 1_000.0  # kg/yr char for activation unit
MIN_STEAM_KG_FOR_ACTIVATION: float = 500.0  # kg/yr steam availability


def nutrient_recovery_viability_gate(
    centrate_m3_annual: float,
    p_conc_mg_l: float,
    has_discharge_permit: bool = True,
) -> GateResult:
    """
    Check if centrate volume and nutrient concentration support struvite recovery.
    
    Struvite crystallization requires:
    - Sufficient annual centrate volume (≥500 m³/yr)
    - Adequate phosphorus concentration (≥50 mg/L PO4-P)
    - Alternative to discharge permit (cost avoidance driver)
    
    Args:
        centrate_m3_annual: Annual centrate volume in m³
        p_conc_mg_l: Phosphorus concentration in mg/L as PO4-P
        has_discharge_permit: Whether facility has existing discharge permit
        
    Returns:
        GateResult indicating viability
    """
    volume_ok = centrate_m3_annual >= MIN_CENTRATE_M3_FOR_NUTRIENT_RECOVERY
    conc_ok = p_conc_mg_l >= MIN_P_CONC_MG_L
    
    passed = volume_ok and conc_ok
    
    # Composite score: volume fraction × concentration fraction
    volume_score = min(centrate_m3_annual / MIN_CENTRATE_M3_FOR_NUTRIENT_RECOVERY, 1.0)
    conc_score = min(p_conc_mg_l / MIN_P_CONC_MG_L, 1.0)
    value = volume_score * conc_score
    
    remediation = None
    if not passed:
        issues = []
        if not volume_ok:
            issues.append(
                f"Centrate volume {centrate_m3_annual:.0f} m³/yr < {MIN_CENTRATE_M3_FOR_NUTRIENT_RECOVERY:.0f} m³/yr threshold"
            )
        if not conc_ok:
            issues.append(
                f"P concentration {p_conc_mg_l:.1f} mg/L < {MIN_P_CONC_MG_L:.0f} mg/L threshold"
            )
        remediation = (
            f"Nutrient recovery not viable: {'; '.join(issues)}. "
            "Consider co-processing external centrate or targeting ammonia stripping only."
        )
    elif not has_discharge_permit:
        # Passed but extra driver noted
        remediation = (
            "No discharge permit - nutrient recovery provides critical permit avoidance. "
            "Prioritize struvite pathway in scenario analysis."
        )
    
    return GateResult(
        name="Nutrient Recovery Viability",
        passed=passed,
        value=value,
        threshold=1.0,  # Need both volume and concentration at 100%
        remediation=remediation,
    )


def chp_grid_viability_gate(
    syngas_excess_mj_annual: float,
    electrical_efficiency: float = 0.30,
    grid_interconnect_available: bool = True,
) -> GateResult:
    """
    Check if excess syngas supports combined heat and power (CHP) investment.
    
    CHP viability requires:
    - Sufficient excess syngas (≥50,000 MJ/yr above process needs)
    - Resulting capacity ≥10 kW for utility interconnect
    - Grid interconnect feasibility (or behind-the-meter use case)
    
    Args:
        syngas_excess_mj_annual: Excess syngas energy in MJ/yr
        electrical_efficiency: CHP electrical efficiency (default 0.30)
        grid_interconnect_available: Whether grid interconnect is feasible
        
    Returns:
        GateResult indicating viability
    """
    # Calculate potential electrical capacity
    # MJ/yr → kW: divide by (365 * 24 * 3.6) for hours and MJ→kWh
    hours_per_year = 365 * 24 * 0.85  # 85% availability
    capacity_kw = (syngas_excess_mj_annual * electrical_efficiency) / (hours_per_year * 3.6)
    
    energy_ok = syngas_excess_mj_annual >= MIN_SYNGAS_EXCESS_MJ_FOR_CHP
    capacity_ok = capacity_kw >= MIN_CHP_CAPACITY_KW
    
    passed = energy_ok and capacity_ok and grid_interconnect_available
    
    remediation = None
    if not passed:
        issues = []
        if not energy_ok:
            issues.append(
                f"Excess syngas {syngas_excess_mj_annual:.0f} MJ/yr < {MIN_SYNGAS_EXCESS_MJ_FOR_CHP:.0f} MJ/yr threshold"
            )
        if not capacity_ok:
            issues.append(
                f"CHP capacity {capacity_kw:.1f} kW < {MIN_CHP_CAPACITY_KW:.0f} kW minimum for interconnect"
            )
        if not grid_interconnect_available:
            issues.append("No grid interconnect available at site")
        
        remediation = (
            f"CHP not viable: {'; '.join(issues)}. "
            "Consider heat-only recovery (boiler/process heat) or process intensification "
            "to increase excess syngas availability."
        )
    
    return GateResult(
        name="CHP Grid Viability",
        passed=passed,
        value=capacity_kw,
        threshold=MIN_CHP_CAPACITY_KW,
        remediation=remediation,
    )


def char_activation_viability_gate(
    char_kg_annual: float,
    steam_available_kg_annual: float,
    steam_ratio: float = 2.5,  # kg steam per kg char
) -> GateResult:
    """
    Check if char production and steam availability support activation unit.
    
    Char activation viability requires:
    - Sufficient char throughput (≥1,000 kg/yr)
    - Adequate steam availability (≥500 kg/yr at 2.5:1 ratio)
    
    Args:
        char_kg_annual: Annual char production in kg
        steam_available_kg_annual: Available steam in kg/yr
        steam_ratio: Steam to char ratio for activation (default 2.5)
        
    Returns:
        GateResult indicating viability
    """
    char_ok = char_kg_annual >= MIN_CHAR_KG_FOR_ACTIVATION
    steam_needed = char_kg_annual * steam_ratio
    steam_ok = steam_available_kg_annual >= min(steam_needed, MIN_STEAM_KG_FOR_ACTIVATION)
    
    passed = char_ok and steam_ok
    
    # Capacity utilization score
    char_score = min(char_kg_annual / MIN_CHAR_KG_FOR_ACTIVATION, 1.0)
    steam_score = min(steam_available_kg_annual / max(steam_needed, 1), 1.0)
    value = min(char_score, steam_score)  # Bottleneck determines viability
    
    remediation = None
    if not passed:
        issues = []
        if not char_ok:
            issues.append(
                f"Char production {char_kg_annual:.0f} kg/yr < {MIN_CHAR_KG_FOR_ACTIVATION:.0f} kg/yr threshold"
            )
        if not steam_ok:
            issues.append(
                f"Steam available {steam_available_kg_annual:.0f} kg/yr insufficient for {steam_needed:.0f} kg/yr needed"
            )
        
        remediation = (
            f"Char activation not viable: {'; '.join(issues)}. "
            "Consider direct char sale (Tier 1/2) or co-processing external biochar."
        )
    
    return GateResult(
        name="Char Activation Viability",
        passed=passed,
        value=value,
        threshold=1.0,
        remediation=remediation,
    )


def heat_export_viability_gate(
    excess_heat_mj_annual: float,
    heat_customer_available: bool,
    min_export_mj: float = 100_000.0,  # 100 GJ/yr minimum for district heat
) -> GateResult:
    """
    Check if excess heat and customer availability support heat export.
    
    Heat export viability requires:
    - Sufficient excess heat (configurable threshold, default 100 GJ/yr)
    - Nearby heat customer (adjacent building, district heating network)
    
    Args:
        excess_heat_mj_annual: Available excess heat in MJ/yr
        heat_customer_available: Whether heat customer exists within viable distance
        min_export_mj: Minimum heat export threshold (default 100,000 MJ/yr)
        
    Returns:
        GateResult indicating viability
    """
    heat_ok = excess_heat_mj_annual >= min_export_mj
    passed = heat_ok and heat_customer_available
    
    remediation = None
    if not passed:
        issues = []
        if not heat_ok:
            issues.append(
                f"Excess heat {excess_heat_mj_annual:.0f} MJ/yr < {min_export_mj:.0f} MJ/yr threshold"
            )
        if not heat_customer_available:
            issues.append("No heat customer within viable export distance")
        
        remediation = (
            f"Heat export not viable: {'; '.join(issues)}. "
            "Identify adjacent buildings for heat integration or use heat for process needs."
        )
    
    return GateResult(
        name="Heat Export Viability",
        passed=passed,
        value=excess_heat_mj_annual,
        threshold=min_export_mj,
        remediation=remediation,
    )


def run_pathway_viability_gates(
    centrate_m3_annual: float = 0.0,
    p_conc_mg_l: float = 0.0,
    syngas_excess_mj_annual: float = 0.0,
    char_kg_annual: float = 0.0,
    steam_available_kg_annual: float = 0.0,
    excess_heat_mj_annual: float = 0.0,
    has_discharge_permit: bool = True,
    grid_interconnect_available: bool = True,
    heat_customer_available: bool = False,
) -> GateReport:
    """
    Run all pathway viability gates for value-add screening.
    
    Use this to determine which value-add pathways are viable before
    running detailed scenario analysis.
    
    Args:
        centrate_m3_annual: Annual centrate volume (m³)
        p_conc_mg_l: Phosphorus concentration (mg/L PO4-P)
        syngas_excess_mj_annual: Excess syngas energy (MJ/yr)
        char_kg_annual: Annual char production (kg)
        steam_available_kg_annual: Available steam (kg/yr)
        excess_heat_mj_annual: Available excess heat (MJ/yr)
        has_discharge_permit: Existing discharge permit
        grid_interconnect_available: Grid interconnect feasibility
        heat_customer_available: Heat customer availability
        
    Returns:
        GateReport with all pathway viability gates
    """
    gates = [
        nutrient_recovery_viability_gate(
            centrate_m3_annual, p_conc_mg_l, has_discharge_permit
        ),
        chp_grid_viability_gate(
            syngas_excess_mj_annual,
            grid_interconnect_available=grid_interconnect_available,
        ),
        char_activation_viability_gate(
            char_kg_annual, steam_available_kg_annual
        ),
        heat_export_viability_gate(
            excess_heat_mj_annual, heat_customer_available
        ),
    ]
    
    return GateReport(gates=gates)

