"""
Core Balances Module - Pure mass and energy balance calculations.
PHYSICS ONLY - No control logic, no economics.

All functions:
    - Are stateless (no side effects)
    - Take explicit inputs, return explicit outputs
    - Include conservation assertions where applicable
    - Use SI units (kg, m³, MJ, hr)
"""

from dataclasses import dataclass
from typing import Tuple, NamedTuple
from .utils import validate_fraction, validate_positive, validate_non_negative, assert_mass_balance


# ============================================================================
# Governing Equations Reference (from spec):
# ============================================================================
#
# EQ Tank:      dV_eq/dt = Q_in - Q_out
# Dewatering:   M_cake = Q_dw * ρ * TS_in * η_cap / TS_cake
#               V_cen  = Q_dw - M_cake / ρ
# Dryer:        M_dried = M_cake * TS_cake / TS_dried
#               E_dry   = (M_cake - M_dried) * h_fg / η_th
# Pyrolysis:    M_char = M_dried * Y_c
#               M_gas  = M_dried * Y_g
#               M_cond = M_dried * Y_l
# Energy:       Q_net = M_gas * LHV_gas * η_rec - E_dry - M_dried * q_pyro
# Centrate:     V_cen_out = min(V_cen_avail, Q_permit * Δt) during window
# ============================================================================


class DeWateringResult(NamedTuple):
    """Result of dewatering calculation."""
    septage_processed_m3: float
    cake_produced_kgds: float
    centrate_produced_m3: float
    centrate_ds_kgds: float
    polymer_used_kg: float
    power_kwh: float


class DryerResult(NamedTuple):
    """Result of dryer calculation."""
    cake_consumed_kgds: float
    dried_produced_kgds: float
    water_evaporated_kg: float
    heat_duty_mj: float


class PyrolysisResult(NamedTuple):
    """Result of pyrolysis calculation."""
    dried_consumed_kgds: float
    char_produced_kg: float
    gas_produced_kg: float
    condensate_produced_kg: float
    heat_required_mj: float
    syngas_energy_mj: float
    char_carbon_kg: float


class EnergyBalanceResult(NamedTuple):
    """Result of energy balance calculation."""
    dryer_duty_mj: float
    pyro_duty_mj: float
    syngas_recovered_mj: float
    net_heat_mj: float
    heat_deficit: bool
    aux_fuel_mj: float


class CarbonResult(NamedTuple):
    """Result of carbon accounting."""
    carbon_in_kg: float
    char_carbon_kg: float
    sequestered_kg: float
    emitted_kg: float
    net_credits_kgco2e: float


# ============================================================================
# Mass Balance Functions
# ============================================================================


def calc_dewatering(
    septage_m3: float,
    ts_fraction: float,
    density_kg_m3: float,
    cake_ts_fraction: float,
    solids_capture: float,
    polymer_kg_per_tds: float,
    power_kwh_per_m3: float
) -> DeWateringResult:
    """
    Calculate dewatering mass balance.
    
    Args:
        septage_m3: Volume of septage to process
        ts_fraction: Total solids fraction of incoming septage
        density_kg_m3: Septage density
        cake_ts_fraction: Target cake solids fraction (e.g., 0.20)
        solids_capture: Fraction of solids captured in cake
        polymer_kg_per_tds: Polymer dose per tonne dry solids
        power_kwh_per_m3: Electrical power per m³ processed
    
    Returns:
        DeWateringResult with all outputs
    """
    validate_non_negative(septage_m3, "septage_m3")
    validate_fraction(ts_fraction, "ts_fraction")
    validate_fraction(cake_ts_fraction, "cake_ts_fraction")
    validate_fraction(solids_capture, "solids_capture")
    
    if septage_m3 == 0:
        return DeWateringResult(0, 0, 0, 0, 0, 0)
    
    septage_mass_kg = septage_m3 * density_kg_m3
    ds_in_kg = septage_mass_kg * ts_fraction
    
    ds_captured_kg = ds_in_kg * solids_capture
    ds_lost_kg = ds_in_kg * (1 - solids_capture)
    
    cake_mass_kg = ds_captured_kg / cake_ts_fraction
    cake_water_kg = cake_mass_kg - ds_captured_kg
    
    total_water_in_kg = septage_mass_kg - ds_in_kg
    centrate_water_kg = total_water_in_kg - cake_water_kg
    centrate_mass_kg = centrate_water_kg + ds_lost_kg
    centrate_m3 = centrate_mass_kg / density_kg_m3
    
    polymer_kg = (ds_captured_kg / 1000) * polymer_kg_per_tds
    power_kwh = septage_m3 * power_kwh_per_m3
    
    total_in = septage_mass_kg
    total_out = cake_mass_kg + centrate_mass_kg
    assert_mass_balance(total_in, total_out, "Dewatering", tolerance=0.001)
    
    return DeWateringResult(
        septage_processed_m3=septage_m3,
        cake_produced_kgds=ds_captured_kg,
        centrate_produced_m3=centrate_m3,
        centrate_ds_kgds=ds_lost_kg,
        polymer_used_kg=polymer_kg,
        power_kwh=power_kwh
    )


def calc_dryer(
    cake_kgds: float,
    cake_ts_fraction: float,
    dried_ts_fraction: float,
    energy_kwh_per_kg_water: float,
    thermal_efficiency: float
) -> DryerResult:
    """
    Calculate dryer mass and energy balance.
    
    Args:
        cake_kgds: Dry solids mass of cake feed
        cake_ts_fraction: Solids fraction of cake (e.g., 0.20)
        dried_ts_fraction: Target solids fraction of dried product (e.g., 0.75)
        energy_kwh_per_kg_water: Specific energy for evaporation
        thermal_efficiency: Thermal efficiency of dryer
    
    Returns:
        DryerResult with outputs
        
    Note:
        If cake is already drier than target (cake_ts >= dried_ts), 
        no evaporation occurs - the dryer is bypassed.
    """
    validate_non_negative(cake_kgds, "cake_kgds")
    validate_fraction(cake_ts_fraction, "cake_ts_fraction")
    validate_fraction(dried_ts_fraction, "dried_ts_fraction")
    validate_fraction(thermal_efficiency, "thermal_efficiency")
    
    if cake_kgds == 0:
        return DryerResult(0, 0, 0, 0)
    
    # If cake already drier than target, bypass dryer (no evaporation needed)
    if cake_ts_fraction >= dried_ts_fraction:
        return DryerResult(
            cake_consumed_kgds=cake_kgds,
            dried_produced_kgds=cake_kgds,
            water_evaporated_kg=0.0,
            heat_duty_mj=0.0
        )
    
    cake_total_kg = cake_kgds / cake_ts_fraction
    cake_water_kg = cake_total_kg - cake_kgds
    
    dried_total_kg = cake_kgds / dried_ts_fraction
    dried_water_kg = dried_total_kg - cake_kgds
    
    # Clamp to non-negative (physics constraint: can't unevaporate water)
    water_evaporated_kg = max(0.0, cake_water_kg - dried_water_kg)
    
    heat_duty_kwh = water_evaporated_kg * energy_kwh_per_kg_water / thermal_efficiency
    heat_duty_mj = heat_duty_kwh * 3.6
    
    total_in = cake_total_kg
    total_out = dried_total_kg + water_evaporated_kg
    assert_mass_balance(total_in, total_out, "Dryer", tolerance=0.001)
    
    return DryerResult(
        cake_consumed_kgds=cake_kgds,
        dried_produced_kgds=cake_kgds,
        water_evaporated_kg=water_evaporated_kg,
        heat_duty_mj=heat_duty_mj
    )


def calc_pyrolysis(
    dried_kgds: float,
    dried_ts_fraction: float,
    yield_char: float,
    yield_gas: float,
    yield_condensate: float,
    heat_requirement_mj_kgds: float,
    lhv_syngas_mj_kg: float,
    syngas_recovery_efficiency: float,
    char_carbon_fraction: float,
    char_permanence_factor: float
) -> PyrolysisResult:
    """
    Calculate pyrolysis mass and energy balance.
    
    Args:
        dried_kgds: Dry solids mass of dried feed
        dried_ts_fraction: Solids fraction of dried product
        yield_char: Mass fraction to char
        yield_gas: Mass fraction to syngas
        yield_condensate: Mass fraction to condensate
        heat_requirement_mj_kgds: Specific heat for pyrolysis
        lhv_syngas_mj_kg: Lower heating value of syngas
        syngas_recovery_efficiency: Fraction of syngas energy recovered
        char_carbon_fraction: Carbon content of char
        char_permanence_factor: Fraction of char carbon considered permanent
    
    Returns:
        PyrolysisResult with outputs
    """
    validate_non_negative(dried_kgds, "dried_kgds")
    validate_fraction(yield_char, "yield_char")
    validate_fraction(yield_gas, "yield_gas")
    validate_fraction(yield_condensate, "yield_condensate")
    
    yields_sum = yield_char + yield_gas + yield_condensate
    if abs(yields_sum - 1.0) > 0.001:
        raise ValueError(f"Pyrolysis yields must sum to 1.0, got {yields_sum}")
    
    if dried_kgds == 0:
        return PyrolysisResult(0, 0, 0, 0, 0, 0, 0)
    
    dried_total_kg = dried_kgds / dried_ts_fraction
    
    char_kg = dried_total_kg * yield_char
    gas_kg = dried_total_kg * yield_gas
    condensate_kg = dried_total_kg * yield_condensate
    
    heat_required_mj = dried_kgds * heat_requirement_mj_kgds
    
    syngas_energy_mj = gas_kg * lhv_syngas_mj_kg * syngas_recovery_efficiency
    
    char_carbon_kg = char_kg * char_carbon_fraction
    
    total_in = dried_total_kg
    total_out = char_kg + gas_kg + condensate_kg
    assert_mass_balance(total_in, total_out, "Pyrolysis", tolerance=0.001)
    
    return PyrolysisResult(
        dried_consumed_kgds=dried_kgds,
        char_produced_kg=char_kg,
        gas_produced_kg=gas_kg,
        condensate_produced_kg=condensate_kg,
        heat_required_mj=heat_required_mj,
        syngas_energy_mj=syngas_energy_mj,
        char_carbon_kg=char_carbon_kg
    )


def calc_cofeed_pyrolysis(
    septage_dried_kgds: float,
    cofeed_kgds: float,
    septage_dried_ts: float,
    cofeed_ts: float,
    yield_char_sept: float,
    yield_gas_sept: float,
    yield_cond_sept: float,
    yield_char_cofeed: float,
    yield_gas_cofeed: float,
    yield_cond_cofeed: float,
    heat_req_mj_kgds: float,
    lhv_syngas_sept: float,
    lhv_syngas_cofeed: float,
    syngas_recovery: float,
    char_c_sept: float,
    char_c_cofeed: float,
    permanence: float
) -> Tuple[PyrolysisResult, PyrolysisResult]:
    """
    Calculate pyrolysis with co-feed, tracking sources separately.
    
    Returns tuple of (septage_result, cofeed_result).
    """
    sept_result = calc_pyrolysis(
        dried_kgds=septage_dried_kgds,
        dried_ts_fraction=septage_dried_ts,
        yield_char=yield_char_sept,
        yield_gas=yield_gas_sept,
        yield_condensate=yield_cond_sept,
        heat_requirement_mj_kgds=heat_req_mj_kgds,
        lhv_syngas_mj_kg=lhv_syngas_sept,
        syngas_recovery_efficiency=syngas_recovery,
        char_carbon_fraction=char_c_sept,
        char_permanence_factor=permanence
    )
    
    cofeed_result = calc_pyrolysis(
        dried_kgds=cofeed_kgds,
        dried_ts_fraction=cofeed_ts,
        yield_char=yield_char_cofeed,
        yield_gas=yield_gas_cofeed,
        yield_condensate=yield_cond_cofeed,
        heat_requirement_mj_kgds=heat_req_mj_kgds,
        lhv_syngas_mj_kg=lhv_syngas_cofeed,
        syngas_recovery_efficiency=syngas_recovery,
        char_carbon_fraction=char_c_cofeed,
        char_permanence_factor=permanence
    )
    
    return sept_result, cofeed_result


# ============================================================================
# Energy Balance Functions
# ============================================================================


def calc_energy_balance(
    dryer_duty_mj: float,
    pyro_duty_mj: float,
    syngas_energy_mj: float
) -> EnergyBalanceResult:
    """
    Calculate overall energy balance.
    
    Q_net = syngas_recovered - dryer_duty - pyro_duty
    
    If Q_net < 0, auxiliary fuel is needed.
    """
    net_heat_mj = syngas_energy_mj - dryer_duty_mj - pyro_duty_mj
    heat_deficit = net_heat_mj < 0
    aux_fuel_mj = -net_heat_mj if heat_deficit else 0.0
    
    return EnergyBalanceResult(
        dryer_duty_mj=dryer_duty_mj,
        pyro_duty_mj=pyro_duty_mj,
        syngas_recovered_mj=syngas_energy_mj,
        net_heat_mj=net_heat_mj,
        heat_deficit=heat_deficit,
        aux_fuel_mj=aux_fuel_mj
    )


def calc_lhv_septage(
    ts_fraction: float,
    organic_fraction: float = 0.65,
    base_lhv_mj_kgds: float = 15.0
) -> float:
    """
    Estimate lower heating value of septage dried solids.
    
    Baseline LHV_sept = 15 MJ/kg DS (locked parameter).
    """
    return base_lhv_mj_kgds * organic_fraction


# ============================================================================
# Carbon Accounting Functions
# ============================================================================


def calc_carbon_balance(
    septage_kgds: float,
    cofeed_kgds: float,
    char_kg: float,
    char_carbon_fraction: float,
    char_permanence_factor: float,
    septage_carbon_fraction: float = 0.35,
    cofeed_carbon_fraction: float = 0.45,
    baseline_emission_kgco2e_per_m3: float = 15.0,
    septage_m3: float = 0.0
) -> CarbonResult:
    """
    Calculate carbon balance and credits.
    
    Sequestered carbon = char_carbon * permanence
    Avoided emissions from baseline (e.g., lagoon) included if specified.
    """
    carbon_in_sept = septage_kgds * septage_carbon_fraction
    carbon_in_cofeed = cofeed_kgds * cofeed_carbon_fraction
    total_carbon_in = carbon_in_sept + carbon_in_cofeed
    
    char_carbon_kg = char_kg * char_carbon_fraction
    sequestered_kg = char_carbon_kg * char_permanence_factor
    emitted_kg = total_carbon_in - sequestered_kg
    
    avoided_emissions_kgco2e = septage_m3 * baseline_emission_kgco2e_per_m3
    
    sequestered_co2e = sequestered_kg * (44 / 12)
    net_credits_kgco2e = sequestered_co2e + avoided_emissions_kgco2e
    
    return CarbonResult(
        carbon_in_kg=total_carbon_in,
        char_carbon_kg=char_carbon_kg,
        sequestered_kg=sequestered_kg,
        emitted_kg=emitted_kg,
        net_credits_kgco2e=net_credits_kgco2e
    )


# ============================================================================
# Centrate Discharge Functions
# ============================================================================


def calc_centrate_discharge(
    available_m3: float,
    q_permit_m3_hr: float,
    timestep_hr: float,
    in_discharge_window: bool
) -> float:
    """
    Calculate centrate discharge for timestep.
    
    Discharge only during permitted windows (Mon-Fri, 8-16h).
    """
    if not in_discharge_window:
        return 0.0
    
    max_discharge = q_permit_m3_hr * timestep_hr
    return min(available_m3, max_discharge)


def is_discharge_window(
    day_of_week: int,
    hour_of_day: int,
    discharge_days: Tuple[int, ...],
    window_start: int,
    window_end: int
) -> bool:
    """
    Check if current time is within centrate discharge window.
    
    Args:
        day_of_week: 0=Monday, 6=Sunday
        hour_of_day: 0-23
        discharge_days: Tuple of allowed days (0-6)
        window_start: Start hour (inclusive)
        window_end: End hour (exclusive)
    """
    if day_of_week not in discharge_days:
        return False
    return window_start <= hour_of_day < window_end


# ============================================================================
# Steady-State Flow Calculations
# ============================================================================


def calc_steady_state_flows(
    annual_septage_m3: float,
    thermal_uptime: float,
    ts_fraction: float,
    density_kg_m3: float,
    cake_ts_fraction: float,
    dried_ts_fraction: float,
    yield_char: float,
    solids_capture: float
) -> dict:
    """
    Calculate steady-state mass flows through the system.
    
    Returns dict with all flow rates for sizing calculations.
    """
    effective_hours = 8760 * thermal_uptime
    
    septage_m3_hr = annual_septage_m3 / 8760
    
    septage_kg_hr = septage_m3_hr * density_kg_m3
    ds_in_kg_hr = septage_kg_hr * ts_fraction
    
    ds_captured_kg_hr = ds_in_kg_hr * solids_capture
    cake_total_kg_hr = ds_captured_kg_hr / cake_ts_fraction
    
    dryer_feed_kgds_hr = ds_captured_kg_hr * (8760 / effective_hours)
    dried_total_kg_hr = dryer_feed_kgds_hr / dried_ts_fraction
    
    pyro_feed_kgds_hr = dryer_feed_kgds_hr
    char_kg_hr = (pyro_feed_kgds_hr / dried_ts_fraction) * yield_char
    
    centrate_m3_hr = septage_m3_hr - (cake_total_kg_hr / density_kg_m3)
    
    return {
        "septage_m3_hr": septage_m3_hr,
        "septage_kgds_hr": ds_in_kg_hr,
        "cake_kgds_hr": ds_captured_kg_hr,
        "dryer_feed_kgds_hr": dryer_feed_kgds_hr,
        "pyro_feed_kgds_hr": pyro_feed_kgds_hr,
        "char_kg_hr": char_kg_hr,
        "centrate_m3_hr": centrate_m3_hr,
        "effective_hours_yr": effective_hours
    }


# ============================================================================
# Option B: Co-feed Routing and Thermal Balance
# ============================================================================


class CofeedRoutingResult(NamedTuple):
    """Result of co-feed dryer bypass routing decision."""
    bypass_mode: bool           # True = bypass dryer, feed direct to pyro
    cofeed_to_dryer_kgds: float # Mass routed through dryer
    cofeed_bypass_kgds: float   # Mass bypassing dryer (direct to pyro)
    mode_changed: bool          # True if routing changed this timestep


def calc_cofeed_routing(
    cofeed_kgds: float,
    cofeed_ts: float,
    prior_bypass_mode: bool,
    bypass_ts_high: float = 0.70,
    bypass_ts_low: float = 0.60
) -> CofeedRoutingResult:
    """
    Determine co-feed routing with hysteresis.
    
    Routing decision:
        - TS >= bypass_ts_high (0.70): bypass dryer, feed directly to pyro
        - TS <= bypass_ts_low (0.60): route through dryer
        - In between: hold prior state (hysteresis band)
    
    This prevents flip-flopping and preserves Option B energy advantage.
    
    Args:
        cofeed_kgds: Co-feed mass (dry solids basis)
        cofeed_ts: Co-feed total solids fraction
        prior_bypass_mode: Previous routing state
        bypass_ts_high: TS threshold to enable bypass
        bypass_ts_low: TS threshold to disable bypass
    
    Returns:
        CofeedRoutingResult with routing decision and mass split
    """
    validate_non_negative(cofeed_kgds, "cofeed_kgds")
    validate_fraction(cofeed_ts, "cofeed_ts")
    
    # Apply hysteresis logic
    if cofeed_ts >= bypass_ts_high:
        new_bypass_mode = True
    elif cofeed_ts <= bypass_ts_low:
        new_bypass_mode = False
    else:
        # In hysteresis band - hold prior state
        new_bypass_mode = prior_bypass_mode
    
    mode_changed = new_bypass_mode != prior_bypass_mode
    
    # Route all co-feed based on current mode
    if new_bypass_mode:
        return CofeedRoutingResult(
            bypass_mode=True,
            cofeed_to_dryer_kgds=0.0,
            cofeed_bypass_kgds=cofeed_kgds,
            mode_changed=mode_changed
        )
    else:
        return CofeedRoutingResult(
            bypass_mode=False,
            cofeed_to_dryer_kgds=cofeed_kgds,
            cofeed_bypass_kgds=0.0,
            mode_changed=mode_changed
        )


class OptionBThermalResult(NamedTuple):
    """Result of Option B thermal balance calculation."""
    # Dryer (septage cake + any wet co-feed)
    dryer_feed_septage_kgds: float
    dryer_feed_cofeed_kgds: float
    dryer_water_evap_kg: float
    dryer_duty_mj: float
    
    # Pyrolysis (dried septage + dried co-feed + bypass co-feed)
    pyro_feed_septage_kgds: float
    pyro_feed_cofeed_kgds: float
    
    # Char production by source
    char_septage_kg: float
    char_cofeed_kg: float
    
    # Gas/condensate
    gas_total_kg: float
    condensate_total_kg: float
    
    # Energy
    syngas_septage_mj: float
    syngas_cofeed_mj: float
    syngas_total_mj: float
    pyro_duty_mj: float
    
    # Net balance
    net_heat_mj: float
    self_sufficiency_ratio: float
    heat_deficit: bool
    aux_fuel_mj: float


def calc_option_b_thermal(
    # Septage stream (always through dryer)
    septage_cake_kgds: float,
    septage_cake_ts: float,
    # Co-feed stream (may bypass dryer)
    cofeed_kgds: float,
    cofeed_ts: float,
    cofeed_bypass_mode: bool,
    # Dryer parameters
    dried_ts: float,
    dryer_energy_kwh_per_kg_water: float,
    dryer_thermal_efficiency: float,
    # Pyrolysis parameters (septage)
    yield_char_sept: float,
    yield_gas_sept: float,
    yield_cond_sept: float,
    lhv_syngas_sept_mj_kg: float,
    # Pyrolysis parameters (co-feed)
    yield_char_cofeed: float,
    yield_gas_cofeed: float,
    yield_cond_cofeed: float,
    lhv_syngas_cofeed_mj_kg: float,
    # Common pyrolysis parameters
    heat_requirement_mj_kgds: float,
    syngas_recovery_efficiency: float,
) -> OptionBThermalResult:
    """
    Calculate Option B thermal balance with dryer bypass.
    
    Stream architecture:
        Septage cake → Dryer → Pyrolysis (always)
        Co-feed (if bypass) → Pyrolysis direct (no dryer load)
        Co-feed (if wet) → Dryer → Pyrolysis
    
    This is the core physics that makes Option B work:
    dry co-feed contributes energy without adding dryer load.
    
    Args:
        septage_cake_kgds: Septage cake mass (dry solids)
        septage_cake_ts: Septage cake total solids (e.g., 0.20)
        cofeed_kgds: Co-feed mass (dry solids)
        cofeed_ts: Co-feed total solids (e.g., 0.85)
        cofeed_bypass_mode: True if co-feed bypasses dryer
        dried_ts: Target dried solids fraction (e.g., 0.75)
        dryer_energy_kwh_per_kg_water: Specific dryer energy
        dryer_thermal_efficiency: Dryer thermal efficiency
        yield_char_sept: Septage char yield (mass fraction)
        yield_gas_sept: Septage gas yield
        yield_cond_sept: Septage condensate yield
        lhv_syngas_sept_mj_kg: Septage syngas LHV
        yield_char_cofeed: Co-feed char yield
        yield_gas_cofeed: Co-feed gas yield
        yield_cond_cofeed: Co-feed condensate yield
        lhv_syngas_cofeed_mj_kg: Co-feed syngas LHV
        heat_requirement_mj_kgds: Pyrolysis heat requirement
        syngas_recovery_efficiency: Syngas energy recovery fraction
    
    Returns:
        OptionBThermalResult with complete energy balance
    """
    # ========================================================================
    # DRYER: Septage always goes through dryer, co-feed only if wet
    # ========================================================================
    
    # Septage drying
    # Clamp to ≥0 to handle edge case where cake is drier than target
    if septage_cake_kgds > 0:
        if septage_cake_ts >= dried_ts:
            # Septage already drier than target - no evaporation needed
            sept_water_evap_kg = 0.0
        else:
            sept_cake_total_kg = septage_cake_kgds / septage_cake_ts
            sept_cake_water_kg = sept_cake_total_kg - septage_cake_kgds
            sept_dried_total_kg = septage_cake_kgds / dried_ts
            sept_dried_water_kg = sept_dried_total_kg - septage_cake_kgds
            sept_water_evap_kg = max(0.0, sept_cake_water_kg - sept_dried_water_kg)
    else:
        sept_water_evap_kg = 0.0
    
    # Co-feed drying (only if not bypassing)
    # Clamp to ≥0 to handle edge case where co-feed is drier than target
    if not cofeed_bypass_mode and cofeed_kgds > 0:
        if cofeed_ts >= dried_ts:
            # Co-feed already drier than target - no evaporation needed
            cofeed_water_evap_kg = 0.0
            cofeed_to_dryer_kgds = 0.0  # effectively bypassing
        else:
            cofeed_total_kg = cofeed_kgds / cofeed_ts
            cofeed_water_kg = cofeed_total_kg - cofeed_kgds
            cofeed_dried_total_kg = cofeed_kgds / dried_ts
            cofeed_dried_water_kg = cofeed_dried_total_kg - cofeed_kgds
            cofeed_water_evap_kg = max(0.0, cofeed_water_kg - cofeed_dried_water_kg)
            cofeed_to_dryer_kgds = cofeed_kgds
    else:
        cofeed_water_evap_kg = 0.0
        cofeed_to_dryer_kgds = 0.0
    
    total_water_evap_kg = sept_water_evap_kg + cofeed_water_evap_kg
    
    # Dryer duty
    dryer_duty_kwh = total_water_evap_kg * dryer_energy_kwh_per_kg_water / dryer_thermal_efficiency
    dryer_duty_mj = dryer_duty_kwh * 3.6
    
    # ========================================================================
    # PYROLYSIS: Two parallel streams with different yields/LHVs
    # ========================================================================
    
    # Septage pyrolysis (from dried septage)
    sept_dried_total_kg = septage_cake_kgds / dried_ts if septage_cake_kgds > 0 else 0.0
    char_sept_kg = sept_dried_total_kg * yield_char_sept
    gas_sept_kg = sept_dried_total_kg * yield_gas_sept
    cond_sept_kg = sept_dried_total_kg * yield_cond_sept
    syngas_sept_mj = gas_sept_kg * lhv_syngas_sept_mj_kg * syngas_recovery_efficiency
    
    # Co-feed pyrolysis
    if cofeed_bypass_mode and cofeed_kgds > 0:
        # Bypass: co-feed enters at its native TS (assumed dry enough for direct feed)
        cofeed_total_kg = cofeed_kgds / cofeed_ts
        cofeed_to_pyro_kgds = cofeed_kgds
    elif not cofeed_bypass_mode and cofeed_kgds > 0:
        # Through dryer: co-feed is now at dried_ts
        cofeed_total_kg = cofeed_kgds / dried_ts
        cofeed_to_pyro_kgds = cofeed_kgds
    else:
        cofeed_total_kg = 0.0
        cofeed_to_pyro_kgds = 0.0
    
    char_cofeed_kg = cofeed_total_kg * yield_char_cofeed
    gas_cofeed_kg = cofeed_total_kg * yield_gas_cofeed
    cond_cofeed_kg = cofeed_total_kg * yield_cond_cofeed
    syngas_cofeed_mj = gas_cofeed_kg * lhv_syngas_cofeed_mj_kg * syngas_recovery_efficiency
    
    # Total outputs
    char_total_kg = char_sept_kg + char_cofeed_kg
    gas_total_kg = gas_sept_kg + gas_cofeed_kg
    cond_total_kg = cond_sept_kg + cond_cofeed_kg
    syngas_total_mj = syngas_sept_mj + syngas_cofeed_mj
    
    # Pyrolysis heat duty (proportional to DS processed)
    total_ds_to_pyro = septage_cake_kgds + cofeed_to_pyro_kgds
    pyro_duty_mj = total_ds_to_pyro * heat_requirement_mj_kgds
    
    # ========================================================================
    # NET ENERGY BALANCE
    # ========================================================================
    
    total_thermal_demand = dryer_duty_mj + pyro_duty_mj
    net_heat_mj = syngas_total_mj - total_thermal_demand
    
    self_sufficiency = syngas_total_mj / total_thermal_demand if total_thermal_demand > 0 else 1.0
    heat_deficit = net_heat_mj < 0
    aux_fuel_mj = -net_heat_mj if heat_deficit else 0.0
    
    return OptionBThermalResult(
        dryer_feed_septage_kgds=septage_cake_kgds,
        dryer_feed_cofeed_kgds=cofeed_to_dryer_kgds,
        dryer_water_evap_kg=total_water_evap_kg,
        dryer_duty_mj=dryer_duty_mj,
        pyro_feed_septage_kgds=septage_cake_kgds,
        pyro_feed_cofeed_kgds=cofeed_to_pyro_kgds,
        char_septage_kg=char_sept_kg,
        char_cofeed_kg=char_cofeed_kg,
        gas_total_kg=gas_total_kg,
        condensate_total_kg=cond_total_kg,
        syngas_septage_mj=syngas_sept_mj,
        syngas_cofeed_mj=syngas_cofeed_mj,
        syngas_total_mj=syngas_total_mj,
        pyro_duty_mj=pyro_duty_mj,
        net_heat_mj=net_heat_mj,
        self_sufficiency_ratio=self_sufficiency,
        heat_deficit=heat_deficit,
        aux_fuel_mj=aux_fuel_mj,
    )


class SegregatedCharRevenueResult(NamedTuple):
    """Result of segregated char revenue calculation."""
    char_septage_kg: float
    char_cofeed_kg: float
    tier_septage: int
    tier_cofeed: int
    price_septage_per_t: float
    price_cofeed_per_t: float
    revenue_septage: float
    revenue_cofeed: float
    revenue_total: float


def calc_segregated_char_revenue(
    char_septage_kg: float,
    char_cofeed_kg: float,
    tier_septage: int = 3,
    tier_cofeed: int = 2,
    tier_1_price: float = 500.0,
    tier_2_price: float = 225.0,
    tier_3_price: float = 75.0,
) -> SegregatedCharRevenueResult:
    """
    Calculate char revenue with segregated streams and tier pricing.
    
    Conservative defaults:
        - Septage char → Tier 3 ($75/t) - low value, restricted outlet
        - Co-feed char → Tier 2 ($225/t) - bulk soil amendment
    
    Tier 1 ($500/t premium) is opt-in only.
    """
    def get_price(tier: int) -> float:
        if tier == 1:
            return tier_1_price
        elif tier == 2:
            return tier_2_price
        else:
            return tier_3_price
    
    price_sept = get_price(tier_septage)
    price_cofeed = get_price(tier_cofeed)
    
    # Convert kg to tonnes for pricing
    revenue_sept = (char_septage_kg / 1000.0) * price_sept
    revenue_cofeed = (char_cofeed_kg / 1000.0) * price_cofeed
    
    return SegregatedCharRevenueResult(
        char_septage_kg=char_septage_kg,
        char_cofeed_kg=char_cofeed_kg,
        tier_septage=tier_septage,
        tier_cofeed=tier_cofeed,
        price_septage_per_t=price_sept,
        price_cofeed_per_t=price_cofeed,
        revenue_septage=revenue_sept,
        revenue_cofeed=revenue_cofeed,
        revenue_total=revenue_sept + revenue_cofeed,
    )


def calc_blended_quality_index(
    char_septage_kg: float,
    char_cofeed_kg: float,
    qi_septage: float = 0.8,
    qi_cofeed: float = 0.2,
) -> float:
    """
    Calculate mass-weighted quality index for blended char.
    
    QI_blend = (m_sept * QI_sept + m_co * QI_co) / (m_sept + m_co)
    
    Lower QI = better quality (0 = perfect, 1 = worst).
    Used to determine tier if blending is enabled.
    """
    total_mass = char_septage_kg + char_cofeed_kg
    if total_mass == 0:
        return 0.5  # Default mid-range
    
    return (char_septage_kg * qi_septage + char_cofeed_kg * qi_cofeed) / total_mass


# ============================================================================
# Value-Add Pathway Calculations
# ============================================================================

class StruviteRecoveryResult(NamedTuple):
    """Result of struvite (phosphorus) recovery calculation."""
    centrate_processed_m3: float
    phosphorus_recovered_kg: float
    struvite_produced_kg: float
    magnesium_consumed_kg: float
    revenue_annual: float
    avoided_p_discharge_kg: float


class AmmoniaStrippingResult(NamedTuple):
    """Result of ammonia stripping and capture calculation."""
    centrate_processed_m3: float
    nitrogen_recovered_kg: float
    ammonium_sulfate_produced_kg: float
    acid_consumed_kg: float
    steam_consumed_mj: float
    revenue_annual: float


class CHPResult(NamedTuple):
    """Result of combined heat and power calculation."""
    syngas_consumed_mj: float
    electricity_generated_kwh: float
    heat_recovered_mj: float
    grid_export_kwh: float
    grid_revenue_annual: float
    self_consumption_kwh: float


class HeatExportResult(NamedTuple):
    """Result of heat export calculation."""
    excess_heat_mj: float
    exported_heat_mj: float
    revenue_annual: float


class CharActivationResult(NamedTuple):
    """Result of char activation (upgrading) calculation."""
    char_input_kg: float
    activated_char_output_kg: float
    activation_yield: float
    steam_consumed_kg: float
    revenue_premium: float


class ScreeningsReuseResult(NamedTuple):
    """Result of screenings/grit/ash beneficial reuse calculation."""
    screenings_kg: float
    grit_kg: float
    ash_kg: float
    total_reuse_kg: float
    avoided_disposal_cost: float
    reuse_revenue: float


class CarbonCreditResult(NamedTuple):
    """Result of carbon credit calculation."""
    char_carbon_kg: float
    sequestered_co2e_kg: float
    credits_claimable_tonnes: float
    credit_revenue_annual: float


def calc_struvite_recovery(
    centrate_m3_annual: float,
    p_concentration_mg_L: float,
    recovery_efficiency: float,
    mg_dose_ratio: float,
    struvite_revenue_per_tonne: float,
) -> StruviteRecoveryResult:
    """
    Calculate struvite (MgNH4PO4·6H2O) recovery from centrate.
    
    Stoichiometry: Mg + NH4 + PO4 → MgNH4PO4·6H2O
    MW ratio: P (31) → Struvite (245) = 7.9:1
    
    Args:
        centrate_m3_annual: Annual centrate volume
        p_concentration_mg_L: Phosphorus concentration in centrate
        recovery_efficiency: Fraction of P recovered (typically 0.80-0.90)
        mg_dose_ratio: Mg:P molar ratio (typically 1.2-1.5)
        struvite_revenue_per_tonne: Revenue per tonne struvite
    
    Returns:
        StruviteRecoveryResult with mass and revenue outputs
    """
    # P mass in centrate (mg/L = g/m³)
    p_in_kg = centrate_m3_annual * p_concentration_mg_L / 1000.0
    
    # P recovered
    p_recovered_kg = p_in_kg * recovery_efficiency
    
    # Struvite produced (MW ratio ~7.9:1)
    struvite_kg = p_recovered_kg * 7.9
    
    # Mg consumed (MW Mg=24, MW P=31, molar ratio applied)
    mg_kg = p_recovered_kg * (24.0 / 31.0) * mg_dose_ratio
    
    # Revenue
    revenue = (struvite_kg / 1000.0) * struvite_revenue_per_tonne
    
    return StruviteRecoveryResult(
        centrate_processed_m3=centrate_m3_annual,
        phosphorus_recovered_kg=p_recovered_kg,
        struvite_produced_kg=struvite_kg,
        magnesium_consumed_kg=mg_kg,
        revenue_annual=revenue,
        avoided_p_discharge_kg=p_recovered_kg,
    )


def calc_ammonia_stripping(
    centrate_m3_annual: float,
    n_concentration_mg_L: float,
    recovery_efficiency: float,
    acid_consumption_kg_per_kg_n: float,
    steam_mj_per_m3: float,
    ammonium_sulfate_revenue_per_tonne: float,
) -> AmmoniaStrippingResult:
    """
    Calculate ammonia stripping and capture as ammonium sulfate.
    
    2NH3 + H2SO4 → (NH4)2SO4
    
    Args:
        centrate_m3_annual: Annual centrate volume
        n_concentration_mg_L: NH4-N concentration in centrate
        recovery_efficiency: Fraction of N recovered
        acid_consumption_kg_per_kg_n: kg H2SO4 per kg N
        steam_mj_per_m3: Steam requirement per m³ centrate
        ammonium_sulfate_revenue_per_tonne: Revenue per tonne (NH4)2SO4
    
    Returns:
        AmmoniaStrippingResult with outputs
    """
    # N mass in centrate
    n_in_kg = centrate_m3_annual * n_concentration_mg_L / 1000.0
    
    # N recovered
    n_recovered_kg = n_in_kg * recovery_efficiency
    
    # Ammonium sulfate: N content ~21%, so kg AS = kg N / 0.21
    ammonium_sulfate_kg = n_recovered_kg / 0.21
    
    # Acid consumed
    acid_kg = n_recovered_kg * acid_consumption_kg_per_kg_n
    
    # Steam
    steam_mj = centrate_m3_annual * steam_mj_per_m3
    
    # Revenue
    revenue = (ammonium_sulfate_kg / 1000.0) * ammonium_sulfate_revenue_per_tonne
    
    return AmmoniaStrippingResult(
        centrate_processed_m3=centrate_m3_annual,
        nitrogen_recovered_kg=n_recovered_kg,
        ammonium_sulfate_produced_kg=ammonium_sulfate_kg,
        acid_consumed_kg=acid_kg,
        steam_consumed_mj=steam_mj,
        revenue_annual=revenue,
    )


def calc_syngas_chp(
    syngas_energy_annual_mj: float,
    process_heat_demand_mj: float,
    electrical_efficiency: float,
    thermal_efficiency: float,
    site_power_demand_kwh: float,
    grid_export_enabled: bool,
    export_rate_per_kwh: float,
) -> CHPResult:
    """
    Calculate combined heat and power from syngas.
    
    Priority: Process heat first, then CHP on excess syngas.
    
    Args:
        syngas_energy_annual_mj: Total syngas energy available
        process_heat_demand_mj: Heat required for dryer + pyrolysis
        electrical_efficiency: Syngas → electricity efficiency
        thermal_efficiency: Syngas → usable heat efficiency
        site_power_demand_kwh: Annual site electrical demand
        grid_export_enabled: Whether grid export is permitted
        export_rate_per_kwh: Grid export rate ($/kWh)
    
    Returns:
        CHPResult with power and revenue outputs
    """
    # Syngas available for CHP (after process heat)
    excess_syngas_mj = max(0.0, syngas_energy_annual_mj - process_heat_demand_mj)
    
    # CHP outputs
    electricity_kwh = excess_syngas_mj * electrical_efficiency / 3.6  # MJ → kWh
    heat_recovered_mj = excess_syngas_mj * thermal_efficiency
    
    # Self-consumption vs export
    self_consumption_kwh = min(electricity_kwh, site_power_demand_kwh)
    grid_export_kwh = electricity_kwh - self_consumption_kwh if grid_export_enabled else 0.0
    
    # Revenue from grid export only
    grid_revenue = grid_export_kwh * export_rate_per_kwh
    
    return CHPResult(
        syngas_consumed_mj=excess_syngas_mj,
        electricity_generated_kwh=electricity_kwh,
        heat_recovered_mj=heat_recovered_mj,
        grid_export_kwh=grid_export_kwh,
        grid_revenue_annual=grid_revenue,
        self_consumption_kwh=self_consumption_kwh,
    )


def calc_heat_export(
    excess_heat_mj: float,
    exportable_fraction: float,
    heat_rate_per_gj: float,
) -> HeatExportResult:
    """
    Calculate revenue from exporting excess heat.
    
    Args:
        excess_heat_mj: Available excess heat after process use
        exportable_fraction: Fraction that can be exported (logistics)
        heat_rate_per_gj: Revenue rate per GJ exported
    
    Returns:
        HeatExportResult with export volumes and revenue
    """
    exported_mj = excess_heat_mj * exportable_fraction
    exported_gj = exported_mj / 1000.0
    
    revenue = exported_gj * heat_rate_per_gj
    
    return HeatExportResult(
        excess_heat_mj=excess_heat_mj,
        exported_heat_mj=exported_mj,
        revenue_annual=revenue,
    )


def calc_char_activation(
    char_input_kg: float,
    activation_yield: float,
    steam_kg_per_kg_char: float,
    base_price_per_tonne: float,
    activated_premium_per_tonne: float,
) -> CharActivationResult:
    """
    Calculate char activation (steam or CO2) to produce activated biochar.
    
    Args:
        char_input_kg: Mass of char to activate
        activation_yield: Mass yield (output/input)
        steam_kg_per_kg_char: Steam consumption ratio
        base_price_per_tonne: Base char price (Tier-2)
        activated_premium_per_tonne: Price premium for activated char
    
    Returns:
        CharActivationResult with outputs and premium revenue
    """
    activated_kg = char_input_kg * activation_yield
    steam_kg = char_input_kg * steam_kg_per_kg_char
    
    # Revenue premium (additional revenue over selling as bulk char)
    premium_revenue = (activated_kg / 1000.0) * activated_premium_per_tonne
    
    return CharActivationResult(
        char_input_kg=char_input_kg,
        activated_char_output_kg=activated_kg,
        activation_yield=activation_yield,
        steam_consumed_kg=steam_kg,
        revenue_premium=premium_revenue,
    )


def calc_screenings_reuse(
    septage_processed_m3: float,
    char_produced_kg: float,
    screenings_fraction: float,
    grit_fraction: float,
    ash_fraction: float,
    density_kg_m3: float,
    landfill_cost_per_tonne: float,
    reuse_credit_per_tonne: float,
) -> ScreeningsReuseResult:
    """
    Calculate beneficial reuse of screenings, grit, and ash.
    
    Args:
        septage_processed_m3: Total septage processed
        char_produced_kg: Total char produced
        screenings_fraction: Screenings as fraction of septage mass
        grit_fraction: Grit as fraction of septage mass
        ash_fraction: Ash as fraction of char mass
        density_kg_m3: Septage density
        landfill_cost_per_tonne: Cost if landfilled
        reuse_credit_per_tonne: Credit if beneficially reused
    
    Returns:
        ScreeningsReuseResult with masses and economics
    """
    septage_mass_kg = septage_processed_m3 * density_kg_m3
    
    screenings_kg = septage_mass_kg * screenings_fraction
    grit_kg = septage_mass_kg * grit_fraction
    ash_kg = char_produced_kg * ash_fraction
    
    total_kg = screenings_kg + grit_kg + ash_kg
    total_tonnes = total_kg / 1000.0
    
    avoided_disposal = total_tonnes * landfill_cost_per_tonne
    reuse_revenue = total_tonnes * reuse_credit_per_tonne
    
    return ScreeningsReuseResult(
        screenings_kg=screenings_kg,
        grit_kg=grit_kg,
        ash_kg=ash_kg,
        total_reuse_kg=total_kg,
        avoided_disposal_cost=avoided_disposal,
        reuse_revenue=reuse_revenue,
    )


def calc_carbon_credits(
    char_carbon_kg: float,
    permanence_discount: float,
    credit_price_per_tonne_co2e: float,
) -> CarbonCreditResult:
    """
    Calculate carbon credit revenue from char sequestration.
    
    CO2e = char_carbon * 44/12 (stoichiometric)
    
    Args:
        char_carbon_kg: Carbon mass in char
        permanence_discount: Discount for permanence uncertainty (e.g., 0.80)
        credit_price_per_tonne_co2e: Carbon credit price
    
    Returns:
        CarbonCreditResult with sequestration and revenue
    """
    # CO2 equivalent (C → CO2 = 44/12 = 3.67)
    co2e_kg = char_carbon_kg * 3.67
    
    # Apply permanence discount
    claimable_kg = co2e_kg * permanence_discount
    claimable_tonnes = claimable_kg / 1000.0
    
    revenue = claimable_tonnes * credit_price_per_tonne_co2e
    
    return CarbonCreditResult(
        char_carbon_kg=char_carbon_kg,
        sequestered_co2e_kg=co2e_kg,
        credits_claimable_tonnes=claimable_tonnes,
        credit_revenue_annual=revenue,
    )

