"""
Thermal Feasibility Module - Heat transfer constraints for pyrolysis reactor design.

Provides:
    - Heat required calculation (sensible + latent + reaction)
    - Heat available calculation (from reactor wall)
    - Thermal feasibility gate (Q_req <= Q_max)

Design Intent:
    If Q_req > Q_max, the reactor cannot physically deliver the required
    heat rate regardless of kinetics or yields. This is the hardest 
    physical constraint for pyrolysis reactor design.

Key Equations:
    Q_req = ṁ·cp·ΔT + ṁ_water·Δh_vap + ṁ_rxn·ΔH_py
    Q_max = U·A·ΔT_lm

References:
    - ref_pyrolysis_heat_transfer_2015
    - ref_pyrolysis_enthalpy_2011
"""

from dataclasses import dataclass
from typing import Optional, List, Tuple
import math

from .parameters import (
    ReactorParams,
    FeedstockProperties,
    OperatingEnvelope,
    OvernightState,
    OPERATING_ENVELOPE_DEFAULT,
)


# Thermodynamic constants
CP_SOLIDS_J_KG_K = 1500.0       # Specific heat of dried solids (J/kg·K)
CP_WATER_J_KG_K = 4186.0        # Specific heat of water (J/kg·K)
DELTA_H_VAP_J_KG = 2.26e6       # Latent heat of vaporization (J/kg)
DELTA_H_PY_J_KG = 0.5e6         # Pyrolysis enthalpy (J/kg dry solids, endothermic)


@dataclass
class HeatRequirement:
    """Breakdown of heat required for pyrolysis."""
    Q_sensible_kw: float        # Heat to raise solids temperature
    Q_latent_kw: float          # Heat to vaporize remaining water
    Q_reaction_kw: float        # Heat of pyrolysis reaction
    Q_total_kw: float           # Total heat required
    
    m_dot_solids_kg_s: float    # Dry solids flow rate
    m_dot_water_kg_s: float     # Water flow rate (in feed)
    T_feed_k: float             # Feed temperature
    T_reactor_k: float          # Reactor temperature
    
    @property
    def heat_intensity_kw_per_kg(self) -> float:
        """Heat required per kg dry solids."""
        if self.m_dot_solids_kg_s <= 0:
            return 0.0
        return self.Q_total_kw / self.m_dot_solids_kg_s


@dataclass
class HeatAvailable:
    """Heat transfer capacity of reactor."""
    Q_max_kw: float             # Maximum heat transfer rate
    U_w_m2k: float              # Overall heat transfer coefficient
    A_m2: float                 # Heat transfer area
    delta_T_lm_k: float         # Log-mean temperature difference
    
    T_wall_k: float             # Wall temperature
    T_inlet_k: float            # Solids inlet temperature
    T_outlet_k: float           # Solids outlet temperature
    
    @property
    def heat_flux_kw_m2(self) -> float:
        """Heat flux at the wall."""
        if self.A_m2 <= 0:
            return 0.0
        return self.Q_max_kw / self.A_m2


@dataclass
class ThermalFeasibilityResult:
    """Result of thermal feasibility check."""
    feasible: bool              # Q_req <= Q_max
    Q_req_kw: float             # Total heat required
    Q_max_kw: float             # Maximum heat available
    margin_pct: float           # (Q_max - Q_req) / Q_max * 100
    
    # Detailed breakdowns
    heat_requirement: HeatRequirement
    heat_available: HeatAvailable
    
    @property
    def utilization_pct(self) -> float:
        """Heat transfer utilization (Q_req / Q_max * 100)."""
        if self.Q_max_kw <= 0:
            return float('inf')
        return self.Q_req_kw / self.Q_max_kw * 100
    
    @property
    def deficit_kw(self) -> float:
        """Heat deficit (positive if infeasible)."""
        return max(0.0, self.Q_req_kw - self.Q_max_kw)


def calc_log_mean_temp_diff(
    T_hot: float,
    T_cold_in: float,
    T_cold_out: float,
) -> float:
    """
    Calculate log-mean temperature difference for counter-current heat transfer.
    
    Args:
        T_hot: Hot side temperature (wall, assumed constant)
        T_cold_in: Cold side inlet temperature (feed)
        T_cold_out: Cold side outlet temperature (product)
    
    Returns:
        Log-mean temperature difference (K)
    """
    delta_T1 = T_hot - T_cold_in   # Difference at cold inlet
    delta_T2 = T_hot - T_cold_out  # Difference at cold outlet
    
    # Handle edge cases
    if delta_T1 <= 0 or delta_T2 <= 0:
        return 0.0
    
    if abs(delta_T1 - delta_T2) < 0.1:
        # Approximately equal - avoid log(1)
        return (delta_T1 + delta_T2) / 2
    
    return (delta_T1 - delta_T2) / math.log(delta_T1 / delta_T2)


def calc_heat_required(
    m_dot_dry_kg_s: float,
    feedstock: FeedstockProperties,
    T_feed_k: float,
    T_reactor_k: float,
    delta_H_py_J_kg: float = DELTA_H_PY_J_KG,
) -> HeatRequirement:
    """
    Calculate total heat required for pyrolysis.
    
    Q_req = Q_sensible + Q_latent + Q_reaction
    
    Where:
        Q_sensible = ṁ_dry · cp · (T_reactor - T_feed)
        Q_latent = ṁ_water · Δh_vap
        Q_reaction = ṁ_dry · ΔH_py
    
    Args:
        m_dot_dry_kg_s: Dry solids mass flow rate (kg/s)
        feedstock: Feedstock properties (for moisture content)
        T_feed_k: Feed temperature (K)
        T_reactor_k: Reactor temperature (K)
        delta_H_py_J_kg: Pyrolysis enthalpy (J/kg dry, positive = endothermic)
    
    Returns:
        HeatRequirement with detailed breakdown
    """
    # Calculate water content
    # Note: moisture_fraction is water/(water+dry), so:
    # m_wet = m_dry / (1 - moisture_fraction) for as-received
    # But we assume feed is pre-dried to some extent (from dryer)
    # Use residual moisture after dryer (assume ~25% water in dried cake)
    residual_moisture = 0.25  # After dryer, before pyrolysis
    m_dot_water_kg_s = m_dot_dry_kg_s * residual_moisture / (1 - residual_moisture)
    
    # Temperature difference
    delta_T = T_reactor_k - T_feed_k
    
    # Sensible heat (solids + water heating)
    Q_sensible_w = (m_dot_dry_kg_s * CP_SOLIDS_J_KG_K * delta_T +
                   m_dot_water_kg_s * CP_WATER_J_KG_K * delta_T)
    
    # Latent heat (water vaporization)
    Q_latent_w = m_dot_water_kg_s * DELTA_H_VAP_J_KG
    
    # Reaction heat (pyrolysis enthalpy)
    Q_reaction_w = m_dot_dry_kg_s * delta_H_py_J_kg
    
    # Total
    Q_total_w = Q_sensible_w + Q_latent_w + Q_reaction_w
    
    # Convert to kW
    return HeatRequirement(
        Q_sensible_kw=Q_sensible_w / 1000,
        Q_latent_kw=Q_latent_w / 1000,
        Q_reaction_kw=Q_reaction_w / 1000,
        Q_total_kw=Q_total_w / 1000,
        m_dot_solids_kg_s=m_dot_dry_kg_s,
        m_dot_water_kg_s=m_dot_water_kg_s,
        T_feed_k=T_feed_k,
        T_reactor_k=T_reactor_k,
    )


def calc_heat_available(
    reactor: ReactorParams,
    T_reactor_k: Optional[float] = None,
) -> HeatAvailable:
    """
    Calculate maximum heat transfer rate from reactor wall.
    
    Q_max = U · A · ΔT_lm
    
    Args:
        reactor: Reactor parameters (geometry, U, temperatures)
        T_reactor_k: Override for reactor outlet temperature (if different from wall)
    
    Returns:
        HeatAvailable with maximum heat transfer rate
    """
    # Use reactor parameters
    U = reactor.U_w_m2k
    A = reactor.heat_transfer_area_m2
    T_wall = reactor.T_wall_k
    T_inlet = reactor.T_feed_k
    T_outlet = T_reactor_k or (T_wall - 100)  # Assume some approach temp
    
    # Log-mean temperature difference
    delta_T_lm = calc_log_mean_temp_diff(T_wall, T_inlet, T_outlet)
    
    # Maximum heat transfer
    Q_max_w = U * A * delta_T_lm
    
    return HeatAvailable(
        Q_max_kw=Q_max_w / 1000,
        U_w_m2k=U,
        A_m2=A,
        delta_T_lm_k=delta_T_lm,
        T_wall_k=T_wall,
        T_inlet_k=T_inlet,
        T_outlet_k=T_outlet,
    )


def check_thermal_feasibility(
    m_dot_dry_kg_s: float,
    feedstock: FeedstockProperties,
    reactor: ReactorParams,
    T_reactor_k: Optional[float] = None,
) -> ThermalFeasibilityResult:
    """
    Check if reactor can deliver required heat rate.
    
    This is the critical design gate: if Q_req > Q_max, the design
    fails regardless of kinetics or yields.
    
    Args:
        m_dot_dry_kg_s: Dry solids mass flow rate (kg/s)
        feedstock: Feedstock properties
        reactor: Reactor parameters
        T_reactor_k: Reactor operating temperature (default: use kinetics temp)
    
    Returns:
        ThermalFeasibilityResult with pass/fail and margins
    """
    # Use reactor wall temp minus approach as operating temp
    T_op = T_reactor_k or (reactor.T_wall_k - 100)
    
    # Calculate heat required
    heat_req = calc_heat_required(
        m_dot_dry_kg_s=m_dot_dry_kg_s,
        feedstock=feedstock,
        T_feed_k=reactor.T_feed_k,
        T_reactor_k=T_op,
    )
    
    # Calculate heat available
    heat_avail = calc_heat_available(
        reactor=reactor,
        T_reactor_k=T_op,
    )
    
    # Check feasibility
    feasible = heat_req.Q_total_kw <= heat_avail.Q_max_kw
    
    # Calculate margin
    if heat_avail.Q_max_kw > 0:
        margin_pct = (heat_avail.Q_max_kw - heat_req.Q_total_kw) / heat_avail.Q_max_kw * 100
    else:
        margin_pct = -100.0
    
    return ThermalFeasibilityResult(
        feasible=feasible,
        Q_req_kw=heat_req.Q_total_kw,
        Q_max_kw=heat_avail.Q_max_kw,
        margin_pct=margin_pct,
        heat_requirement=heat_req,
        heat_available=heat_avail,
    )


def calc_max_throughput(
    feedstock: FeedstockProperties,
    reactor: ReactorParams,
    safety_factor: float = 0.80,
) -> float:
    """
    Calculate maximum dry solids throughput limited by heat transfer.
    
    Finds m_dot such that Q_req = safety_factor * Q_max.
    
    Args:
        feedstock: Feedstock properties
        reactor: Reactor parameters  
        safety_factor: Target utilization (default 80%)
    
    Returns:
        Maximum dry solids throughput (kg/s)
    """
    # Get available heat
    T_op = reactor.T_wall_k - 100  # Operating temperature
    heat_avail = calc_heat_available(reactor, T_op)
    Q_available_kw = heat_avail.Q_max_kw * safety_factor
    
    # Calculate heat per kg (at 1 kg/s reference)
    ref_heat = calc_heat_required(
        m_dot_dry_kg_s=1.0,
        feedstock=feedstock,
        T_feed_k=reactor.T_feed_k,
        T_reactor_k=T_op,
    )
    heat_per_kg_kw = ref_heat.Q_total_kw
    
    if heat_per_kg_kw <= 0:
        return float('inf')
    
    return Q_available_kw / heat_per_kg_kw


def print_thermal_summary(result: ThermalFeasibilityResult) -> None:
    """Print human-readable thermal feasibility summary."""
    status = "FEASIBLE" if result.feasible else "INFEASIBLE"
    
    req = result.heat_requirement
    avail = result.heat_available
    
    print("=" * 60)
    print("THERMAL FEASIBILITY ANALYSIS")
    print("=" * 60)
    print()
    print("HEAT REQUIRED:")
    print(f"  Sensible:        {req.Q_sensible_kw:8.2f} kW")
    print(f"  Latent (water):  {req.Q_latent_kw:8.2f} kW")
    print(f"  Reaction:        {req.Q_reaction_kw:8.2f} kW")
    print(f"  ─────────────────────────────")
    print(f"  TOTAL:           {req.Q_total_kw:8.2f} kW")
    print()
    print("HEAT AVAILABLE:")
    print(f"  U:               {avail.U_w_m2k:8.1f} W/m²K")
    print(f"  Area:            {avail.A_m2:8.2f} m²")
    print(f"  ΔT_lm:           {avail.delta_T_lm_k:8.1f} K")
    print(f"  ─────────────────────────────")
    print(f"  Q_MAX:           {avail.Q_max_kw:8.2f} kW")
    print()
    print("FEASIBILITY:")
    print(f"  Utilization:     {result.utilization_pct:8.1f}%")
    print(f"  Margin:          {result.margin_pct:+8.1f}%")
    print(f"  Status:          {status}")
    
    if not result.feasible:
        print()
        print(f"  ⚠ DEFICIT:       {result.deficit_kw:8.2f} kW")
        print("  Remediation: Reduce throughput, increase U or A, or raise T_wall")
    
    print("=" * 60)


# =============================================================================
# Operating Envelope Validation
# =============================================================================

@dataclass
class EnvelopeViolation:
    """A single constraint violation within the operating envelope."""
    constraint: str         # Name of violated constraint
    value: float            # Actual value
    limit: float            # Limit value
    direction: str          # "above" or "below"
    severity: str           # "hard" (physics) or "soft" (operational)
    remediation: str        # What to do about it
    
    def __str__(self) -> str:
        return (
            f"[{self.severity.upper()}] {self.constraint}: "
            f"{self.value:.2f} is {self.direction} limit {self.limit:.2f}. "
            f"{self.remediation}"
        )


@dataclass
class EnvelopeCheckResult:
    """
    Result of operating envelope validation.
    
    Combines structured pass/fail with detailed violation list
    for actionable reporting.
    """
    within_envelope: bool
    violations: List[EnvelopeViolation]
    operating_point: dict          # Snapshot of checked values
    envelope_name: str = "default"
    
    @property
    def hard_violations(self) -> List[EnvelopeViolation]:
        """Violations that make operation physically impossible."""
        return [v for v in self.violations if v.severity == "hard"]
    
    @property
    def soft_violations(self) -> List[EnvelopeViolation]:
        """Violations that are operationally undesirable but not impossible."""
        return [v for v in self.violations if v.severity == "soft"]
    
    def __str__(self) -> str:
        status = "WITHIN ENVELOPE" if self.within_envelope else "OUTSIDE ENVELOPE"
        lines = [f"Operating Envelope Check: {status}"]
        if self.violations:
            lines.append(f"  Violations ({len(self.violations)}):")
            for v in self.violations:
                lines.append(f"    {v}")
        return "\n".join(lines)


def check_operating_envelope(
    throughput_kgds_hr: float,
    wall_temperature_c: float,
    feed_ts: float,
    residence_time_s: float = 0.0,
    reactor_temperature_c: float = 0.0,
    overnight_state: Optional[OvernightState] = None,
    overnight_temp_c: Optional[float] = None,
    syngas_self_sufficiency: float = 1.0,
    aux_fuel_fraction: float = 0.0,
    envelope: Optional[OperatingEnvelope] = None,
) -> EnvelopeCheckResult:
    """
    Validate an operating point against the operating envelope.
    
    Checks all constraints and returns structured results with
    per-violation remediation guidance.
    
    Args:
        throughput_kgds_hr: Dry solids throughput to pyrolysis (kg DS/hr)
        wall_temperature_c: Reactor wall temperature (°C)
        feed_ts: Feed total solids fraction (0-1)
        residence_time_s: Solids residence time (s), 0 to skip
        reactor_temperature_c: Reactor operating temperature (°C), 0 to skip
        overnight_state: Planned overnight state, None to skip
        overnight_temp_c: Overnight hold temperature (°C), None to skip
        syngas_self_sufficiency: Syngas/heat demand ratio
        aux_fuel_fraction: Fraction of heat from external fuel
        envelope: Operating envelope to check against (default: OPERATING_ENVELOPE_DEFAULT)
        
    Returns:
        EnvelopeCheckResult with violations list and pass/fail
    """
    env = envelope or OPERATING_ENVELOPE_DEFAULT
    violations: List[EnvelopeViolation] = []
    
    # --- Throughput ---
    if throughput_kgds_hr > env.max_throughput_kgds_hr:
        violations.append(EnvelopeViolation(
            constraint="max_throughput",
            value=throughput_kgds_hr,
            limit=env.max_throughput_kgds_hr,
            direction="above",
            severity="hard",
            remediation="Reduce feed rate or upgrade reactor capacity",
        ))
    if throughput_kgds_hr < env.min_throughput_kgds_hr:
        violations.append(EnvelopeViolation(
            constraint="min_throughput",
            value=throughput_kgds_hr,
            limit=env.min_throughput_kgds_hr,
            direction="below",
            severity="soft",
            remediation="Increase feed rate or supplement with co-feed for stable operation",
        ))
    
    # --- Wall temperature ---
    if wall_temperature_c > env.max_wall_temperature_c:
        violations.append(EnvelopeViolation(
            constraint="max_wall_temperature",
            value=wall_temperature_c,
            limit=env.max_wall_temperature_c,
            direction="above",
            severity="hard",
            remediation="Reduce combustion temperature or increase wall cooling",
        ))
    if wall_temperature_c < env.min_wall_temperature_c:
        violations.append(EnvelopeViolation(
            constraint="min_wall_temperature",
            value=wall_temperature_c,
            limit=env.min_wall_temperature_c,
            direction="below",
            severity="hard",
            remediation="Increase heat input; below this temperature pyrolysis is incomplete",
        ))
    
    # --- Feed TS ---
    if feed_ts > env.max_feed_ts:
        violations.append(EnvelopeViolation(
            constraint="max_feed_ts",
            value=feed_ts,
            limit=env.max_feed_ts,
            direction="above",
            severity="soft",
            remediation="Check feeder bridging/handling; very dry feed may need moisture addition",
        ))
    if feed_ts < env.min_feed_ts:
        violations.append(EnvelopeViolation(
            constraint="min_feed_ts",
            value=feed_ts,
            limit=env.min_feed_ts,
            direction="below",
            severity="hard",
            remediation="Feed too wet for pyrolysis; increase drying or reject load",
        ))
    
    # --- Residence time (if provided) ---
    if residence_time_s > 0:
        if residence_time_s < env.min_residence_time_s:
            violations.append(EnvelopeViolation(
                constraint="min_residence_time",
                value=residence_time_s,
                limit=env.min_residence_time_s,
                direction="below",
                severity="hard",
                remediation="Reduce throughput or increase reactor volume for adequate conversion",
            ))
        if residence_time_s > env.max_residence_time_s:
            violations.append(EnvelopeViolation(
                constraint="max_residence_time",
                value=residence_time_s,
                limit=env.max_residence_time_s,
                direction="above",
                severity="soft",
                remediation="Increase throughput; excessive residence time degrades char quality",
            ))
    
    # --- Reactor temperature (if provided) ---
    if reactor_temperature_c > 0:
        if reactor_temperature_c < env.min_reactor_temperature_c:
            violations.append(EnvelopeViolation(
                constraint="min_reactor_temperature",
                value=reactor_temperature_c,
                limit=env.min_reactor_temperature_c,
                direction="below",
                severity="hard",
                remediation="Increase heat input; below min operating temperature",
            ))
        if reactor_temperature_c > env.max_reactor_temperature_c:
            violations.append(EnvelopeViolation(
                constraint="max_reactor_temperature",
                value=reactor_temperature_c,
                limit=env.max_reactor_temperature_c,
                direction="above",
                severity="hard",
                remediation="Reduce heat input; above max operating temperature",
            ))
    
    # --- Overnight state ---
    if overnight_state is not None:
        if not env.overnight_state_allowed(overnight_state):
            violations.append(EnvelopeViolation(
                constraint="overnight_state",
                value=0.0,  # Categorical, not numeric
                limit=0.0,
                direction="above",
                severity="hard",
                remediation=f"Overnight state '{overnight_state.value}' not in allowed set: "
                           f"{[s.value for s in env.allowed_overnight_states]}",
            ))
    
    if overnight_temp_c is not None:
        if not env.overnight_temp_safe(overnight_temp_c):
            violations.append(EnvelopeViolation(
                constraint="min_overnight_temperature",
                value=overnight_temp_c,
                limit=env.min_overnight_temp_c,
                direction="below",
                severity="hard",
                remediation="Overnight temperature too low; risk of tar condensation and plugging",
            ))
    
    # --- Energy self-sufficiency ---
    if syngas_self_sufficiency < env.min_syngas_self_sufficiency:
        violations.append(EnvelopeViolation(
            constraint="syngas_self_sufficiency",
            value=syngas_self_sufficiency,
            limit=env.min_syngas_self_sufficiency,
            direction="below",
            severity="soft",
            remediation="Increase co-feed or reduce heat demand to achieve energy self-sufficiency",
        ))
    
    if aux_fuel_fraction > env.max_aux_fuel_fraction:
        violations.append(EnvelopeViolation(
            constraint="max_aux_fuel_fraction",
            value=aux_fuel_fraction,
            limit=env.max_aux_fuel_fraction,
            direction="above",
            severity="soft",
            remediation="Reduce external fuel dependency; increase syngas recovery or co-feed",
        ))
    
    operating_point = {
        "throughput_kgds_hr": throughput_kgds_hr,
        "wall_temperature_c": wall_temperature_c,
        "feed_ts": feed_ts,
        "residence_time_s": residence_time_s,
        "reactor_temperature_c": reactor_temperature_c,
        "overnight_state": overnight_state.value if overnight_state else None,
        "overnight_temp_c": overnight_temp_c,
        "syngas_self_sufficiency": syngas_self_sufficiency,
        "aux_fuel_fraction": aux_fuel_fraction,
    }
    
    # Only hard violations make the point "outside envelope"
    hard_fail = any(v.severity == "hard" for v in violations)
    
    return EnvelopeCheckResult(
        within_envelope=not hard_fail,
        violations=violations,
        operating_point=operating_point,
    )
