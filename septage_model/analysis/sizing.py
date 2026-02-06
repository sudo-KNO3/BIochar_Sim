"""
Sizing Module - Buffer tank sizing and steady-state flow calculations.

Implements equations from specification:
    - EQ tank sized for seasonal peak + autonomy
    - Centrate tank sized for weekend accumulation + discharge constraint
    - Cake/dried/char storage sized for thermal outage buffer
"""

from dataclasses import dataclass
from typing import Optional, List, Tuple
import math

from ..core.parameters import (
    ModelParameters,
    ServiceAreaParams,
    DeWateringParams,
    DryerParams,
    PyrolysisParams,
    BufferStorageParams,
    DischargeParams,
    OperatingParams,
)


@dataclass
class SteadyStateFlows:
    """Steady-state mass flow rates through the system."""
    septage_m3_hr: float
    septage_kgds_hr: float
    cake_kgds_hr: float
    dryer_feed_kgds_hr: float
    pyro_feed_kgds_hr: float
    char_kg_hr: float
    centrate_m3_hr: float
    effective_hours_yr: float
    
    annual_septage_m3: float = 0.0
    annual_char_tonnes: float = 0.0
    annual_centrate_m3: float = 0.0
    
    peak_septage_m3_hr: float = 0.0
    peak_centrate_m3_hr: float = 0.0


@dataclass
class SystemSizing:
    """Required equipment and buffer sizes."""
    eq_tank_m3: float
    centrate_tank_m3: float
    cake_storage_kgds: float
    dried_storage_kgds: float
    char_storage_kg: float
    
    dewatering_capacity_m3_hr: float
    dryer_capacity_kgds_hr: float
    pyro_capacity_kgds_hr: float
    
    permit_discharge_rate_m3_hr: float
    actual_discharge_rate_m3_hr: float
    discharge_utilization: float
    
    flows: SteadyStateFlows = None


@dataclass
class ConstraintCheck:
    """Result of constraint/permit checking."""
    name: str
    required: float
    available: float
    margin_percent: float
    passes: bool
    warning: str = ""


def calc_steady_state_flows(params: ModelParameters) -> SteadyStateFlows:
    """
    Calculate steady-state mass flows through the system.
    
    Uses locked baseline parameters to determine design flows.
    """
    sa = params.service_area
    dw = params.dewatering
    dr = params.dryer
    py = params.pyrolysis
    op = params.operating
    
    annual_m3 = sa.annual_septage_m3
    effective_hrs = op.effective_hours_per_year()
    
    avg_septage_m3_hr = annual_m3 / 8760
    avg_septage_kg_hr = avg_septage_m3_hr * sa.density_kg_m3
    avg_ds_kg_hr = avg_septage_kg_hr * sa.ts_fraction_mean
    
    peak_month_mult = max(sa.monthly_multipliers)
    peak_hour_mult = max(sa.hourly_pattern) / (sum(sa.hourly_pattern) / 24) if sum(sa.hourly_pattern) > 0 else 1.0
    peak_dow_mult = max(sa.dow_multipliers) / (sum(sa.dow_multipliers) / 7)
    
    peak_septage_m3_hr = avg_septage_m3_hr * peak_month_mult * peak_hour_mult * peak_dow_mult
    
    ds_captured_hr = avg_ds_kg_hr * dw.solids_capture
    
    thermal_factor = 8760 / effective_hrs
    dryer_feed_kgds_hr = ds_captured_hr * thermal_factor
    
    pyro_feed_kgds_hr = dryer_feed_kgds_hr
    
    dried_total_kg_hr = pyro_feed_kgds_hr / dr.dried_ts_fraction
    char_kg_hr = dried_total_kg_hr * py.yield_char
    
    cake_total_kg_hr = ds_captured_hr / dw.cake_ts_fraction
    centrate_m3_hr = avg_septage_m3_hr - (cake_total_kg_hr / sa.density_kg_m3)
    peak_centrate_m3_hr = centrate_m3_hr * peak_month_mult
    
    annual_char_tonnes = char_kg_hr * effective_hrs / 1000
    annual_centrate_m3 = centrate_m3_hr * 8760
    
    return SteadyStateFlows(
        septage_m3_hr=avg_septage_m3_hr,
        septage_kgds_hr=avg_ds_kg_hr,
        cake_kgds_hr=ds_captured_hr,
        dryer_feed_kgds_hr=dryer_feed_kgds_hr,
        pyro_feed_kgds_hr=pyro_feed_kgds_hr,
        char_kg_hr=char_kg_hr,
        centrate_m3_hr=centrate_m3_hr,
        effective_hours_yr=effective_hrs,
        annual_septage_m3=annual_m3,
        annual_char_tonnes=annual_char_tonnes,
        annual_centrate_m3=annual_centrate_m3,
        peak_septage_m3_hr=peak_septage_m3_hr,
        peak_centrate_m3_hr=peak_centrate_m3_hr,
    )


def calc_required_discharge_rate(
    centrate_m3_hr: float,
    discharge_hours_per_week: float
) -> float:
    """
    Calculate required discharge rate to clear weekly centrate.
    
    Q_req = (centrate_m3_hr * 168) / discharge_hours_per_week
    """
    weekly_centrate_m3 = centrate_m3_hr * 168
    return weekly_centrate_m3 / discharge_hours_per_week


def calc_eq_tank_size(
    avg_septage_m3_hr: float,
    peak_factor: float,
    autonomy_days: float,
    min_level_fraction: float
) -> float:
    """
    Size EQ tank for seasonal peak + autonomy buffer.
    
    V_eq = avg_rate * 24 * autonomy * peak_factor / (1 - min_level)
    """
    daily_volume = avg_septage_m3_hr * 24 * peak_factor
    usable_fraction = 1.0 - min_level_fraction
    return (daily_volume * autonomy_days) / usable_fraction


def calc_centrate_tank_size(
    centrate_m3_hr: float,
    autonomy_days: float,
    weekend_hours: float = 56
) -> float:
    """
    Size centrate tank for weekend accumulation + buffer.
    
    Must hold:
    - Weekend accumulation (no discharge Sat-Sun)
    - Additional autonomy buffer
    """
    weekend_volume = centrate_m3_hr * weekend_hours
    autonomy_volume = centrate_m3_hr * 24 * autonomy_days
    return weekend_volume + autonomy_volume


def calc_cake_storage_size(
    cake_kgds_hr: float,
    autonomy_hours: float,
    dryer_downtime_factor: float = 1.2
) -> float:
    """
    Size cake storage for dryer outage buffer.
    
    Must accumulate cake during dryer downtime.
    """
    return cake_kgds_hr * autonomy_hours * dryer_downtime_factor


def calc_dried_storage_size(
    dryer_output_kgds_hr: float,
    autonomy_hours: float
) -> float:
    """
    Size dried material storage for pyrolysis feed buffer.
    """
    return dryer_output_kgds_hr * autonomy_hours


def calc_char_storage_size(
    char_kg_hr: float,
    autonomy_days: float
) -> float:
    """
    Size char storage for shipping logistics buffer.
    """
    return char_kg_hr * 24 * autonomy_days


def calc_system_sizing(params: ModelParameters) -> SystemSizing:
    """
    Calculate complete system sizing based on parameters.
    
    Returns all buffer sizes and equipment capacities.
    """
    flows = calc_steady_state_flows(params)
    buf = params.buffer_storage
    dis = params.discharge
    dw = params.dewatering
    dr = params.dryer
    py = params.pyrolysis
    
    peak_factor = max(params.service_area.monthly_multipliers)
    eq_tank_m3 = calc_eq_tank_size(
        flows.septage_m3_hr,
        peak_factor,
        buf.eq_autonomy_days,
        buf.eq_min_level_fraction
    )
    
    centrate_tank_m3 = calc_centrate_tank_size(
        flows.centrate_m3_hr,
        buf.centrate_autonomy_days
    )
    
    cake_storage_kgds = calc_cake_storage_size(
        flows.cake_kgds_hr,
        buf.cake_autonomy_hours
    )
    
    dried_storage_kgds = calc_dried_storage_size(
        flows.dryer_feed_kgds_hr,
        buf.dried_autonomy_hours
    )
    
    char_storage_kg = calc_char_storage_size(
        flows.char_kg_hr,
        buf.char_autonomy_days
    )
    
    dewatering_capacity = flows.septage_m3_hr * peak_factor * 1.25
    dewatering_capacity = max(dewatering_capacity, dw.max_throughput_m3_hr * 0.5)
    
    dryer_capacity = flows.dryer_feed_kgds_hr * 1.25
    dryer_capacity = max(dryer_capacity, dr.max_throughput_kgds_hr * 0.5)
    
    pyro_capacity = flows.pyro_feed_kgds_hr * 1.25
    pyro_capacity = max(pyro_capacity, py.max_throughput_kgds_hr * 0.5)
    
    discharge_hours = dis.hours_per_week()
    required_discharge = calc_required_discharge_rate(flows.centrate_m3_hr, discharge_hours)
    discharge_utilization = required_discharge / dis.q_permit_m3_hr
    
    return SystemSizing(
        eq_tank_m3=eq_tank_m3,
        centrate_tank_m3=centrate_tank_m3,
        cake_storage_kgds=cake_storage_kgds,
        dried_storage_kgds=dried_storage_kgds,
        char_storage_kg=char_storage_kg,
        dewatering_capacity_m3_hr=dewatering_capacity,
        dryer_capacity_kgds_hr=dryer_capacity,
        pyro_capacity_kgds_hr=pyro_capacity,
        permit_discharge_rate_m3_hr=dis.q_permit_m3_hr,
        actual_discharge_rate_m3_hr=required_discharge,
        discharge_utilization=discharge_utilization,
        flows=flows,
    )


def check_permit_constraints(sizing: SystemSizing) -> List[ConstraintCheck]:
    """
    Check all permit and physical constraints.
    
    Returns list of constraint checks with pass/fail status.
    """
    checks = []
    
    checks.append(ConstraintCheck(
        name="Centrate Discharge Rate",
        required=sizing.actual_discharge_rate_m3_hr,
        available=sizing.permit_discharge_rate_m3_hr,
        margin_percent=(sizing.permit_discharge_rate_m3_hr - sizing.actual_discharge_rate_m3_hr) 
                       / sizing.permit_discharge_rate_m3_hr * 100,
        passes=sizing.actual_discharge_rate_m3_hr <= sizing.permit_discharge_rate_m3_hr,
        warning="Insufficient permit discharge capacity" if sizing.discharge_utilization > 1.0 else ""
    ))
    
    checks.append(ConstraintCheck(
        name="Discharge Utilization",
        required=sizing.discharge_utilization * 100,
        available=100.0,
        margin_percent=(1.0 - sizing.discharge_utilization) * 100,
        passes=sizing.discharge_utilization <= 0.90,
        warning="High discharge utilization - limited margin" if sizing.discharge_utilization > 0.80 else ""
    ))
    
    return checks


def size_equipment(params: ModelParameters) -> dict:
    """
    Size all major equipment with safety factors.
    
    Returns dict of equipment sizes and costs.
    """
    sizing = calc_system_sizing(params)
    cap = params.capex_scaling
    
    def scale_cost(ref_cost: float, ref_size: float, actual_size: float, exp: float) -> float:
        return ref_cost * (actual_size / ref_size) ** exp
    
    eq_tank_cost = scale_cost(
        cap.eq_tank_ref_cost, cap.eq_tank_ref_size_m3,
        sizing.eq_tank_m3, cap.eq_tank_scaling_exp
    )
    
    cen_tank_cost = scale_cost(
        cap.cen_tank_ref_cost, cap.cen_tank_ref_size_m3,
        sizing.centrate_tank_m3, cap.cen_tank_scaling_exp
    )
    
    dewatering_cost = scale_cost(
        cap.dewatering_ref_cost, cap.dewatering_ref_size,
        sizing.dewatering_capacity_m3_hr, cap.dewatering_scaling_exp
    )
    
    dryer_cost = scale_cost(
        cap.dryer_ref_cost, cap.dryer_ref_size,
        sizing.dryer_capacity_kgds_hr, cap.dryer_scaling_exp
    )
    
    pyro_cost = scale_cost(
        cap.pyro_ref_cost, cap.pyro_ref_size,
        sizing.pyro_capacity_kgds_hr, cap.pyro_scaling_exp
    )
    
    equipment_total = eq_tank_cost + cen_tank_cost + dewatering_cost + dryer_cost + pyro_cost
    
    site_work = equipment_total * cap.site_work_fraction
    electrical = equipment_total * cap.electrical_fraction
    instrumentation = equipment_total * cap.instrumentation_fraction
    engineering = equipment_total * cap.engineering_fraction
    contingency = equipment_total * cap.contingency_fraction
    
    total_capex = equipment_total + site_work + electrical + instrumentation + engineering + contingency
    
    return {
        "sizing": sizing,
        "equipment_costs": {
            "eq_tank": eq_tank_cost,
            "centrate_tank": cen_tank_cost,
            "dewatering": dewatering_cost,
            "dryer": dryer_cost,
            "pyrolysis": pyro_cost,
            "total_equipment": equipment_total,
        },
        "indirect_costs": {
            "site_work": site_work,
            "electrical": electrical,
            "instrumentation": instrumentation,
            "engineering": engineering,
            "contingency": contingency,
        },
        "total_capex": total_capex,
    }
