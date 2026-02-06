"""
Core module - Parameters, State, and Physics calculations.

This module contains:
    - parameters.py: Frozen parameter dataclasses (NEVER change during run)
    - state.py: Mutable state containers (evolve each timestep)
    - balances.py: Pure mass/energy balance functions (physics only)
    - utils.py: Validation, clipping, unit conversion utilities
"""

from .parameters import (
    ModelParameters,
    ServiceAreaParams,
    DeWateringParams,
    DryerParams,
    PyrolysisParams,
    CoFeedParams,
    BufferStorageParams,
    OffSpecParams,
    OffSpecTrigger,
    # Overnight mode types (GAP-004)
    OvernightModeStatus,
    OvernightMode,
    OvernightModeParams,
    VendorOvernightData,
    VendorValidationPolicy,
    RestartBucket,
    validate_overnight_responses,
    DischargeParams,
    ControlParams,
    OperatingParams,
    EconomicParams,
    CapexScalingParams,
    ParameterType,
    # Option B parameters
    CofeedSupplyParams,
    CofeedRoutingParams,
    CharQualityParams,
    RegulatoryParams,
    CofeedSeasonalProfile,
    RegulatoryPathway,
    CharQualityTier,
    # Deployment mode types
    DeploymentMode,
    DeploymentParams,
    # Staffing and operations
    StaffingModel,
    OperationsParams,
    MaintenanceModel,
    # Operating envelope
    OperatingEnvelope,
    OvernightState,
    OPERATING_ENVELOPE_DEFAULT,
    # Scenario factories
    create_baseline_parameters,
    create_cofeed_scenario,
    create_high_discharge_scenario,
    create_option_b_scenario,
    create_product_scenario,
    create_hub_scenario,
    create_hub_staffed_scenario,
)

from .state import (
    SimulationState,
    TankState,
    SolidsTankState,
    QueueState,
    ControllerState,
    ThermalSystemState,
    DischargeState,
    MassBalanceState,
    CarbonAccountingState,
    EconomicState,
    SystemMode,
    OverflowAction,
    # Option B state
    CofeedRoutingState,
    OptionBState,
    create_initial_state,
    # Pathway state management
    PathwayExecutionState,
)

from .balances import (
    calc_dewatering,
    calc_dryer,
    calc_pyrolysis,
    calc_cofeed_pyrolysis,
    calc_energy_balance,
    calc_carbon_balance,
    calc_centrate_discharge,
    calc_steady_state_flows,
    is_discharge_window,
    DeWateringResult,
    DryerResult,
    PyrolysisResult,
    EnergyBalanceResult,
    CarbonResult,
    # Option B balance functions
    calc_cofeed_routing,
    calc_option_b_thermal,
    calc_segregated_char_revenue,
    calc_blended_quality_index,
    CofeedRoutingResult,
    OptionBThermalResult,
    SegregatedCharRevenueResult,
)

from .utils import (
    ClipResult,
    clip_range,
    apply_deadband,
    validate_fraction,
    validate_positive,
    validate_non_negative,
    assert_mass_balance,
    m3_to_liters,
    liters_to_m3,
    kg_to_tonnes,
    tonnes_to_kg,
    mj_to_kwh,
    kwh_to_mj,
)

__all__ = [
    # Parameters
    "ModelParameters",
    "ServiceAreaParams",
    "DeWateringParams",
    "DryerParams",
    "PyrolysisParams",
    "CoFeedParams",
    "BufferStorageParams",
    "OffSpecParams",
    "OffSpecTrigger",
    "DischargeParams",
    "ControlParams",
    "OperatingParams",
    "EconomicParams",
    "CapexScalingParams",
    "ParameterType",
    # Option B parameters
    "CofeedSupplyParams",
    "CofeedRoutingParams",
    "CharQualityParams",
    "RegulatoryParams",
    "CofeedSeasonalProfile",
    "RegulatoryPathway",
    "CharQualityTier",
    # Scenario factories
    "create_baseline_parameters",
    "create_cofeed_scenario",
    "create_high_discharge_scenario",
    "create_option_b_scenario",
    # State
    "SimulationState",
    "TankState",
    "SolidsTankState",
    "QueueState",
    "ControllerState",
    "ThermalSystemState",
    "DischargeState",
    "MassBalanceState",
    "CarbonAccountingState",
    "EconomicState",
    "SystemMode",
    "OverflowAction",
    "create_initial_state",
    # Balances
    "calc_dewatering",
    "calc_dryer",
    "calc_pyrolysis",
    "calc_cofeed_pyrolysis",
    "calc_energy_balance",
    "calc_carbon_balance",
    "calc_centrate_discharge",
    "calc_steady_state_flows",
    "is_discharge_window",
    "DeWateringResult",
    "DryerResult",
    "PyrolysisResult",
    "EnergyBalanceResult",
    "CarbonResult",
    # Option B balance functions
    "calc_cofeed_routing",
    "calc_option_b_thermal",
    "calc_segregated_char_revenue",
    "calc_blended_quality_index",
    "CofeedRoutingResult",
    "OptionBThermalResult",
    "SegregatedCharRevenueResult",
    # Option B state
    "CofeedRoutingState",
    "OptionBState",
    # Operating envelope
    "OperatingEnvelope",
    "OvernightState",
    "OPERATING_ENVELOPE_DEFAULT",
    # Pathway state management
    "PathwayExecutionState",
    # Utils
    "ClipResult",
    "clip_range",
    "apply_deadband",
    "validate_fraction",
    "validate_positive",
    "validate_non_negative",
    "assert_mass_balance",
    "m3_to_liters",
    "liters_to_m3",
    "kg_to_tonnes",
    "tonnes_to_kg",
    "mj_to_kwh",
    "kwh_to_mj",
]
