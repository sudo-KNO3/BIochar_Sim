"""
Core State Module - Mutable state containers for simulation.
State evolves, Parameters do not.

State containers track:
    - Tank levels (EQ, centrate, cake, dried, char)
    - Queue status (trucks waiting)
    - Controller state (current setpoints, mode)
    - Thermal system (dryer/pyrolysis operating status)
    - Discharge window tracking
"""

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum, auto


class SystemMode(Enum):
    NORMAL = auto()
    STANDBY = auto()
    MAINTENANCE = auto()
    OUTAGE = auto()
    WARMUP = auto()
    COOLDOWN = auto()


class OverflowAction(Enum):
    NONE = auto()
    DIVERT_EXTERNAL = auto()
    REJECT_ARRIVAL = auto()


@dataclass
class TankState:
    """Generic buffer tank state."""
    level_m3: float = 0.0
    capacity_m3: float = 100.0
    min_level_m3: float = 0.0
    
    overflow_count: int = 0
    overflow_volume_m3: float = 0.0
    underflow_count: int = 0
    
    def fill_fraction(self) -> float:
        usable = self.capacity_m3 - self.min_level_m3
        current = self.level_m3 - self.min_level_m3
        return max(0.0, min(1.0, current / usable)) if usable > 0 else 0.0
    
    def available_capacity_m3(self) -> float:
        return max(0.0, self.capacity_m3 - self.level_m3)
    
    def available_volume_m3(self) -> float:
        return max(0.0, self.level_m3 - self.min_level_m3)


@dataclass
class SolidsTankState(TankState):
    """Solids storage (cake, dried, char) tracking kg DS."""
    level_kgds: float = 0.0
    capacity_kgds: float = 5000.0
    min_level_kgds: float = 0.0
    
    def fill_fraction(self) -> float:
        usable = self.capacity_kgds - self.min_level_kgds
        current = self.level_kgds - self.min_level_kgds
        return max(0.0, min(1.0, current / usable)) if usable > 0 else 0.0
    
    def available_capacity_kgds(self) -> float:
        return max(0.0, self.capacity_kgds - self.level_kgds)
    
    def available_mass_kgds(self) -> float:
        return max(0.0, self.level_kgds - self.min_level_kgds)


@dataclass
class QueueState:
    """Truck queue state for M/G/1 queueing model."""
    trucks_in_queue: int = 0
    max_queue_length: int = 0
    total_arrivals: int = 0
    total_rejections: int = 0
    total_wait_time_min: float = 0.0
    max_wait_time_min: float = 0.0
    server_busy: bool = False
    current_service_end_time: float = 0.0
    
    def average_wait_time_min(self) -> float:
        served = self.total_arrivals - self.total_rejections
        if served <= 0:
            return 0.0
        return self.total_wait_time_min / served


@dataclass
class ControllerState:
    """Process controller state."""
    mode: SystemMode = SystemMode.NORMAL
    
    cake_setpoint_kgds: float = 0.0
    cake_feed_rate_kgds_hr: float = 0.0
    last_feed_change_time: float = 0.0
    
    dryer_on: bool = False
    dryer_on_since: float = 0.0
    dryer_off_since: float = 0.0
    
    pyro_on: bool = False
    pyro_on_since: float = 0.0
    pyro_off_since: float = 0.0
    
    integral_error_kgds_hr: float = 0.0
    last_error_kgds: float = 0.0
    
    cofeed_active: bool = False
    cofeed_rate_kgds_hr: float = 0.0


@dataclass
class ThermalSystemState:
    """Thermal system operating state."""
    dryer_feed_kgds_hr: float = 0.0
    dryer_output_kgds_hr: float = 0.0
    dryer_water_evap_kg_hr: float = 0.0
    dryer_heat_duty_mj_hr: float = 0.0
    dryer_temperature_c: float = 20.0
    
    pyro_feed_kgds_hr: float = 0.0
    pyro_char_output_kg_hr: float = 0.0
    pyro_gas_output_kg_hr: float = 0.0
    pyro_condensate_kg_hr: float = 0.0
    pyro_heat_duty_mj_hr: float = 0.0
    pyro_syngas_energy_mj_hr: float = 0.0
    pyro_temperature_c: float = 20.0
    
    net_heat_mj_hr: float = 0.0
    heat_deficit: bool = False
    
    operating_hours: float = 0.0
    downtime_hours: float = 0.0
    last_outage_time: float = 0.0


@dataclass
class DischargeState:
    """Centrate discharge tracking."""
    in_discharge_window: bool = False
    current_window_start: float = 0.0
    total_discharged_m3: float = 0.0
    weekly_discharged_m3: float = 0.0
    daily_discharged_m3: float = 0.0
    
    permit_violations: int = 0
    emergency_discharges: int = 0


@dataclass
class MassBalanceState:
    """Cumulative mass balance tracking for closure verification."""
    septage_in_m3: float = 0.0
    septage_in_kgds: float = 0.0
    cofeed_in_kgds: float = 0.0
    
    centrate_out_m3: float = 0.0
    centrate_ds_out_kgds: float = 0.0
    char_out_kg: float = 0.0
    gas_out_kg: float = 0.0
    condensate_out_kg: float = 0.0
    water_evap_kg: float = 0.0
    
    screenings_out_kg: float = 0.0
    overflow_m3: float = 0.0
    
    # Option B: Segregated char tracking by source
    char_septage_kg: float = 0.0
    char_cofeed_kg: float = 0.0
    
    # Option B: Co-feed routing tracking
    cofeed_to_dryer_kgds: float = 0.0
    cofeed_bypass_kgds: float = 0.0
    
    mass_balance_errors: List[float] = field(default_factory=list)
    max_abs_error: float = 0.0
    
    def check_closure(self, tolerance: float = 0.001) -> Tuple[bool, float]:
        total_in = self.septage_in_kgds + self.cofeed_in_kgds
        total_out = (
            self.centrate_ds_out_kgds +
            self.char_out_kg +
            self.gas_out_kg +
            self.condensate_out_kg +
            self.water_evap_kg +
            self.screenings_out_kg
        )
        
        if total_in == 0:
            return True, 0.0
        
        error = abs(total_in - total_out) / total_in
        return error < tolerance, error


@dataclass
class CarbonAccountingState:
    """Carbon accounting for credits/offsets."""
    total_carbon_in_kg: float = 0.0
    char_carbon_kg: float = 0.0
    sequestered_carbon_kg: float = 0.0
    emitted_carbon_kg: float = 0.0
    
    avoided_emissions_kgco2e: float = 0.0
    net_credits_tco2e: float = 0.0


# =============================================================================
# Pathway Execution State - Sequential State Management
# =============================================================================

@dataclass(frozen=True)
class PathwayExecutionState:
    """
    Immutable state container for sequential pathway evaluation.
    
    State flows through pathways in order: struvite → ammonia → CHP → heat_export
    → char_activation → screenings → carbon_credits
    
    Each pathway consumes from available resources and produces outputs.
    The frozen dataclass ensures state transitions are explicit via replace().
    
    Design philosophy:
        - Pathways consume from shared pools (state_{k+1} = F_{p_k}(state_k))
        - Disabled pathways pass state unchanged (no double-counting)
        - Mass/energy conservation is verifiable at each transition
    """
    # Centrate pool
    centrate_remaining_m3: float = 0.0
    p_concentration_mg_L: float = 0.0
    n_concentration_mg_L: float = 0.0
    
    # Energy pools
    syngas_remaining_mj: float = 0.0
    heat_low_remaining_mj: float = 0.0     # <100°C
    heat_medium_remaining_mj: float = 0.0  # 100-300°C
    heat_high_remaining_mj: float = 0.0    # >300°C
    
    # Solid pools
    char_remaining_kg: float = 0.0
    steam_remaining_kg: float = 0.0
    
    # Tracking
    pathways_executed: Tuple[str, ...] = ()
    
    def consume_syngas(self, mj: float) -> 'PathwayExecutionState':
        """Consume syngas, returning new state. Raises if insufficient."""
        if mj > self.syngas_remaining_mj + 1e-6:  # Small tolerance
            raise ValueError(
                f"Insufficient syngas: requested {mj:.1f} MJ, "
                f"available {self.syngas_remaining_mj:.1f} MJ"
            )
        return replace(self, syngas_remaining_mj=max(0, self.syngas_remaining_mj - mj))
    
    def consume_heat(self, mj: float, grade: str) -> 'PathwayExecutionState':
        """
        Consume heat of specified grade, returning new state.
        
        Higher grade heat can supply lower grade needs:
            HIGH → MEDIUM → LOW
        """
        grade = grade.upper()
        if grade == "LOW":
            # Can use any grade
            total = self.heat_low_remaining_mj + self.heat_medium_remaining_mj + self.heat_high_remaining_mj
            if mj > total + 1e-6:
                raise ValueError(f"Insufficient heat: requested {mj:.1f} MJ, available {total:.1f} MJ")
            # Consume from low first, then medium, then high
            remaining = mj
            low = max(0, self.heat_low_remaining_mj - remaining)
            remaining = max(0, remaining - self.heat_low_remaining_mj)
            medium = max(0, self.heat_medium_remaining_mj - remaining)
            remaining = max(0, remaining - self.heat_medium_remaining_mj)
            high = max(0, self.heat_high_remaining_mj - remaining)
            return replace(self, heat_low_remaining_mj=low, heat_medium_remaining_mj=medium, heat_high_remaining_mj=high)
        elif grade == "MEDIUM":
            # Can use medium or high
            total = self.heat_medium_remaining_mj + self.heat_high_remaining_mj
            if mj > total + 1e-6:
                raise ValueError(f"Insufficient medium+ heat: requested {mj:.1f} MJ, available {total:.1f} MJ")
            remaining = mj
            medium = max(0, self.heat_medium_remaining_mj - remaining)
            remaining = max(0, remaining - self.heat_medium_remaining_mj)
            high = max(0, self.heat_high_remaining_mj - remaining)
            return replace(self, heat_medium_remaining_mj=medium, heat_high_remaining_mj=high)
        elif grade == "HIGH":
            # Must use high grade
            if mj > self.heat_high_remaining_mj + 1e-6:
                raise ValueError(f"Insufficient high-grade heat: requested {mj:.1f} MJ, available {self.heat_high_remaining_mj:.1f} MJ")
            return replace(self, heat_high_remaining_mj=max(0, self.heat_high_remaining_mj - mj))
        else:
            raise ValueError(f"Unknown heat grade: {grade}")
    
    def reduce_p_concentration(self, fraction_removed: float) -> 'PathwayExecutionState':
        """Reduce P concentration by fraction removed (0-1)."""
        if not 0 <= fraction_removed <= 1:
            raise ValueError(f"Fraction must be 0-1, got {fraction_removed}")
        new_conc = self.p_concentration_mg_L * (1 - fraction_removed)
        return replace(self, p_concentration_mg_L=new_conc)
    
    def reduce_n_concentration(self, fraction_removed: float) -> 'PathwayExecutionState':
        """Reduce N concentration by fraction removed (0-1)."""
        if not 0 <= fraction_removed <= 1:
            raise ValueError(f"Fraction must be 0-1, got {fraction_removed}")
        new_conc = self.n_concentration_mg_L * (1 - fraction_removed)
        return replace(self, n_concentration_mg_L=new_conc)
    
    def allocate_char(self, kg: float) -> 'PathwayExecutionState':
        """Allocate char to a pathway, reducing available pool."""
        if kg > self.char_remaining_kg + 1e-6:
            raise ValueError(
                f"Insufficient char: requested {kg:.1f} kg, "
                f"available {self.char_remaining_kg:.1f} kg"
            )
        return replace(self, char_remaining_kg=max(0, self.char_remaining_kg - kg))
    
    def record_pathway(self, pathway_name: str) -> 'PathwayExecutionState':
        """Record that a pathway was executed."""
        return replace(self, pathways_executed=self.pathways_executed + (pathway_name,))
    
    @classmethod
    def from_operating_inputs(
        cls,
        centrate_m3: float,
        p_concentration_mg_L: float,
        n_concentration_mg_L: float,
        syngas_mj: float,
        char_kg: float,
        heat_low_mj: float = 0.0,
        heat_medium_mj: float = 0.0,
        heat_high_mj: float = 0.0,
        steam_kg: float = 0.0,
    ) -> 'PathwayExecutionState':
        """Create initial pathway state from operating inputs."""
        return cls(
            centrate_remaining_m3=centrate_m3,
            p_concentration_mg_L=p_concentration_mg_L,
            n_concentration_mg_L=n_concentration_mg_L,
            syngas_remaining_mj=syngas_mj,
            char_remaining_kg=char_kg,
            heat_low_remaining_mj=heat_low_mj,
            heat_medium_remaining_mj=heat_medium_mj,
            heat_high_remaining_mj=heat_high_mj,
            steam_remaining_kg=steam_kg,
        )


@dataclass
class EconomicState:
    """Running economic totals."""
    tipping_revenue: float = 0.0
    char_revenue: float = 0.0
    carbon_credit_revenue: float = 0.0
    
    electricity_cost: float = 0.0
    gas_cost: float = 0.0
    polymer_cost: float = 0.0
    disposal_cost: float = 0.0
    labor_cost: float = 0.0
    
    total_revenue: float = 0.0
    total_opex: float = 0.0
    net_operating_income: float = 0.0
    
    # Option B: Segregated char revenue tracking
    char_revenue_septage: float = 0.0   # Tier 3 revenue
    char_revenue_cofeed: float = 0.0    # Tier 2 revenue
    
    # Option B: Co-feed costs
    cofeed_purchase_cost: float = 0.0
    cofeed_transport_cost: float = 0.0
    
    # Option B: Regulatory costs
    compliance_cost_adder: float = 0.0


@dataclass
class CofeedRoutingState:
    """
    Option B: Co-feed dryer bypass routing state.
    
    Implements hysteresis to prevent flip-flopping:
        - TS >= 0.70: bypass dryer (feed direct to pyro)
        - TS <= 0.60: route through dryer
        - 0.60 < TS < 0.70: hold prior state
    """
    bypass_mode: bool = True            # Current routing (True = bypass dryer)
    last_ts_reading: float = 0.85       # Last measured TS
    
    # Cumulative tracking
    total_bypassed_kgds: float = 0.0
    total_to_dryer_kgds: float = 0.0
    mode_switches: int = 0              # Count of routing changes


@dataclass
class OptionBState:
    """
    Option B: Complete state container for solids-centric operation.
    
    Tracks co-feed routing, segregated char, and associated economics.
    """
    cofeed_routing: CofeedRoutingState = field(default_factory=CofeedRoutingState)
    
    # Current timestep flows
    cofeed_feed_kgds_hr: float = 0.0
    cofeed_to_pyro_direct_kgds_hr: float = 0.0
    cofeed_to_dryer_kgds_hr: float = 0.0
    
    # Pyrolysis source tracking
    pyro_feed_septage_kgds_hr: float = 0.0
    pyro_feed_cofeed_kgds_hr: float = 0.0
    
    # Char production by source
    char_septage_kg_hr: float = 0.0
    char_cofeed_kg_hr: float = 0.0
    
    # Energy contribution tracking
    syngas_from_septage_mj_hr: float = 0.0
    syngas_from_cofeed_mj_hr: float = 0.0


@dataclass
class SimulationState:
    """Complete simulation state container."""
    time_hr: float = 0.0
    timestep_hr: float = 1.0
    day_of_year: int = 1
    month: int = 1
    day_of_week: int = 0
    hour_of_day: int = 0
    year: int = 1
    
    eq_tank: TankState = field(default_factory=TankState)
    centrate_tank: TankState = field(default_factory=TankState)
    cake_storage: SolidsTankState = field(default_factory=SolidsTankState)
    dried_storage: SolidsTankState = field(default_factory=SolidsTankState)
    char_storage: SolidsTankState = field(default_factory=SolidsTankState)
    
    queue: QueueState = field(default_factory=QueueState)
    controller: ControllerState = field(default_factory=ControllerState)
    thermal: ThermalSystemState = field(default_factory=ThermalSystemState)
    discharge: DischargeState = field(default_factory=DischargeState)
    
    mass_balance: MassBalanceState = field(default_factory=MassBalanceState)
    carbon: CarbonAccountingState = field(default_factory=CarbonAccountingState)
    economic: EconomicState = field(default_factory=EconomicState)
    
    # Option B: Co-feed and segregated char state
    option_b: OptionBState = field(default_factory=OptionBState)
    
    alerts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def create_initial_state(
    eq_capacity_m3: float = 100.0,
    centrate_capacity_m3: float = 75.0,
    cake_capacity_kgds: float = 5000.0,
    dried_capacity_kgds: float = 2000.0,
    char_capacity_kgds: float = 10000.0,
    initial_eq_level_m3: float = 10.0,
    timestep_hr: float = 1.0
) -> SimulationState:
    """Create initial simulation state with specified tank sizes."""
    return SimulationState(
        timestep_hr=timestep_hr,
        eq_tank=TankState(
            level_m3=initial_eq_level_m3,
            capacity_m3=eq_capacity_m3,
            min_level_m3=eq_capacity_m3 * 0.10
        ),
        centrate_tank=TankState(
            level_m3=0.0,
            capacity_m3=centrate_capacity_m3,
            min_level_m3=0.0
        ),
        cake_storage=SolidsTankState(
            level_kgds=0.0,
            capacity_kgds=cake_capacity_kgds,
            min_level_kgds=0.0
        ),
        dried_storage=SolidsTankState(
            level_kgds=0.0,
            capacity_kgds=dried_capacity_kgds,
            min_level_kgds=0.0
        ),
        char_storage=SolidsTankState(
            level_kgds=0.0,
            capacity_kgds=char_capacity_kgds,
            min_level_kgds=0.0
        ),
        controller=ControllerState(mode=SystemMode.NORMAL)
    )
