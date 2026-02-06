"""
Core Parameters Module - Frozen dataclasses defining all model parameters.
Parameters NEVER change during a simulation run - only state evolves.

Locked Baseline (Tiny Township / North Simcoe):
    - Annual septage: 5,000 m³/yr
    - Thermal uptime: 0.90
    - Seasonality: 80% Apr-Nov / 20% Dec-Mar
    - Q_permit: 3.0 m³/hr (Mon-Fri, 8hr windows)
    - T_c: 24 hr (cake control correction time)
    - Co-feed: OFF by default
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any, Literal
from enum import Enum
import json
import hashlib
import warnings

from .utils import validate_fraction, validate_positive, validate_non_negative, validate_yields_sum


# =============================================================================
# Design-Grade Physics: Feedstock Characterization
# =============================================================================

@dataclass(frozen=True)
class ProximateAnalysis:
    """
    Proximate analysis on dry basis (fraction of dry solids).
    
    Constraint: volatile_matter + fixed_carbon + ash must sum to 1.0 (±1%)
    
    References:
        ref_sludge_composition_fonts_2009 for septage defaults
    """
    volatile_matter: float    # VM fraction (dry basis)
    fixed_carbon: float       # FC fraction (dry basis)
    ash: float                # Ash fraction (dry basis)
    
    def __post_init__(self):
        total = self.volatile_matter + self.fixed_carbon + self.ash
        if abs(total - 1.0) > 0.01:
            raise ValueError(
                f"Proximate analysis must sum to 1.0 (±1%), got {total:.3f}. "
                f"VM={self.volatile_matter}, FC={self.fixed_carbon}, Ash={self.ash}"
            )


@dataclass(frozen=True)
class UltimateAnalysis:
    """
    Ultimate analysis on dry ash-free (DAF) basis.
    
    Constraint: C + H + O + N + S must sum to 1.0 (±1%)
    """
    carbon: float     # C fraction (DAF)
    hydrogen: float   # H fraction (DAF)
    oxygen: float     # O fraction (DAF)
    nitrogen: float   # N fraction (DAF)
    sulfur: float     # S fraction (DAF)
    
    def __post_init__(self):
        total = self.carbon + self.hydrogen + self.oxygen + self.nitrogen + self.sulfur
        if abs(total - 1.0) > 0.01:
            raise ValueError(
                f"Ultimate analysis must sum to 1.0 (±1%), got {total:.3f}. "
                f"C={self.carbon}, H={self.hydrogen}, O={self.oxygen}, N={self.nitrogen}, S={self.sulfur}"
            )


@dataclass(frozen=True)
class FeedstockProperties:
    """
    Complete feedstock characterization for design-grade pyrolysis modeling.
    
    Enables:
        - Energy balance from ultimate analysis
        - Ash tracking through process
        - Biochar quality prediction
        - Emissions estimation (N, S)
    
    Note: Backward compatible - existing code can use ts_fraction property.
    """
    name: str                               # e.g., "septage_solids", "wood_chips"
    moisture_fraction: float                # As-received moisture (0.97 for septage slurry)
    
    # Composition analysis
    proximate: ProximateAnalysis
    ultimate: UltimateAnalysis
    
    # Energy content of dry solids
    lhv_dry_mj_kg: float                    # LHV of dry solids (MJ/kg)
    hhv_dry_mj_kg: Optional[float] = None   # HHV if known
    
    # Optional physical properties
    bulk_density_kg_m3: Optional[float] = None  # For volumetric calculations
    ash_fusion_temp_c: Optional[float] = None   # Ash behavior
    
    @property
    def ts_fraction(self) -> float:
        """Total solids fraction (for backward compatibility)."""
        return 1.0 - self.moisture_fraction
    
    @property 
    def organic_fraction(self) -> float:
        """Organic content = 1 - ash (on dry basis)."""
        return 1.0 - self.proximate.ash
    
    @property
    def carbon_dry_basis(self) -> float:
        """Carbon content on dry basis (not DAF)."""
        return self.ultimate.carbon * self.organic_fraction


# Default feedstock instances (literature-backed)
SEPTAGE_SOLIDS_DEFAULT = FeedstockProperties(
    name="septage_solids",
    moisture_fraction=0.97,  # 3% TS (typical septage slurry)
    proximate=ProximateAnalysis(
        volatile_matter=0.55,
        fixed_carbon=0.10,
        ash=0.35,            # Septage is high-ash
    ),
    ultimate=UltimateAnalysis(
        carbon=0.52,         # DAF basis
        hydrogen=0.07,
        oxygen=0.35,
        nitrogen=0.05,
        sulfur=0.01,
    ),
    lhv_dry_mj_kg=15.0,
    bulk_density_kg_m3=600.0,  # Dried cake
)

WOOD_CHIPS_DEFAULT = FeedstockProperties(
    name="wood_chips",
    moisture_fraction=0.15,  # 85% TS (air-dried wood)
    proximate=ProximateAnalysis(
        volatile_matter=0.80,
        fixed_carbon=0.18,
        ash=0.02,            # Wood is low-ash
    ),
    ultimate=UltimateAnalysis(
        carbon=0.50,
        hydrogen=0.06,
        oxygen=0.43,
        nitrogen=0.005,
        sulfur=0.005,
    ),
    lhv_dry_mj_kg=18.5,
    bulk_density_kg_m3=250.0,  # Loose chips
)


# =============================================================================
# Design-Grade Physics: Pyrolysis Kinetics
# =============================================================================

# Type alias for kinetics tier
KineticsTier = Literal["TIER1_GLOBAL", "TIER2_PARALLEL"]


class UnvalidatedKineticsWarning(UserWarning):
    """Raised when literature-based kinetics are used in design_mode."""
    pass


@dataclass(frozen=True)
class KineticsParams:
    """
    Pyrolysis kinetics parameters with tiered formulation and validation governance.
    
    Tier-1 (active by default):
        Global single-step kinetics: dX/dt = A * exp(-Ea/RT) * (1-X)^n
        
    Tier-2 (structured, not calibrated):
        Parallel reactions: Biomass → Char (k_char), Biomass → Volatiles (k_vol)
        Only activated when tier="TIER2_PARALLEL" AND validated=True
    
    Engineering Intent:
        - Tier-1 must always be runnable
        - Tier-2 parameters may be None until lab data exists
        - validated=False is default for literature-based kinetics
        - source_refs must reference ref_ids in references.json
    """
    # --- Identity ---
    stream_id: str                  # e.g. "septage", "cofeed_wood"
    tier: KineticsTier = "TIER1_GLOBAL"
    
    # --- Tier 1: Global kinetics (ACTIVE by default) ---
    Ea_J_per_mol: float = 250000.0          # Activation energy (J/mol)
    A_s_inv: float = 1e18                   # Pre-exponential factor (1/s)
    reaction_order: float = 1.0             # Reaction order n
    
    # --- Design gate: conversion threshold ---
    X_min: float = 0.90                     # Minimum required conversion
    
    # --- Operating conditions ---
    temperature_k: float = 823.15           # Reactor temperature (K) = 550°C
    
    # --- RTD model (plug flow for now) ---
    rtd_model: Literal["PFR"] = "PFR"
    dispersion_pe: Optional[float] = None   # Peclet number (future)
    
    # --- Tier 2: Parallel reactions (STRUCTURE ONLY) ---
    # These are ignored unless tier == "TIER2_PARALLEL" AND validated == True
    Ea_char_J_per_mol: Optional[float] = None
    A_char_s_inv: Optional[float] = None
    Ea_volatile_J_per_mol: Optional[float] = None
    A_volatile_s_inv: Optional[float] = None
    
    # --- Validation / governance ---
    validated: bool = False                 # Must be True for DRL-4+
    source_refs: Tuple[str, ...] = ()       # Reference IDs from references.json
    notes: Optional[str] = None
    
    def __post_init__(self):
        # Enforce: unvalidated kinetics must have source references
        if not self.validated and len(self.source_refs) == 0:
            raise ValueError(
                f"Kinetics for stream '{self.stream_id}' are unvalidated but have no source_refs. "
                "Literature-based kinetics must reference at least one ref_id from references.json."
            )
        
        # Enforce: Tier-2 requires validation
        if self.tier == "TIER2_PARALLEL" and not self.validated:
            raise ValueError(
                f"Tier-2 parallel kinetics for stream '{self.stream_id}' require validated=True. "
                "Tier-2 cannot be activated with literature-only parameters."
            )


# Default kinetics instances (literature-backed, unvalidated)
SEPTAGE_KINETICS_DEFAULT = KineticsParams(
    stream_id="septage",
    tier="TIER1_GLOBAL",
    Ea_J_per_mol=250000.0,      # Mid-range from DAEM studies
    A_s_inv=1e18,               # Mid-log range
    reaction_order=1.0,         # Parallel first-order heritage
    X_min=0.95,                 # Higher for pathogen/odor destruction
    temperature_k=823.15,       # 550°C
    validated=False,
    source_refs=(
        "ref_sludge_kinetics_daem_2012",
        "ref_sludge_parallel_reactions_2008",
    ),
    notes="Literature defaults for sewage sludge. DRL-4 validation required.",
)

WOOD_KINETICS_DEFAULT = KineticsParams(
    stream_id="cofeed_wood",
    tier="TIER1_GLOBAL",
    Ea_J_per_mol=180000.0,      # Mid-range for wood
    A_s_inv=1e12,               # Lower than sludge
    reaction_order=1.0,
    X_min=0.85,                 # Lower acceptable for wood (char quality focus)
    temperature_k=823.15,       # 550°C
    validated=False,
    source_refs=("ref_wood_pyrolysis_di_blasi_2008",),
    notes="Literature defaults for wood pyrolysis. DRL-4 validation required.",
)


# =============================================================================
# Design-Grade Physics: Reactor Parameters
# =============================================================================

class ReactorType(Enum):
    """Pyrolysis reactor configuration types."""
    AUGER = "auger"                   # Screw/auger reactor
    ROTARY_KILN = "rotary_kiln"       # Rotating drum
    FLUIDIZED_BED = "fluidized_bed"   # Bubbling or circulating FB


@dataclass(frozen=True)
class ReactorParams:
    """
    Reactor geometry and heat transfer parameters for design-grade physics.
    
    Enables:
        - Residence time calculation from holdup
        - Heat transfer feasibility gate
        - Reactor sizing checks
    
    Key relationships:
        τ_s = M_holdup / ṁ_solids
        Q_max = U * A * ΔT_lm
    """
    # --- Reactor type ---
    reactor_type: ReactorType = ReactorType.AUGER
    
    # --- Geometry ---
    length_m: float = 3.0                   # Reactor length
    diameter_m: float = 0.5                 # Reactor diameter
    fill_fraction: float = 0.15            # Fraction of volume filled with solids
    
    # --- Bulk properties ---
    bulk_density_kg_m3: float = 500.0       # Bulk density of bed material
    
    # --- Heat transfer ---
    U_w_m2k: float = 50.0                   # Overall heat transfer coefficient (W/m²K)
    wall_thickness_m: float = 0.01          # Wall thickness for heat transfer area
    
    # --- Temperature ---
    T_wall_k: float = 923.15                # Wall temperature (K) = 650°C
    T_feed_k: float = 373.15                # Feed temperature (K) = 100°C (post-dryer)
    
    # --- RTD ---
    rtd_model: Literal["PFR"] = "PFR"
    
    # --- Validation ---
    validated: bool = False
    source_refs: Tuple[str, ...] = ("ref_pyrolysis_heat_transfer_2015",)
    
    @property
    def cross_section_area_m2(self) -> float:
        """Reactor cross-sectional area."""
        import math
        return math.pi * (self.diameter_m / 2) ** 2
    
    @property
    def total_volume_m3(self) -> float:
        """Total reactor volume."""
        return self.cross_section_area_m2 * self.length_m
    
    @property
    def filled_volume_m3(self) -> float:
        """Volume occupied by solids."""
        return self.total_volume_m3 * self.fill_fraction
    
    @property
    def holdup_mass_kg(self) -> float:
        """Mass of solids in reactor at steady state."""
        return self.filled_volume_m3 * self.bulk_density_kg_m3
    
    @property
    def heat_transfer_area_m2(self) -> float:
        """Heat transfer area (inner wall surface)."""
        import math
        return math.pi * self.diameter_m * self.length_m
    
    def calc_residence_time_s(self, m_dot_kg_s: float) -> float:
        """Calculate solids residence time for given mass flow rate."""
        if m_dot_kg_s <= 0:
            raise ValueError("Mass flow rate must be positive")
        return self.holdup_mass_kg / m_dot_kg_s


# Default reactor (auger type, literature-backed)
REACTOR_DEFAULT = ReactorParams(
    reactor_type=ReactorType.AUGER,
    length_m=3.0,
    diameter_m=0.5,
    fill_fraction=0.15,
    bulk_density_kg_m3=500.0,
    U_w_m2k=50.0,
    T_wall_k=923.15,
    T_feed_k=373.15,
    validated=False,
    source_refs=("ref_pyrolysis_heat_transfer_2015",),
)


class ParameterType(Enum):
    FIXED = "fixed"
    UNCERTAIN = "uncertain"
    DECISION = "decision"


class CofeedSeasonalProfile(Enum):
    """Co-feed supply seasonality profiles."""
    WOOD_STEADY = "wood_steady"      # Year-round stable supply (default)
    AG_SEASONAL = "ag_seasonal"       # Agricultural residues with harvest peak


class RegulatoryPathway(Enum):
    """Facility regulatory classification."""
    WASTE_ONLY = "waste_only"         # Septage-only, waste treatment permit
    BIOMASS_HYBRID = "biomass_hybrid" # Co-feed enabled, may require different permit


class CharQualityTier(Enum):
    """Biochar quality/market tiers."""
    TIER_1_PREMIUM = 1    # IBI-certified, low metals, $500/t
    TIER_2_BULK = 2       # Bulk soil amendment, $225/t
    TIER_3_LOW_VALUE = 3  # Landfill cover/restricted, $75/t


class DeploymentMode(Enum):
    """Deployment configuration for Option B system."""
    PRODUCT = "product"           # Owner-operated, labor externalized, 0.6x CAPEX
    REGIONAL_HUB = "regional_hub" # Staffed facility, full CAPEX, labor factor 0.7


@dataclass(frozen=True)
class DeploymentParams:
    """
    Deployment-specific parameters for Option B.
    
    Product Mode: Owner-operated asset for rural waste handlers
        - Smaller scale, modular equipment
        - Buyer economics framing (savings vs dumping fees)
        - Labor regime defined in StaffingModel
    
    Regional Hub Mode: Centralized staffed facility
        - Full-scale equipment
        - Facility NOI framing
        - Labor regime defined in StaffingModel
    """
    mode: DeploymentMode = DeploymentMode.PRODUCT
    
    # Scale parameters
    annual_septage_m3: float = 2000.0      # Product: 2000, Hub: 5000
    annual_cofeed_tds: float = 600.0       # Product: 600, Hub: 1200
    
    # Economic parameters
    capex_multiplier: float = 0.6          # Product: 0.6, Hub: 1.0
    capex_validated: bool = False          # Flag: CAPEX estimate requires vendor validation
    
    # Buyer economics (Product mode)
    reference_dumping_fee: float = 55.0    # $/m3 - what buyer currently pays
    
    # Hauling parameters for non-cash value (Product mode)
    # Used to calculate truck hours and fuel saved
    avg_haul_distance_km: float = 45.0     # Average one-way distance to disposal site
    truck_capacity_m3: float = 12.0        # Typical vacuum truck capacity
    truck_speed_km_hr: float = 50.0        # Average speed including loading/unloading
    fuel_cost_per_km: float = 0.85         # Diesel cost per km
    driver_hourly_rate: float = 35.0       # Loaded driver cost (for value calculation)
    
    @classmethod
    def product_default(cls) -> 'DeploymentParams':
        return cls(
            mode=DeploymentMode.PRODUCT,
            annual_septage_m3=2000.0,
            annual_cofeed_tds=600.0,
            capex_multiplier=0.6,
        )
    
    @classmethod
    def hub_default(cls) -> 'DeploymentParams':
        return cls(
            mode=DeploymentMode.REGIONAL_HUB,
            annual_septage_m3=5000.0,
            annual_cofeed_tds=1200.0,
            capex_multiplier=1.0,
        )




@dataclass(frozen=True)
class ServiceAreaParams:
    """Service area characteristics for septage supply."""
    annual_septage_m3: float = 5000.0
    density_kg_m3: float = 1000.0
    ts_fraction_mean: float = 0.03
    ts_fraction_std: float = 0.01
    ts_fraction_min: float = 0.02
    ts_fraction_max: float = 0.06
    
    # 80% Apr-Nov, 20% Dec-Mar
    monthly_multipliers: Tuple[float, ...] = (
        0.6, 0.6, 0.6, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 0.6
    )
    
    hourly_pattern: Tuple[float, ...] = (
        0.00, 0.00, 0.00, 0.00, 0.00, 0.00,
        0.02, 0.12, 0.14, 0.14, 0.14, 0.14,
        0.10, 0.08, 0.06, 0.04, 0.02, 0.00,
        0.00, 0.00, 0.00, 0.00, 0.00, 0.00
    )
    
    dow_multipliers: Tuple[float, ...] = (1.2, 1.2, 1.2, 1.2, 1.2, 0.2, 0.2)
    truck_capacity_m3_mean: float = 10.0
    truck_capacity_m3_std: float = 2.0
    unloading_time_min_mean: float = 20.0
    unloading_time_min_std: float = 5.0
    rejection_rate: float = 0.01


@dataclass(frozen=True)
class DeWateringParams:
    """Dewatering unit performance parameters."""
    cake_ts_fraction: float = 0.20
    solids_capture: float = 0.95
    polymer_kg_per_tds: float = 5.0
    power_kwh_per_m3: float = 2.0
    max_throughput_m3_hr: float = 5.0


@dataclass(frozen=True)
class DryerParams:
    """Dryer performance parameters."""
    dried_ts_fraction: float = 0.75
    energy_kwh_per_kg_water: float = 0.9
    thermal_efficiency: float = 0.55
    max_throughput_kgds_hr: float = 100.0
    min_turndown: float = 0.3


@dataclass(frozen=True)
class PyrolysisParams:
    """Pyrolysis reactor performance parameters."""
    yield_char: float = 0.35
    yield_gas: float = 0.40
    yield_condensate: float = 0.25
    char_carbon_fraction: float = 0.50
    char_permanence_factor: float = 0.80
    lhv_syngas_sept_mj_kg: float = 8.0
    lhv_syngas_cofeed_mj_kg: float = 12.0
    heat_requirement_mj_kgds: float = 0.5
    syngas_recovery_efficiency: float = 0.75
    max_throughput_kgds_hr: float = 50.0
    max_feed_variation: float = 0.05


@dataclass(frozen=True)
class CoFeedParams:
    """Co-substrate feed parameters for winter stabilization."""
    enabled: bool = False
    ts_fraction: float = 0.85
    cost_per_tds: float = 80.0
    yield_char_cofeed: float = 0.30
    yield_gas_cofeed: float = 0.45
    yield_condensate_cofeed: float = 0.25
    char_carbon_fraction_cofeed: float = 0.70
    lhv_syngas_mj_kg: float = 10.0  # Wood syngas has higher LHV than septage
    winter_months: Tuple[int, ...] = (11, 0, 1, 2)


@dataclass(frozen=True)
class CofeedSupplyParams:
    """
    Co-feed supply chain parameters for Option B.
    
    Controls delivered cost, availability, and contract security.
    Default assumes wood residuals with stable year-round supply.
    """
    # Transport and delivered cost
    transport_km: float = 25.0                    # Average haul distance
    cost_per_tkm: float = 0.15                    # $/tonne-km transport cost
    base_cost_per_tds: float = 80.0               # Base cost at source $/tDS
    
    # Supply profile
    seasonal_profile: CofeedSeasonalProfile = CofeedSeasonalProfile.WOOD_STEADY
    
    # Wood-steady: 1.0 all months (default, contractable baseload)
    wood_monthly_multipliers: Tuple[float, ...] = (
        1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0
    )
    
    # Ag-seasonal: Oct-Dec peak (1.5), Apr-Jul low (0.5), normalized
    # Pattern: Jan=0.8, Feb=0.8, Mar=0.7, Apr-Jul=0.5, Aug=0.8, Sep=1.0, Oct-Dec=1.5
    ag_monthly_multipliers: Tuple[float, ...] = (
        0.8, 0.8, 0.7, 0.5, 0.5, 0.5, 0.5, 0.8, 1.0, 1.5, 1.5, 1.5
    )
    
    # Contract security (1.0 = fully contracted, 0.7 = mostly spot)
    contract_security_factor: float = 0.85
    
    # Annual target for Option B (tDS/yr)
    annual_target_tds: float = 1200.0
    
    def get_monthly_multipliers(self) -> Tuple[float, ...]:
        """Return appropriate monthly pattern based on profile."""
        if self.seasonal_profile == CofeedSeasonalProfile.WOOD_STEADY:
            return self.wood_monthly_multipliers
        else:
            return self.ag_monthly_multipliers
    
    def delivered_cost_per_tds(self) -> float:
        """Calculate total delivered cost including transport."""
        transport_cost = self.transport_km * self.cost_per_tkm
        return self.base_cost_per_tds + transport_cost


@dataclass(frozen=True)
class CofeedRoutingParams:
    """
    Dryer bypass routing logic with hysteresis.
    
    Co-feed routing decision:
        - TS >= bypass_ts_high (0.70): bypass dryer, feed directly to pyro
        - TS <= bypass_ts_low (0.60): route through dryer
        - 0.60 < TS < 0.70: hold prior state (hysteresis band)
    
    This prevents flip-flopping and preserves Option B energy advantage.
    """
    bypass_ts_high: float = 0.70    # Above this: bypass dryer
    bypass_ts_low: float = 0.60     # Below this: use dryer
    default_bypass_mode: bool = True # Initial state (True = bypass, assumes dry co-feed)


@dataclass(frozen=True)
class CharQualityParams:
    """
    Biochar quality tracking and pricing by source.
    
    Conservative defaults:
        - Co-feed char → Tier 2 (bulk soil amendment)
        - Septage char → Tier 3 (low-value/restricted)
    
    Tier 1 (premium) is opt-in only when quality conditions explicitly met.
    """
    # Tier prices ($/tonne)
    tier_1_price: float = 500.0     # Premium: IBI-certified, low metals
    tier_2_price: float = 225.0     # Bulk: soil amendment, minimal cert
    tier_3_price: float = 75.0      # Low-value: landfill cover, restricted
    
    # Default tier assignments (conservative)
    default_tier_cofeed: int = 2    # Co-feed char → Tier 2
    default_tier_septage: int = 3   # Septage char → Tier 3
    
    # Quality index (0-1, lower = better quality)
    # Used for blended char pricing if segregation disabled
    quality_index_cofeed: float = 0.2   # Clean biomass
    quality_index_septage: float = 0.8  # Higher ash/metals risk
    
    # Segregation control
    segregation_enabled: bool = True    # Default: keep char streams separate
    
    def get_tier_price(self, tier: int) -> float:
        """Return price for specified tier."""
        if tier == 1:
            return self.tier_1_price
        elif tier == 2:
            return self.tier_2_price
        else:
            return self.tier_3_price


@dataclass(frozen=True)
class RegulatoryParams:
    """
    Regulatory pathway and compliance cost parameters.
    
    Adding co-feed may reclassify facility from waste treatment
    to biomass energy, affecting permits and compliance costs.
    """
    pathway: RegulatoryPathway = RegulatoryPathway.WASTE_ONLY
    
    # Cost adjustments for BIOMASS_HYBRID pathway
    compliance_cost_adder: float = 15000.0   # Additional $/yr compliance
    permitting_capex_adder: float = 75000.0  # One-time permitting cost
    timeline_risk_factor: float = 1.2        # Schedule multiplier for NPV
    
    def get_annual_compliance_adder(self) -> float:
        """Return additional annual compliance cost for pathway."""
        if self.pathway == RegulatoryPathway.BIOMASS_HYBRID:
            return self.compliance_cost_adder
        return 0.0
    
    def get_permitting_capex_adder(self) -> float:
        """Return additional permitting CAPEX for pathway."""
        if self.pathway == RegulatoryPathway.BIOMASS_HYBRID:
            return self.permitting_capex_adder
        return 0.0


@dataclass(frozen=True)
class StaffingModel:
    """
    Self-contained staffing regime definition.
    
    Defines labor cost and owner time for a specific operating mode.
    Single source of truth for all labor-related parameters.
    """
    mode: str = "hub_staffed"  # "owner_op" | "daytime_callout" | "hub_staffed"
    
    # Paid labor (cash cost basis)
    paid_hours_per_week: float = 112.0  # 8hr * 2 shifts * 7 days for hub
    base_wage_per_hr: float = 35.0
    burden_multiplier: float = 1.35  # benefits, payroll taxes, WSIB
    
    # On-call / callout (optional)
    on_call_allowance_weekly: float = 0.0
    overtime_multiplier: float = 1.5
    expected_callouts_per_week: float = 0.0
    callout_hours_per_event: float = 2.0
    
    # Owner time (informational, not in cash cost)
    owner_time_hours_per_week: float = 0.0
    
    def annual_cash_labor_cost(self) -> float:
        """
        Fully-loaded annual labor cost (cash basis only).
        
        For owner-op, returns 0 (owner time externalized).
        Does NOT include owner_time_hours_per_week.
        """
        base_hours_yr = self.paid_hours_per_week * 52
        base_cost = base_hours_yr * self.base_wage_per_hr * self.burden_multiplier
        
        on_call_annual = self.on_call_allowance_weekly * 52
        
        callout_hours_yr = self.expected_callouts_per_week * self.callout_hours_per_event * 52
        callout_cost = (callout_hours_yr * self.base_wage_per_hr * 
                       self.overtime_multiplier * self.burden_multiplier)
        
        return base_cost + on_call_annual + callout_cost
    
    @classmethod
    def owner_op(cls, owner_hours: float = 5.0) -> 'StaffingModel':
        """
        Owner-operated: cash labor cost = 0, owner time tracked separately.
        
        Args:
            owner_hours: Expected owner time commitment (hr/wk), informational only
        """
        return cls(
            mode="owner_op",
            paid_hours_per_week=0.0,
            base_wage_per_hr=0.0,
            burden_multiplier=1.0,
            owner_time_hours_per_week=owner_hours,
        )
    
    @classmethod
    def hub_light_ops(cls) -> 'StaffingModel':
        """
        Light-ops hub: Daytime staff + on-call for nights/weekends.
        
        Semi-attended facility with:
        - 40 hr/wk paid (1 operator, daytime M-F)
        - On-call allowance for nights/weekends
        - Expected 2 callouts/week @ 2 hrs each
        
        Total annual labor: ~$133k (48% of fully-staffed)
        """
        return cls(
            mode="hub_light_ops",
            paid_hours_per_week=40.0,  # 8hr * 5 days
            base_wage_per_hr=38.0,
            burden_multiplier=1.35,
            on_call_allowance_weekly=200.0,
            expected_callouts_per_week=2.0,
            callout_hours_per_event=2.0,
        )
    
    @classmethod
    def daytime_callout(cls) -> 'StaffingModel':
        """
        Alias for hub_light_ops (deprecated name).
        Use hub_light_ops() for clarity.
        """
        return cls.hub_light_ops()
    
    @classmethod
    def hub_staffed(cls) -> 'StaffingModel':
        """
        Fully staffed hub: 2 shifts/day, 7 days.
        
        Traditional staffed facility with:
        - 112 hr/wk paid (2 operators × 8 hr × 7 days)
        - No on-call (always staffed)
        
        Total annual labor: ~$275k
        """
        return cls(
            mode="hub_staffed",
            paid_hours_per_week=112.0,  # 8hr * 2 shifts * 7 days
            base_wage_per_hr=35.0,
            burden_multiplier=1.35,
        )
    
    @classmethod
    def hub_default(cls) -> 'StaffingModel':
        """Alias for hub_staffed (default hub assumption)."""
        return cls.hub_staffed()


@dataclass(frozen=True)
class MaintenanceModel:
    """
    Decomposed maintenance cost model for design-driven analysis.
    
    Replaces blunt %CAPEX with actionable cost buckets:
        planned_maintenance: scheduled service, wear parts, inspections
        unplanned_callouts: emergency repairs, travel, contractor costs
        consumables: filters, lubricants, calibration gases, etc.
    
    Total = C_fixed + k_throughput × (tDS/yr) + C_callouts
    
    This maps directly to design choices:
        - Modular assemblies → reduce callout frequency
        - Owner-serviceable → reduce callout cost
        - Quality bearings/seals → reduce wear part frequency
    """
    # Fixed annual costs (sensors, calibration, software, fire system)
    fixed_annual: float = 8000.0  # $/yr
    
    # Throughput-linked wear (augers, seals, refractory, bearings)
    wear_cost_per_tds: float = 15.0  # $/tDS processed
    
    # Unplanned callouts
    callouts_per_year: float = 12.0  # Expected callout events
    cost_per_callout: float = 1500.0  # $/event (parts + labor + travel)
    owner_can_service: bool = False  # If True, callout cost reduced 60%
    
    # Consumables and inspections
    consumables_annual: float = 5000.0  # Filters, lubricants, etc.
    inspection_annual: float = 3000.0  # Third-party inspections, compliance
    
    def annual_cost(self, annual_tds: float) -> float:
        """
        Calculate total annual maintenance cost.
        
        Args:
            annual_tds: Annual dry solids processed (septage + co-feed)
        
        Returns:
            Total annual maintenance burden
        """
        # Fixed costs
        fixed = self.fixed_annual + self.consumables_annual + self.inspection_annual
        
        # Throughput-linked
        wear = self.wear_cost_per_tds * annual_tds
        
        # Callouts (owner-serviceable reduces cost by 60%)
        callout_rate = self.cost_per_callout * (0.4 if self.owner_can_service else 1.0)
        callouts = self.callouts_per_year * callout_rate
        
        return fixed + wear + callouts
    
    def breakdown(self, annual_tds: float) -> dict:
        """Return itemized maintenance breakdown for reporting."""
        callout_rate = self.cost_per_callout * (0.4 if self.owner_can_service else 1.0)
        return {
            'fixed': self.fixed_annual,
            'wear_parts': self.wear_cost_per_tds * annual_tds,
            'callouts': self.callouts_per_year * callout_rate,
            'consumables': self.consumables_annual,
            'inspections': self.inspection_annual,
            'total': self.annual_cost(annual_tds),
        }
    
    @classmethod
    def product_low_maintenance(cls) -> 'MaintenanceModel':
        """
        Low-maintenance product design target.
        
        Assumes:
            - Owner-serviceable (60% callout cost reduction)
            - Modular assemblies (fewer callouts)
            - Quality wear parts (low $/tDS)
        
        Target: ~$25k/yr at Product scale → viable payback
        """
        return cls(
            fixed_annual=6000.0,
            wear_cost_per_tds=12.0,
            callouts_per_year=6.0,  # Half of default
            cost_per_callout=1200.0,
            owner_can_service=True,
            consumables_annual=4000.0,
            inspection_annual=2500.0,
        )
    
    @classmethod
    def product_standard(cls) -> 'MaintenanceModel':
        """
        Standard product maintenance (current baseline).
        
        ~$40-50k/yr at Product scale → marginal payback
        """
        return cls(
            fixed_annual=8000.0,
            wear_cost_per_tds=15.0,
            callouts_per_year=12.0,
            cost_per_callout=1500.0,
            owner_can_service=False,
            consumables_annual=5000.0,
            inspection_annual=3000.0,
        )
    
    @classmethod
    def hub_facility(cls) -> 'MaintenanceModel':
        """
        Hub facility maintenance (higher scale, contractor service).
        """
        return cls(
            fixed_annual=15000.0,
            wear_cost_per_tds=12.0,  # Economies of scale
            callouts_per_year=24.0,  # More equipment
            cost_per_callout=2000.0,  # Contractor rates
            owner_can_service=False,
            consumables_annual=12000.0,
            inspection_annual=8000.0,
        )


@dataclass(frozen=True)
class OperationsParams:
    """
    OPEX complexity and operational mode parameters.
    
    Modifies labor and maintenance costs based on operational complexity.
    Separate from CAPEX scaling (equipment) and StaffingModel (labor regime).
    """
    # Two-stream operation complexity
    two_stream_mode: bool = True  # Option B operates septage + co-feed
    complexity_factor: float = 1.15  # Multiplier for labor + maintenance
    
    # Legacy maintenance scaling (for backward compatibility)
    # Prefer using MaintenanceModel for new analysis
    maintenance_fraction_of_capex: float = 0.03  # Annual maintenance as % CAPEX
    
    def apply_complexity(self, base_cost: float) -> float:
        """Apply complexity factor to a base OPEX cost."""
        return base_cost * self.complexity_factor if self.two_stream_mode else base_cost


@dataclass(frozen=True)
class BufferStorageParams:
    """Buffer tank sizing parameters."""
    eq_autonomy_days: float = 3.0
    eq_min_level_fraction: float = 0.10
    centrate_autonomy_days: float = 3.0
    cake_autonomy_hours: float = 48.0
    dried_autonomy_hours: float = 24.0
    char_autonomy_days: float = 14.0


class OffSpecTrigger(Enum):
    """Triggers for off-spec load diversion."""
    HIGH_FOG = "high_fog"                    # Fats, oil, grease above threshold
    TRASH_HEAVY = "trash_heavy"              # Excessive debris/rags
    UNKNOWN_CHEMISTRY = "unknown_chemistry"  # Suspected industrial contamination
    HIGH_TS = "high_ts"                      # TS > 6% (unusual, may indicate grease trap)
    LOW_TS = "low_ts"                        # TS < 1% (mostly water, process upset)
    ODOR_ALARM = "odor_alarm"                # H2S or unusual odor
    VISUAL_FLAG = "visual_flag"              # Operator visual inspection concern


@dataclass(frozen=True)
class OffSpecParams:
    """
    Off-spec load handling parameters.
    
    Off-spec tank is MANDATORY for both product and hub modes.
    Without it, one bad load = total process contamination.
    
    Design philosophy:
        - Divert suspect loads BEFORE they enter EQ
        - Hold in separate tank for characterization
        - Haul off if contamination confirmed
        - Blend back slowly if false positive
    """
    # Tank sizing
    tank_volume_m3: float = 12.0             # Default: 1 truck load
    tank_volume_hub_m3: float = 24.0         # Hub: 2 truck loads
    
    # Diversion triggers (which conditions trigger diversion)
    enabled_triggers: Tuple[str, ...] = (
        "high_fog",
        "trash_heavy",
        "unknown_chemistry",
        "visual_flag",
    )
    
    # Trigger thresholds
    fog_threshold_mg_L: float = 500.0        # FOG concentration trigger
    ts_high_threshold: float = 0.06          # >6% TS = suspect grease trap
    ts_low_threshold: float = 0.01           # <1% TS = mostly water
    
    # Hold and disposition
    max_hold_days: float = 7.0               # Max days before haul-off required
    haul_off_cost_per_m3: float = 85.0       # Cost to haul to municipal WWTP
    
    # Blend-back (if false positive)
    blend_back_rate_fraction: float = 0.10   # Max 10% of feed from off-spec tank
    blend_back_requires_test: bool = True    # Require lab test before blend-back
    
    # Alarm/notification
    notify_on_diversion: bool = True         # Send alert when load diverted
    log_all_decisions: bool = True           # Audit trail for diversions
    
    def get_tank_volume(self, is_hub: bool = False) -> float:
        """Return appropriate tank volume for deployment mode."""
        return self.tank_volume_hub_m3 if is_hub else self.tank_volume_m3
    
    def is_trigger_enabled(self, trigger: str) -> bool:
        """Check if a specific trigger is enabled."""
        return trigger in self.enabled_triggers


# =============================================================================
# Overnight Mode Parameters (GAP-004 placeholder)
# =============================================================================

class OvernightModeStatus(Enum):
    """Validation status for overnight mode parameters.
    
    UNKNOWN blocks DRL-4+ claims until ≥2 consistent vendor responses.
    """
    UNKNOWN = "unknown"              # Default: blocks DRL-4
    PARTIAL = "partial"              # 1 vendor response: informative only
    VALIDATED = "validated"          # ≥2 consistent responses: lifts block


class RestartBucket(Enum):
    """Restart time classification for consistency matching."""
    FAST = "fast"          # < 1 hour (hot hold)
    MODERATE = "moderate"  # 1-4 hours (warm standby)
    SLOW = "slow"          # > 4 hours (cold restart)


@dataclass(frozen=True)
class VendorValidationPolicy:
    """Policy for vendor response validation.
    
    Configurable thresholds for what constitutes "validated" vendor data.
    Dependency-injected into validation functions, not global.
    """
    min_vendors: int = 2                    # Require ≥2 consistent responses
    mode_match_required: bool = True        # Same overnight_mode enum required
    restart_bucket_match: bool = True       # Same restart time bucket required
    restart_pct_tolerance: float = 0.25     # ±25% for numeric restart time
    thermal_hold_match: bool = True         # Boolean match required
    
    def classify_restart_time(self, hours: float) -> RestartBucket:
        """Classify restart time into bucket (<1hr, 1-4hr, >4hr)."""
        if hours < 1.0:
            return RestartBucket.FAST
        elif hours <= 4.0:
            return RestartBucket.MODERATE
        else:
            return RestartBucket.SLOW
    
    def restart_times_consistent(self, t1: float, t2: float) -> bool:
        """Check if two restart times are consistent per policy."""
        # Same bucket check
        if self.restart_bucket_match:
            if self.classify_restart_time(t1) != self.classify_restart_time(t2):
                return False
        
        # Percentage tolerance check
        avg = (t1 + t2) / 2
        if avg > 0:
            diff_pct = abs(t1 - t2) / avg
            if diff_pct > self.restart_pct_tolerance:
                return False
        
        return True


class OvernightMode(Enum):
    """Overnight operating mode (vendor-validated)."""
    UNKNOWN = "unknown"                    # Not yet determined
    HOLD = "hold"                          # Hot hold: maintains temperature
    CONTROLLED_COOLDOWN = "controlled_cooldown"  # Gradual cooling, 1-4hr restart
    FULL_SHUTDOWN = "full_shutdown"        # Complete shutdown, >4hr restart


@dataclass(frozen=True)
class VendorOvernightData:
    """Single vendor's overnight mode response.
    
    Captured from vendor emails per overnight_response_schema.json.
    This is the structured parsing output - no free-text allowed.
    """
    vendor_id: str
    packet_hash: str
    date_received: str
    mode: OvernightMode = OvernightMode.UNKNOWN
    thermal_continuous_heat: bool = False
    min_temp_c: Optional[float] = None
    restart_time_hot_hr: Optional[float] = None
    restart_time_warm_hr: Optional[float] = None
    restart_time_cold_hr: Optional[float] = None
    shutdown_philosophy: str = "unknown"  # alarm_only, auto_rampdown, auto_shutdown, hybrid
    
    def get_restart_time(self, mode: OvernightMode) -> Optional[float]:
        """Get restart time for a given overnight mode."""
        if mode == OvernightMode.HOLD:
            return self.restart_time_hot_hr
        elif mode == OvernightMode.CONTROLLED_COOLDOWN:
            return self.restart_time_warm_hr
        elif mode == OvernightMode.FULL_SHUTDOWN:
            return self.restart_time_cold_hr
        return None


@dataclass(frozen=True)
class OvernightModeParams:
    """Overnight mode parameters for hub operations.
    
    Blocks DRL-4+ claims when status=UNKNOWN (default).
    Requires ≥2 consistent vendor responses for VALIDATED status.
    
    This is a GAP-004 placeholder that gets populated when vendor
    responses are parsed via validate_overnight_responses().
    
    Pipeline:
        Raw Email/PDF/XLS → VendorOvernightData (structured)
                         → validate_overnight_responses(policy)
                         → OvernightModeParams (validated or blocked)
                         → DRL Gate (4+ only)
    """
    # Validation status (blocks DRL-4 when UNKNOWN)
    status: OvernightModeStatus = OvernightModeStatus.UNKNOWN
    
    # Derived mode (only trustworthy when status=VALIDATED)
    mode: OvernightMode = OvernightMode.UNKNOWN
    
    # Thermal parameters (vendor-validated)
    min_temp_c: Optional[float] = None         # Minimum safe overnight temp
    continuous_heat_required: bool = False     # Must maintain heat source
    
    # Restart parameters (vendor-validated)
    restart_time_hot_hr: Optional[float] = None     # From hot hold
    restart_time_warm_hr: Optional[float] = None    # From controlled cooldown
    restart_time_cold_hr: Optional[float] = None    # From full shutdown
    
    # Shutdown/alarm philosophy
    shutdown_philosophy: str = "unknown"  # alarm_only, auto_rampdown, auto_shutdown, hybrid
    
    # Energy penalty for restart (used in economics)
    restart_energy_penalty_kwh: Optional[float] = None
    
    # Vendor data (raw responses for audit trail)
    vendor_responses: Tuple[VendorOvernightData, ...] = ()
    
    # Validation policy used (injected, not hardcoded)
    policy: VendorValidationPolicy = field(default_factory=VendorValidationPolicy)
    
    @property
    def is_validated(self) -> bool:
        """True if ≥2 consistent vendor responses exist."""
        return self.status == OvernightModeStatus.VALIDATED
    
    @property
    def blocks_drl4(self) -> bool:
        """True if DRL-4+ claims should be blocked."""
        return self.status == OvernightModeStatus.UNKNOWN
    
    @property
    def vendor_count(self) -> int:
        """Number of vendor responses received."""
        return len(self.vendor_responses)
    
    def get_restart_time(self) -> Optional[float]:
        """Get restart time for current mode."""
        if self.mode == OvernightMode.HOLD:
            return self.restart_time_hot_hr
        elif self.mode == OvernightMode.CONTROLLED_COOLDOWN:
            return self.restart_time_warm_hr
        elif self.mode == OvernightMode.FULL_SHUTDOWN:
            return self.restart_time_cold_hr
        return None
    
    def get_unvalidated_assumptions(self) -> List[str]:
        """Return list of unvalidated assumptions for DRL-3 warnings."""
        assumptions = []
        if self.status != OvernightModeStatus.VALIDATED:
            assumptions.append(f"overnight_mode={self.mode.value} (vendor count: {self.vendor_count})")
            if self.restart_time_hot_hr:
                assumptions.append(f"restart_time_hot={self.restart_time_hot_hr}hr (unvalidated)")
            if self.continuous_heat_required:
                assumptions.append("continuous_heat_required=True (unvalidated)")
        return assumptions


def validate_overnight_responses(
    responses: List[VendorOvernightData],
    policy: VendorValidationPolicy = None,
) -> OvernightModeParams:
    """Validate vendor responses and create OvernightModeParams.
    
    Applies the ≥min_vendors consistent rule:
    - 0 responses: UNKNOWN (blocks DRL-4)
    - 1 response: PARTIAL (informative only, blocks DRL-4)
    - ≥min_vendors consistent: VALIDATED (lifts DRL-4 block)
    - ≥min_vendors inconsistent: PARTIAL (blocks DRL-4)
    
    Consistency rules (engineer-grade):
    - overnight_mode: exact enum match required
    - restart_time: bucketed comparison (<1hr, 1-4hr, >4hr)
    - thermal_hold: boolean match required
    
    Args:
        responses: List of VendorOvernightData (from structured parsing)
        policy: Validation policy (dependency-injected)
    
    Returns:
        OvernightModeParams with appropriate status
    """
    if policy is None:
        policy = VendorValidationPolicy()
    
    if len(responses) == 0:
        return OvernightModeParams(
            status=OvernightModeStatus.UNKNOWN,
            policy=policy,
        )
    
    if len(responses) == 1:
        r = responses[0]
        # With min_vendors=1, single response can be VALIDATED
        status = OvernightModeStatus.VALIDATED if policy.min_vendors <= 1 else OvernightModeStatus.PARTIAL
        return OvernightModeParams(
            status=status,
            mode=r.mode,
            min_temp_c=r.min_temp_c,
            continuous_heat_required=r.thermal_continuous_heat,
            restart_time_hot_hr=r.restart_time_hot_hr,
            restart_time_warm_hr=r.restart_time_warm_hr,
            restart_time_cold_hr=r.restart_time_cold_hr,
            shutdown_philosophy=r.shutdown_philosophy,
            vendor_responses=tuple(responses),
            policy=policy,
        )
    
    # Check for ≥min_vendors consistent responses
    reference = responses[0]
    consistent_responses = [reference]
    
    for r in responses[1:]:
        is_consistent = True
        
        # Mode match check (exact enum)
        if policy.mode_match_required and r.mode != reference.mode:
            is_consistent = False
        
        # Thermal hold match (boolean)
        if policy.thermal_hold_match and r.thermal_continuous_heat != reference.thermal_continuous_heat:
            is_consistent = False
        
        # Restart time consistency check (bucketed)
        ref_restart = reference.get_restart_time(reference.mode)
        r_restart = r.get_restart_time(r.mode)
        if ref_restart is not None and r_restart is not None:
            if not policy.restart_times_consistent(ref_restart, r_restart):
                is_consistent = False
        
        if is_consistent:
            consistent_responses.append(r)
    
    # Determine status based on consistent count vs policy threshold
    if len(consistent_responses) >= policy.min_vendors:
        status = OvernightModeStatus.VALIDATED
    else:
        status = OvernightModeStatus.PARTIAL
    
    # Aggregate from consistent responses
    modes = [r.mode for r in consistent_responses]
    mode = max(set(modes), key=modes.count)  # Most common mode
    
    # Average restart times from consistent responses
    hot_times = [r.restart_time_hot_hr for r in consistent_responses if r.restart_time_hot_hr]
    warm_times = [r.restart_time_warm_hr for r in consistent_responses if r.restart_time_warm_hr]
    cold_times = [r.restart_time_cold_hr for r in consistent_responses if r.restart_time_cold_hr]
    min_temps = [r.min_temp_c for r in consistent_responses if r.min_temp_c]
    
    return OvernightModeParams(
        status=status,
        mode=mode,
        min_temp_c=sum(min_temps) / len(min_temps) if min_temps else None,
        continuous_heat_required=any(r.thermal_continuous_heat for r in consistent_responses),
        restart_time_hot_hr=sum(hot_times) / len(hot_times) if hot_times else None,
        restart_time_warm_hr=sum(warm_times) / len(warm_times) if warm_times else None,
        restart_time_cold_hr=sum(cold_times) / len(cold_times) if cold_times else None,
        shutdown_philosophy=reference.shutdown_philosophy,
        vendor_responses=tuple(responses),
        policy=policy,
    )


@dataclass(frozen=True)
class DischargeParams:
    """Centrate discharge parameters."""
    q_permit_m3_hr: float = 3.0
    window_start_hour: int = 8
    window_end_hour: int = 16
    discharge_days: Tuple[int, ...] = (0, 1, 2, 3, 4)
    min_discharge_level_m3: float = 0.5
    
    def hours_per_week(self) -> float:
        hours_per_day = self.window_end_hour - self.window_start_hour
        return hours_per_day * len(self.discharge_days)


@dataclass(frozen=True)
class ControlParams:
    """Process control parameters."""
    cake_control_tc_hr: float = 24.0
    cake_deadband_fraction: float = 0.10
    cake_feed_slew_kg_hr_per_hr: float = 20.0
    min_on_duration_hr: float = 4.0
    min_off_duration_hr: float = 1.0
    use_feedforward: bool = False


@dataclass(frozen=True)
class OperatingParams:
    """Facility operating parameters."""
    thermal_uptime: float = 0.90
    scheduled_maintenance_days: float = 14.0
    maintenance_months: Tuple[int, ...] = (2,)
    mean_outage_duration_hr: float = 8.0
    outage_rate_per_year: float = 6.0
    receiving_hours_per_day: float = 12.0
    receiving_days_per_week: int = 6
    
    def effective_hours_per_year(self) -> float:
        return 8760 * self.thermal_uptime


@dataclass(frozen=True)
class EconomicParams:
    """
    Economic parameters for financial analysis.
    
    Note: Labor parameters moved to StaffingModel.
    """
    tipping_fee_per_m3: float = 45.0
    char_sale_price_per_tonne: float = 200.0
    carbon_credit_per_tco2e: float = 50.0
    carbon_credits_enabled: bool = False
    electricity_price_kwh: float = 0.12
    natural_gas_price_mj: float = 0.015
    polymer_cost_per_kg: float = 3.0
    # Labor fields removed - see StaffingModel
    screenings_disposal_per_tonne: float = 150.0
    condensate_treatment_per_m3: float = 20.0
    insurance_fraction_of_capex: float = 0.01
    compliance_annual: float = 25000.0
    discount_rate: float = 0.08
    analysis_period_years: int = 20
    debt_fraction: float = 0.70
    interest_rate: float = 0.06
    loan_term_years: int = 15


@dataclass(frozen=True)
class CapexScalingParams:
    """Parametric CAPEX scaling for equipment sizing."""
    eq_tank_ref_size_m3: float = 50.0
    eq_tank_ref_cost: float = 75000.0
    eq_tank_scaling_exp: float = 0.6
    cen_tank_ref_size_m3: float = 30.0
    cen_tank_ref_cost: float = 50000.0
    cen_tank_scaling_exp: float = 0.6
    dewatering_ref_size: float = 5.0
    dewatering_ref_cost: float = 250000.0
    dewatering_scaling_exp: float = 0.7
    dryer_ref_size: float = 100.0
    dryer_ref_cost: float = 400000.0
    dryer_scaling_exp: float = 0.65
    pyro_ref_size: float = 50.0
    pyro_ref_cost: float = 800000.0
    pyro_scaling_exp: float = 0.7
    building_cost_per_m2: float = 1500.0
    site_work_fraction: float = 0.15
    electrical_fraction: float = 0.12
    instrumentation_fraction: float = 0.08
    engineering_fraction: float = 0.15
    contingency_fraction: float = 0.20
    
    # Option B: Co-feed infrastructure (added when cofeed enabled)
    # Includes: receiving pit, walking floor, covered storage, dust/fire control
    cofeed_infrastructure_capex: float = 350000.0
    # Note: operator_complexity_factor moved to OperationsParams


# =============================================================================
# Operating Envelope - Allowable Operating Region
# =============================================================================

class OvernightState(Enum):
    """Allowed overnight operational states.
    
    Defines the set of safe overnight configurations. Each maps to
    a restart penalty and thermal risk profile.
    """
    HOT_HOLD = "hot_hold"                     # Maintain temperature, fastest restart
    WARM_STANDBY = "warm_standby"             # Partial cooling, moderate restart
    CONTROLLED_COOLDOWN = "controlled_cooldown"  # Planned cooling, slow restart
    COLD_SHUTDOWN = "cold_shutdown"            # Full shutdown, longest restart


@dataclass(frozen=True)
class OperatingEnvelope:
    """
    Formal operating envelope defining allowable operating region.
    
    This is the single source of truth for what operating conditions
    are physically and operationally permissible. Used for:
        - Vendor comparison (can the proposed system stay inside?)
        - Facility design input (what ranges must equipment support?)
        - CI gate (reject operating points outside the envelope)
    
    Constraints are based on:
        - Reactor thermal feasibility (heat transfer limits)
        - Process chemistry (residence time, temperature windows)
        - Equipment protection (min wall temperature, TS limits)
        - Operational safety (overnight thermal management)
    
    All values use CONSERVATIVE defaults backed by literature
    and first-principles. Override with vendor-validated data only.
    """
    
    # --- Throughput limits ---
    max_throughput_kgds_hr: float = 50.0      # Max dry solids to pyrolysis
    min_throughput_kgds_hr: float = 10.0      # Min for stable operation (turndown)
    turndown_ratio: float = 0.20              # min/max = 20% turndown
    
    # --- Residence time ---
    min_residence_time_s: float = 600.0       # 10 minutes minimum for >85% conversion
    max_residence_time_s: float = 3600.0      # 60 minutes max (char quality degradation)
    target_residence_time_s: float = 1200.0   # 20 minutes nominal design point
    
    # --- Temperature window ---
    min_wall_temperature_c: float = 450.0     # Below this: incomplete pyrolysis
    max_wall_temperature_c: float = 750.0     # Above this: ash fusion, refractory risk
    target_wall_temperature_c: float = 650.0  # Nominal design point
    min_reactor_temperature_c: float = 400.0  # Min operating temp (process chemistry)
    max_reactor_temperature_c: float = 700.0  # Max operating temp
    
    # --- Feed TS bands ---
    min_feed_ts: float = 0.60                 # Below this: too wet for pyrolysis
    max_feed_ts: float = 0.95                 # Above this: flow/handling issues
    target_feed_ts: float = 0.75              # Nominal dried feed TS
    septage_cake_ts_min: float = 0.15         # Min dewatered cake TS
    septage_cake_ts_max: float = 0.30         # Max dewatered cake TS
    cofeed_ts_min: float = 0.50               # Min co-feed TS (after screening)
    cofeed_ts_max: float = 0.95               # Max co-feed TS
    
    # --- Overnight states ---
    allowed_overnight_states: Tuple[OvernightState, ...] = (
        OvernightState.HOT_HOLD,
        OvernightState.WARM_STANDBY,
        OvernightState.CONTROLLED_COOLDOWN,
    )
    min_overnight_temp_c: float = 200.0       # Below this: tar condensation risk
    max_restart_time_hr: float = 4.0          # Max acceptable restart to full operation
    
    # --- Energy constraints ---
    min_syngas_self_sufficiency: float = 1.0  # Ratio: syngas available / heat demand
    max_aux_fuel_fraction: float = 0.20       # Max fraction of heat from external fuel
    
    # --- Safety margins ---
    thermal_margin_pct: float = 20.0          # Require 20% heat transfer margin
    throughput_safety_factor: float = 0.80    # Operate at 80% of max capacity
    
    def throughput_in_range(self, kgds_hr: float) -> bool:
        """Check if throughput is within allowable range."""
        return self.min_throughput_kgds_hr <= kgds_hr <= self.max_throughput_kgds_hr
    
    def residence_time_in_range(self, seconds: float) -> bool:
        """Check if residence time is within allowable range."""
        return self.min_residence_time_s <= seconds <= self.max_residence_time_s
    
    def wall_temperature_in_range(self, temp_c: float) -> bool:
        """Check if wall temperature is within allowable range."""
        return self.min_wall_temperature_c <= temp_c <= self.max_wall_temperature_c
    
    def feed_ts_in_range(self, ts: float) -> bool:
        """Check if feed total solids is within allowable range."""
        return self.min_feed_ts <= ts <= self.max_feed_ts
    
    def overnight_state_allowed(self, state: OvernightState) -> bool:
        """Check if overnight state is in the allowed set."""
        return state in self.allowed_overnight_states
    
    def overnight_temp_safe(self, temp_c: float) -> bool:
        """Check if overnight hold temperature is above minimum safe value."""
        return temp_c >= self.min_overnight_temp_c


# Default operating envelope (conservative, literature-backed)
OPERATING_ENVELOPE_DEFAULT = OperatingEnvelope()


@dataclass(frozen=True)
class ModelParameters:
    """Complete set of model parameters for a simulation run."""
    version: str = "1.0.0"
    name: str = "baseline_v1.0"
    description: str = "Conservative baseline for Tiny Township"
    
    # ==========================================================================
    # Design Mode: DRL-3 screening vs DRL-4+ design physics
    # ==========================================================================
    # False → fixed-yield pathway (existing DRL-3 economics screening)
    # True  → kinetics + residence-time + heat-transfer gates enforced
    design_mode: bool = False
    
    # Design-grade physics parameters (only used when design_mode=True)
    feedstock_septage: FeedstockProperties = field(default_factory=lambda: SEPTAGE_SOLIDS_DEFAULT)
    feedstock_cofeed: FeedstockProperties = field(default_factory=lambda: WOOD_CHIPS_DEFAULT)
    kinetics_septage: KineticsParams = field(default_factory=lambda: SEPTAGE_KINETICS_DEFAULT)
    kinetics_cofeed: KineticsParams = field(default_factory=lambda: WOOD_KINETICS_DEFAULT)
    reactor: ReactorParams = field(default_factory=lambda: REACTOR_DEFAULT)
    
    # Core process parameters
    service_area: ServiceAreaParams = field(default_factory=ServiceAreaParams)
    dewatering: DeWateringParams = field(default_factory=DeWateringParams)
    dryer: DryerParams = field(default_factory=DryerParams)
    pyrolysis: PyrolysisParams = field(default_factory=PyrolysisParams)
    cofeed: CoFeedParams = field(default_factory=CoFeedParams)
    buffer_storage: BufferStorageParams = field(default_factory=BufferStorageParams)
    off_spec: OffSpecParams = field(default_factory=OffSpecParams)
    overnight_mode: OvernightModeParams = field(default_factory=OvernightModeParams)
    discharge: DischargeParams = field(default_factory=DischargeParams)
    control: ControlParams = field(default_factory=ControlParams)
    operating: OperatingParams = field(default_factory=OperatingParams)
    economic: EconomicParams = field(default_factory=EconomicParams)
    capex_scaling: CapexScalingParams = field(default_factory=CapexScalingParams)
    
    # Staffing model (labor regime) - single source of truth for labor
    staffing: StaffingModel = field(default_factory=StaffingModel.hub_default)
    
    # Operations complexity (OPEX modifiers)
    operations: OperationsParams = field(default_factory=OperationsParams)
    
    # Maintenance model (decomposed cost buckets)
    maintenance: MaintenanceModel = field(default_factory=MaintenanceModel.product_standard)
    
    # Option B: Co-feed supply chain and routing
    cofeed_supply: CofeedSupplyParams = field(default_factory=CofeedSupplyParams)
    cofeed_routing: CofeedRoutingParams = field(default_factory=CofeedRoutingParams)
    
    # Option B: Char quality and revenue
    char_quality: CharQualityParams = field(default_factory=CharQualityParams)
    
    # Option B: Regulatory pathway
    regulatory: RegulatoryParams = field(default_factory=RegulatoryParams)
    deployment: DeploymentParams = field(default_factory=DeploymentParams)
    
    # Operating envelope (allowable operating region)
    envelope: OperatingEnvelope = field(default_factory=OperatingEnvelope)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def compute_hash(self) -> str:
        serialized = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:12]
    
    def get_fingerprint(self) -> str:
        return f"{self.name}_{self.version}_{self.compute_hash()}"
    
    def is_option_b(self) -> bool:
        """Check if this is an Option B (co-feed enabled) configuration."""
        return self.cofeed.enabled


def create_baseline_parameters() -> ModelParameters:
    """Create the locked conservative baseline parameter set."""
    return ModelParameters(
        name="baseline_v1.0",
        description="Conservative baseline for Tiny Township - 5000 m³/yr",
        staffing=StaffingModel.hub_default(),
        operations=OperationsParams(two_stream_mode=False),
    )


def create_cofeed_scenario() -> ModelParameters:
    """Create parameters with co-feed enabled for winter stabilization."""
    return ModelParameters(
        name="cofeed_enabled_v1.0",
        description="Baseline with winter co-feed enabled",
        cofeed=CoFeedParams(enabled=True),
        staffing=StaffingModel.hub_default(),
        operations=OperationsParams(two_stream_mode=True),
    )


def create_high_discharge_scenario() -> ModelParameters:
    """Create parameters with higher centrate discharge rate."""
    return ModelParameters(
        name="high_discharge_v1.0",
        description="Baseline with Q_permit = 5.0 m³/hr",
        discharge=DischargeParams(q_permit_m3_hr=5.0),
        staffing=StaffingModel.hub_default(),
        operations=OperationsParams(two_stream_mode=False),
    )


def create_option_b_scenario(
    annual_cofeed_tds: float = 1200.0,
    cofeed_ts: float = 0.85,
    transport_km: float = 25.0
) -> ModelParameters:
    """
    Create Option B: Solids-centric facility with mandatory co-feed.
    
    This is the only configuration that achieves thermal self-sufficiency
    at the proposed scale. Septage is treated as a compatible secondary
    waste stream, not the energy backbone.
    
    Args:
        annual_cofeed_tds: Annual co-feed dry solids (default 1200 tDS/yr)
        cofeed_ts: Co-feed total solids fraction (default 0.85 for wood)
        transport_km: Average transport distance (default 25 km)
    
    Returns:
        ModelParameters configured for Option B operation
    """
    return ModelParameters(
        name="option_b_cofeed_dominant",
        version="1.0.0",
        description=f"Option B: Solids-centric with {annual_cofeed_tds:.0f} tDS/yr co-feed",
        
        # Enable co-feed with year-round operation
        cofeed=CoFeedParams(
            enabled=True,
            ts_fraction=cofeed_ts,
            cost_per_tds=80.0,
            yield_char_cofeed=0.30,
            yield_gas_cofeed=0.45,
            yield_condensate_cofeed=0.25,
            char_carbon_fraction_cofeed=0.70,
            # Year-round, not just winter
            winter_months=(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11),
        ),
        
        # Supply chain parameters
        cofeed_supply=CofeedSupplyParams(
            transport_km=transport_km,
            annual_target_tds=annual_cofeed_tds,
            seasonal_profile=CofeedSeasonalProfile.WOOD_STEADY,
            contract_security_factor=0.85,
        ),
        
        # Dryer bypass for dry co-feed
        cofeed_routing=CofeedRoutingParams(
            bypass_ts_high=0.70,
            bypass_ts_low=0.60,
            default_bypass_mode=True,
        ),
        
        # Segregated char with conservative pricing
        char_quality=CharQualityParams(
            segregation_enabled=True,
            default_tier_cofeed=2,   # Tier 2: $225/t
            default_tier_septage=3,  # Tier 3: $75/t
        ),
        
        # Biomass hybrid regulatory pathway
        regulatory=RegulatoryParams(
            pathway=RegulatoryPathway.BIOMASS_HYBRID,
            compliance_cost_adder=15000.0,
            permitting_capex_adder=75000.0,
        ),
        
        # Default to hub staffing for Option B base
        staffing=StaffingModel.hub_default(),
        
        # Two-stream operation with complexity factor
        operations=OperationsParams(
            two_stream_mode=True,
            complexity_factor=1.15,
        ),
    )


def create_product_scenario(
    annual_septage_m3: float = 2000.0,
    annual_cofeed_tds: float = 600.0,
    reference_dumping_fee: float = 55.0,
) -> ModelParameters:
    """
    Create Product Mode scenario: owner-operated asset for rural waste handlers.
    
    This is the DEFAULT analytical case for Option B evaluation.
    FROZEN ECONOMICS: Uses product_low_maintenance() as the baseline.
    
    Key characteristics:
        - Labor externalized (owner's time not costed separately)
        - Smaller scale (2,000 m³/yr septage, 600 tDS/yr co-feed)
        - 0.6x CAPEX (modular, smaller equipment)
        - Buyer economics framing (savings vs dumping fees)
        - Low-maintenance design target (~$16k/yr service burden)
    
    Design Requirements (derived from economics):
        - Owner-serviceable: REQUIRED
        - Max callouts: ~0.25/week (1/month)
        - No routine refractory relines
        - Modular wear parts
    
    Args:
        annual_septage_m3: Annual septage volume (default 2,000)
        annual_cofeed_tds: Annual co-feed dry solids (default 600)
        reference_dumping_fee: Current dumping fee buyer pays (default $55/m3)
    
    Returns:
        ModelParameters configured for Product Mode
    """
    from dataclasses import replace
    
    # Start from Option B base
    base = create_option_b_scenario(
        annual_cofeed_tds=annual_cofeed_tds,
    )
    
    # Override with Product Mode deployment params
    deployment = DeploymentParams(
        mode=DeploymentMode.PRODUCT,
        annual_septage_m3=annual_septage_m3,
        annual_cofeed_tds=annual_cofeed_tds,
        capex_multiplier=0.6,
        reference_dumping_fee=reference_dumping_fee,
    )
    
    # Owner-operated staffing: cash labor = 0, owner time tracked
    staffing = StaffingModel.owner_op(owner_hours=5.0)
    
    # FROZEN: Low-maintenance design as the economic baseline
    # This is the viability requirement, not a preference
    maintenance = MaintenanceModel.product_low_maintenance()
    
    # Scale service area
    new_service = replace(base.service_area, annual_septage_m3=annual_septage_m3)
    
    # Update cofeed supply
    new_supply = replace(base.cofeed_supply, annual_target_tds=annual_cofeed_tds)
    
    return replace(
        base,
        name="product_mode_owner_operated",
        description=f"Product Mode: {annual_septage_m3:.0f} m3/yr septage, {annual_cofeed_tds:.0f} tDS/yr co-feed (low-maint)",
        service_area=new_service,
        cofeed_supply=new_supply,
        deployment=deployment,
        staffing=staffing,
        maintenance=maintenance,
    )


def create_hub_scenario(
    annual_septage_m3: float = 5000.0,
    annual_cofeed_tds: float = 1200.0,
) -> ModelParameters:
    """
    Create Regional Hub scenario: staffed centralized facility.
    
    Key characteristics:
        - Light operations (daytime staff + on-call, NOT fully staffed)
        - Full scale (5,000 m³/yr septage, 1,200 tDS/yr co-feed)
        - Full CAPEX (1.0×)
        - Facility NOI framing
        
    Note: Uses hub_light_ops staffing (~$133k/yr labor).
    For fully-staffed hub (~$275k/yr), use create_hub_staffed_scenario().
    
    Args:
        annual_septage_m3: Annual septage volume (default 5,000)
        annual_cofeed_tds: Annual co-feed dry solids (default 1,200)
    
    Returns:
        ModelParameters configured for Regional Hub Mode (light ops)
    """
    from dataclasses import replace
    
    # Start from Option B base
    base = create_option_b_scenario(
        annual_cofeed_tds=annual_cofeed_tds,
    )
    
    # Override with Hub Mode deployment params
    deployment = DeploymentParams(
        mode=DeploymentMode.REGIONAL_HUB,
        annual_septage_m3=annual_septage_m3,
        annual_cofeed_tds=annual_cofeed_tds,
        capex_multiplier=1.0,
    )
    
    # Light ops: Daytime staffed with on-call for nights/weekends
    # Use hub_light_ops() for clarity (48% of fully-staffed labor cost)
    staffing = StaffingModel.hub_light_ops()
    
    # Scale service area
    new_service = replace(base.service_area, annual_septage_m3=annual_septage_m3)
    
    # Update cofeed supply
    new_supply = replace(base.cofeed_supply, annual_target_tds=annual_cofeed_tds)
    
    return replace(
        base,
        name="hub_mode_light_ops",
        description=f"Hub Mode (Light Ops): {annual_septage_m3:.0f} m³/yr septage, {annual_cofeed_tds:.0f} tDS/yr co-feed",
        service_area=new_service,
        cofeed_supply=new_supply,
        deployment=deployment,
        staffing=staffing,
    )


def create_hub_staffed_scenario(
    annual_septage_m3: float = 5000.0,
    annual_cofeed_tds: float = 1200.0,
) -> ModelParameters:
    """
    Create Regional Hub scenario with FULL staffing.
    
    Key characteristics:
        - Fully staffed (2 shifts/day, 7 days/week)
        - Full scale (5,000 m³/yr septage, 1,200 tDS/yr co-feed)
        - Full CAPEX (1.0×)
        - Facility NOI framing
        
    Note: Uses hub_staffed staffing (~$275k/yr labor).
    This typically results in negative NOI under current assumptions.
    For light-ops hub (~$133k/yr), use create_hub_scenario().
    
    Args:
        annual_septage_m3: Annual septage volume (default 5,000)
        annual_cofeed_tds: Annual co-feed dry solids (default 1,200)
    
    Returns:
        ModelParameters configured for Regional Hub Mode (fully staffed)
    """
    from dataclasses import replace
    
    # Start from light-ops hub, override staffing
    base = create_hub_scenario(
        annual_septage_m3=annual_septage_m3,
        annual_cofeed_tds=annual_cofeed_tds,
    )
    
    # Override to fully staffed
    staffing = StaffingModel.hub_staffed()
    
    return replace(
        base,
        name="hub_mode_fully_staffed",
        description=f"Hub Mode (Fully Staffed): {annual_septage_m3:.0f} m³/yr septage, {annual_cofeed_tds:.0f} tDS/yr co-feed",
        staffing=staffing,
    )
