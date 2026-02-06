"""
Stream Pathways Module - Value-Add Options for Waste Streams.

This module defines pathway options for each waste stream, enabling scenario-based
comparison of disposal-only vs. value-add economics.

Design Philosophy:
    - You are no longer "disposing waste" — you are managing secondary feedstocks
    - Each stream has disposition options tagged by maturity (NEAR_TERM, MID_TERM, SPECULATIVE)
    - Pathway params include default CAPEX/OPEX with user override capability
    - Scenario risk levels filter which pathways are included in analysis

Stream Categories:
    - Centrate: Liquid phase after dewatering (nutrients, organics)
    - Char: Primary solid product (carbon-rich, tunable properties)
    - Syngas: Gaseous product (variable composition, dispatchable energy)
    - Screenings/Grit: Solid rejects (low value, stable)
    - Off-Spec: Contaminated/rejected loads (liability management)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from enum import Enum
from typing import Optional, Tuple, Dict, List


# =============================================================================
# Maturity & Risk Classification
# =============================================================================

class PathwayMaturity(Enum):
    """Technology readiness level for value-add pathways."""
    NEAR_TERM = "near_term"          # Proven tech, <2yr deployment, low regulatory risk
    MID_TERM = "mid_term"            # R&D phase, 2-5yr horizon, moderate risk
    SPECULATIVE = "speculative"      # Conceptual, 5+ yr or heavy regulatory burden


class ScenarioRisk(Enum):
    """Risk tolerance for scenario analysis."""
    CONSERVATIVE = "conservative"    # NEAR_TERM pathways only
    MODERATE = "moderate"            # NEAR_TERM + MID_TERM pathways
    OPTIMISTIC = "optimistic"        # All pathways including SPECULATIVE


class HeatGrade(Enum):
    """
    Heat quality classification by temperature range.
    
    Thermodynamic principle: Higher grade heat can supply lower grade needs,
    but not vice versa. This prevents cascading errors in heat integration.
    """
    LOW = "low"           # <100°C: drying assist, space heating
    MEDIUM = "medium"     # 100-300°C: drying, distillation, evaporation
    HIGH = "high"         # >300°C: pyrolysis, steam generation, char activation


# Heat grade ordering for compatibility checks
_HEAT_GRADE_ORDER = {HeatGrade.LOW: 0, HeatGrade.MEDIUM: 1, HeatGrade.HIGH: 2}


def heat_grade_compatible(supplied: HeatGrade, required: HeatGrade) -> bool:
    """
    Check if supplied heat grade can satisfy required heat grade.
    
    Higher grade heat can supply lower grade needs (with exergy loss),
    but lower grade cannot supply higher grade needs.
    
    Args:
        supplied: The heat grade available from source
        required: The heat grade needed by consumer
        
    Returns:
        True if supplied can satisfy required
    """
    return _HEAT_GRADE_ORDER[supplied] >= _HEAT_GRADE_ORDER[required]


class PathwayTier(Enum):
    """Economic tier classification for pathways."""
    DISPOSAL_ONLY = "disposal_only"  # Cost center, no value recovery
    RECOVERABLE = "recoverable"      # Modest value recovery, proven markets
    UPGRADABLE = "upgradable"        # High value potential, requires processing


def pathway_allowed(maturity: PathwayMaturity, risk: ScenarioRisk) -> bool:
    """Check if a pathway maturity is allowed under given scenario risk."""
    if risk == ScenarioRisk.OPTIMISTIC:
        return True
    elif risk == ScenarioRisk.MODERATE:
        return maturity in (PathwayMaturity.NEAR_TERM, PathwayMaturity.MID_TERM)
    else:  # CONSERVATIVE
        return maturity == PathwayMaturity.NEAR_TERM


# =============================================================================
# Centrate Pathways
# =============================================================================

class CentratePathway(Enum):
    """Disposition options for centrate (liquid phase after dewatering)."""
    # Disposal-only (baseline)
    LOCAL_DISCHARGE = "local_discharge"      # Permitted discharge to municipal system
    HAUL_OFF = "haul_off"                    # Tanker to WWTP
    LAGOON = "lagoon"                        # On-site storage lagoon
    
    # Recoverable (near-term)
    NUTRIENT_CONCENTRATE = "nutrient_concentrate"  # Evaporate/RO to reduce haul volume
    STRUVITE_RECOVERY = "struvite_recovery"        # Phosphorus recovery as MgNH4PO4
    AMMONIA_STRIPPING = "ammonia_stripping"        # N recovery as ammonium sulfate
    
    # Upgradable (mid-term)
    ELECTROCHEMICAL = "electrochemical"            # Electrodialysis nutrient separation
    ALGAE_CULTIVATION = "algae_cultivation"        # Contained algae/duckweed growth
    
    # Speculative
    MICROBIAL_PROTEIN = "microbial_protein"        # Single-cell protein production


# Pathway metadata
CENTRATE_PATHWAY_INFO = {
    CentratePathway.LOCAL_DISCHARGE: {
        "tier": PathwayTier.DISPOSAL_ONLY,
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "Permitted discharge to municipal sewer",
    },
    CentratePathway.HAUL_OFF: {
        "tier": PathwayTier.DISPOSAL_ONLY,
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "Tanker haul to WWTP for treatment",
    },
    CentratePathway.LAGOON: {
        "tier": PathwayTier.DISPOSAL_ONLY,
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "On-site facultative lagoon storage",
    },
    CentratePathway.NUTRIENT_CONCENTRATE: {
        "tier": PathwayTier.RECOVERABLE,
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "Volume reduction via evaporation or RO",
    },
    CentratePathway.STRUVITE_RECOVERY: {
        "tier": PathwayTier.RECOVERABLE,
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "Phosphorus precipitation as struvite fertilizer",
    },
    CentratePathway.AMMONIA_STRIPPING: {
        "tier": PathwayTier.RECOVERABLE,
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "Nitrogen recovery via air/steam stripping",
    },
    CentratePathway.ELECTROCHEMICAL: {
        "tier": PathwayTier.UPGRADABLE,
        "maturity": PathwayMaturity.MID_TERM,
        "description": "Electrodialysis or electrocoagulation",
    },
    CentratePathway.ALGAE_CULTIVATION: {
        "tier": PathwayTier.UPGRADABLE,
        "maturity": PathwayMaturity.MID_TERM,
        "description": "Contained algae/duckweed biomass production",
    },
    CentratePathway.MICROBIAL_PROTEIN: {
        "tier": PathwayTier.UPGRADABLE,
        "maturity": PathwayMaturity.SPECULATIVE,
        "description": "Single-cell protein from bacterial/yeast culture",
    },
}


@dataclass(frozen=True)
class StruvitePathwayParams:
    """Parameters for struvite (phosphorus) recovery from centrate."""
    enabled: bool = False
    maturity: PathwayMaturity = PathwayMaturity.NEAR_TERM
    tier: PathwayTier = PathwayTier.RECOVERABLE
    
    # Recovery efficiency
    p_recovery_efficiency: float = 0.85       # Fraction of P recovered
    mg_dose_ratio: float = 1.3                # Mg:P molar ratio
    
    # Economics (defaults)
    capex_default: float = 55_000.0           # $ installed (small reactor + dosing)
    opex_annual_default: float = 8_500.0      # $/yr (MgCl2, power, maintenance)
    struvite_revenue_per_tonne: float = 200.0 # $/tonne product
    
    # User overrides
    capex_override: Optional[float] = None
    opex_override: Optional[float] = None
    
    @property
    def capex(self) -> float:
        return self.capex_override if self.capex_override is not None else self.capex_default
    
    @property
    def opex_annual(self) -> float:
        return self.opex_override if self.opex_override is not None else self.opex_annual_default


@dataclass(frozen=True)
class AmmoniaStrippingParams:
    """Parameters for ammonia stripping and capture."""
    enabled: bool = False
    maturity: PathwayMaturity = PathwayMaturity.NEAR_TERM
    tier: PathwayTier = PathwayTier.RECOVERABLE
    
    # Recovery efficiency
    n_recovery_efficiency: float = 0.75       # Fraction of NH4-N recovered
    acid_consumption_kg_per_kg_n: float = 3.5 # kg H2SO4 per kg N captured
    
    # Economics
    capex_default: float = 85_000.0           # $ installed (tower + scrubber)
    opex_annual_default: float = 12_000.0     # $/yr (acid, power, steam if needed)
    ammonium_sulfate_revenue_per_tonne: float = 180.0  # $/tonne (21-0-0)
    
    capex_override: Optional[float] = None
    opex_override: Optional[float] = None
    
    @property
    def capex(self) -> float:
        return self.capex_override if self.capex_override is not None else self.capex_default
    
    @property
    def opex_annual(self) -> float:
        return self.opex_override if self.opex_override is not None else self.opex_annual_default


@dataclass(frozen=True)
class NutrientConcentrateParams:
    """Parameters for centrate volume reduction (evaporation/RO)."""
    enabled: bool = False
    maturity: PathwayMaturity = PathwayMaturity.NEAR_TERM
    tier: PathwayTier = PathwayTier.RECOVERABLE
    
    # Process
    volume_reduction_factor: float = 5.0      # 5:1 concentration ratio
    uses_waste_heat: bool = True              # Leverages pyrolysis waste heat
    
    # Economics
    capex_default: float = 40_000.0           # $ installed (evaporator or small RO)
    opex_annual_default: float = 5_000.0      # $/yr (power, membrane replacement)
    haul_cost_savings_per_m3: float = 25.0    # $/m³ avoided haul cost
    
    capex_override: Optional[float] = None
    opex_override: Optional[float] = None
    
    @property
    def capex(self) -> float:
        return self.capex_override if self.capex_override is not None else self.capex_default
    
    @property
    def opex_annual(self) -> float:
        return self.opex_override if self.opex_override is not None else self.opex_annual_default


# =============================================================================
# Char Pathways
# =============================================================================

class CharPathway(Enum):
    """Disposition options for pyrolysis char."""
    # Disposal-only (baseline alternatives)
    LANDFILL_COVER = "landfill_cover"         # Tier-3: lowest value
    
    # Recoverable (current model)
    BULK_SOIL_AMENDMENT = "bulk_soil_amendment"   # Tier-2: agriculture, reclamation
    PREMIUM_CERTIFIED = "premium_certified"       # Tier-1: IBI-certified
    COMPOST_BLEND = "compost_blend"               # Manure/compost amendment
    SEPTIC_MEDIA = "septic_media"                 # Leach field adsorptive media
    
    # Upgradable (mid-term)
    ACTIVATED_BIOCHAR = "activated_biochar"       # Steam/CO2 activation
    BUILDING_MATERIALS = "building_materials"     # Char-cement, char-asphalt
    
    # Speculative
    ELECTRODE_MATERIAL = "electrode_material"     # Supercapacitors, soil batteries


CHAR_PATHWAY_INFO = {
    CharPathway.LANDFILL_COVER: {
        "tier": PathwayTier.DISPOSAL_ONLY,
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "Alternative daily cover / landfill amendment",
    },
    CharPathway.BULK_SOIL_AMENDMENT: {
        "tier": PathwayTier.RECOVERABLE,
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "Bulk soil amendment for agriculture/reclamation",
    },
    CharPathway.PREMIUM_CERTIFIED: {
        "tier": PathwayTier.RECOVERABLE,
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "IBI-certified premium biochar",
    },
    CharPathway.COMPOST_BLEND: {
        "tier": PathwayTier.RECOVERABLE,
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "Blended with manure/compost for odour control",
    },
    CharPathway.SEPTIC_MEDIA: {
        "tier": PathwayTier.RECOVERABLE,
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "Adsorptive media for septic leach fields",
    },
    CharPathway.ACTIVATED_BIOCHAR: {
        "tier": PathwayTier.UPGRADABLE,
        "maturity": PathwayMaturity.MID_TERM,
        "description": "Low-temp steam/CO2 activation for filtration",
    },
    CharPathway.BUILDING_MATERIALS: {
        "tier": PathwayTier.UPGRADABLE,
        "maturity": PathwayMaturity.MID_TERM,
        "description": "Carbon-negative cement or asphalt blends",
    },
    CharPathway.ELECTRODE_MATERIAL: {
        "tier": PathwayTier.UPGRADABLE,
        "maturity": PathwayMaturity.SPECULATIVE,
        "description": "Low-grade electrode for supercapacitors",
    },
}


@dataclass(frozen=True)
class CharActivationParams:
    """Parameters for on-site char activation (upgrading to activated carbon)."""
    enabled: bool = False
    maturity: PathwayMaturity = PathwayMaturity.MID_TERM
    tier: PathwayTier = PathwayTier.UPGRADABLE
    
    # Process
    activation_method: str = "steam"          # "steam" or "co2"
    activation_yield: float = 0.85            # Mass yield (char in → activated out)
    surface_area_target_m2_g: float = 400.0   # BET surface area target
    
    # Economics
    capex_default: float = 75_000.0           # $ installed (activation furnace)
    opex_annual_default: float = 15_000.0     # $/yr (steam, CO2, power)
    activated_char_premium_per_tonne: float = 350.0  # $/tonne over bulk char
    
    capex_override: Optional[float] = None
    opex_override: Optional[float] = None
    
    @property
    def capex(self) -> float:
        return self.capex_override if self.capex_override is not None else self.capex_default
    
    @property
    def opex_annual(self) -> float:
        return self.opex_override if self.opex_override is not None else self.opex_annual_default


@dataclass(frozen=True)
class SepticMediaParams:
    """Parameters for char as septic leach field media."""
    enabled: bool = False
    maturity: PathwayMaturity = PathwayMaturity.NEAR_TERM
    tier: PathwayTier = PathwayTier.RECOVERABLE
    
    # Market
    target_particle_size_mm: Tuple[float, float] = (2.0, 10.0)  # Grading spec
    septic_industry_premium_per_tonne: float = 75.0  # $/tonne over bulk
    
    # No significant CAPEX (screening/grading)
    capex_default: float = 5_000.0            # Screening equipment
    opex_annual_default: float = 1_000.0      # Minimal
    
    capex_override: Optional[float] = None
    opex_override: Optional[float] = None
    
    @property
    def capex(self) -> float:
        return self.capex_override if self.capex_override is not None else self.capex_default
    
    @property
    def opex_annual(self) -> float:
        return self.opex_override if self.opex_override is not None else self.opex_annual_default


# =============================================================================
# Syngas / Energy Pathways
# =============================================================================

class SyngasPathway(Enum):
    """Disposition options for syngas and excess thermal energy."""
    # Baseline (current)
    PROCESS_HEAT_ONLY = "process_heat_only"   # Internal combustion for drying
    
    # Recoverable
    HEAT_EXPORT = "heat_export"               # Dry biomass, heat greenhouses
    CHP_ELECTRICITY = "chp_electricity"       # Microturbine or engine genset
    
    # Upgradable (mid-term)
    THERMAL_DESALINATION = "thermal_desalination"  # Centrate concentration
    BIO_OIL_REFORMING = "bio_oil_reforming"        # Condensate upgrading
    
    # Speculative
    HYDROGEN_PRODUCTION = "hydrogen_production"    # Syngas reforming to H2


SYNGAS_PATHWAY_INFO = {
    SyngasPathway.PROCESS_HEAT_ONLY: {
        "tier": PathwayTier.DISPOSAL_ONLY,  # Not really disposal, but baseline
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "Syngas combustion for process heat only",
    },
    SyngasPathway.HEAT_EXPORT: {
        "tier": PathwayTier.RECOVERABLE,
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "Export heat to adjacent processes/buildings",
    },
    SyngasPathway.CHP_ELECTRICITY: {
        "tier": PathwayTier.RECOVERABLE,
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "Combined heat & power with grid export",
    },
    SyngasPathway.THERMAL_DESALINATION: {
        "tier": PathwayTier.UPGRADABLE,
        "maturity": PathwayMaturity.MID_TERM,
        "description": "Waste heat for centrate volume reduction",
    },
    SyngasPathway.BIO_OIL_REFORMING: {
        "tier": PathwayTier.UPGRADABLE,
        "maturity": PathwayMaturity.MID_TERM,
        "description": "Pyrolysis condensate reforming to syngas",
    },
    SyngasPathway.HYDROGEN_PRODUCTION: {
        "tier": PathwayTier.UPGRADABLE,
        "maturity": PathwayMaturity.SPECULATIVE,
        "description": "Water-gas shift for hydrogen production",
    },
}


@dataclass(frozen=True)
class CHPParams:
    """Parameters for combined heat and power generation."""
    enabled: bool = False
    maturity: PathwayMaturity = PathwayMaturity.NEAR_TERM
    tier: PathwayTier = PathwayTier.RECOVERABLE
    
    # Performance
    electrical_efficiency: float = 0.25       # Syngas → electricity
    thermal_efficiency: float = 0.55          # Syngas → usable heat
    capacity_kw_e: float = 25.0               # Electrical capacity
    
    # Grid connection
    grid_export_enabled: bool = False
    export_rate_per_kwh: float = 0.08         # $/kWh (varies by jurisdiction)
    
    # Economics
    capex_default: float = 120_000.0          # $ installed (engine + controls)
    opex_annual_default: float = 8_000.0      # $/yr (maintenance, overhauls)
    
    capex_override: Optional[float] = None
    opex_override: Optional[float] = None
    
    @property
    def capex(self) -> float:
        return self.capex_override if self.capex_override is not None else self.capex_default
    
    @property
    def opex_annual(self) -> float:
        return self.opex_override if self.opex_override is not None else self.opex_annual_default


@dataclass(frozen=True)
class HeatExportParams:
    """Parameters for excess heat export to adjacent users."""
    enabled: bool = False
    maturity: PathwayMaturity = PathwayMaturity.NEAR_TERM
    tier: PathwayTier = PathwayTier.RECOVERABLE
    
    # Heat availability
    exportable_fraction: float = 0.30         # Fraction of waste heat exportable
    heat_rate_per_gj: float = 8.0             # $/GJ (district heat typical)
    
    # Economics
    capex_default: float = 25_000.0           # $ installed (piping, heat exchanger)
    opex_annual_default: float = 2_000.0      # $/yr
    
    capex_override: Optional[float] = None
    opex_override: Optional[float] = None
    
    @property
    def capex(self) -> float:
        return self.capex_override if self.capex_override is not None else self.capex_default
    
    @property
    def opex_annual(self) -> float:
        return self.opex_override if self.opex_override is not None else self.opex_annual_default


# =============================================================================
# Screenings / Grit / Ash Pathways
# =============================================================================

class ScreeningsPathway(Enum):
    """Disposition options for screenings, grit, and ash."""
    # Disposal-only (baseline)
    LANDFILL_DISPOSAL = "landfill_disposal"   # Standard MSW landfill
    
    # Recoverable
    ALTERNATIVE_COVER = "alternative_cover"   # Landfill daily cover
    ROAD_BASE = "road_base"                   # Sub-base aggregate blend
    
    # Upgradable (mid-term)
    GEOPOLYMER_FEEDSTOCK = "geopolymer_feedstock"  # Ash for geopolymer cement


SCREENINGS_PATHWAY_INFO = {
    ScreeningsPathway.LANDFILL_DISPOSAL: {
        "tier": PathwayTier.DISPOSAL_ONLY,
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "Standard landfill disposal",
    },
    ScreeningsPathway.ALTERNATIVE_COVER: {
        "tier": PathwayTier.RECOVERABLE,
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "Alternative daily cover at landfill",
    },
    ScreeningsPathway.ROAD_BASE: {
        "tier": PathwayTier.RECOVERABLE,
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "Blended into road sub-base aggregate",
    },
    ScreeningsPathway.GEOPOLYMER_FEEDSTOCK: {
        "tier": PathwayTier.UPGRADABLE,
        "maturity": PathwayMaturity.MID_TERM,
        "description": "Ash as silica/alumina source for geopolymer",
    },
}


@dataclass(frozen=True)
class ScreeningsReuseParams:
    """Parameters for screenings/grit/ash beneficial reuse."""
    enabled: bool = False
    maturity: PathwayMaturity = PathwayMaturity.NEAR_TERM
    tier: PathwayTier = PathwayTier.RECOVERABLE
    
    # Reuse pathway
    pathway: ScreeningsPathway = ScreeningsPathway.LANDFILL_DISPOSAL
    
    # Volume estimates
    screenings_fraction_of_feed: float = 0.005   # ~0.5% of incoming septage
    grit_fraction_of_feed: float = 0.002         # ~0.2%
    ash_fraction_of_char: float = 0.15           # 15% of char is ash
    
    # Economics (avoided disposal cost)
    landfill_cost_per_tonne: float = 85.0        # $/tonne disposal
    reuse_credit_per_tonne: float = 10.0         # $/tonne if beneficial reuse
    
    # Minimal CAPEX for reuse pathway
    capex_default: float = 0.0
    opex_annual_default: float = 0.0
    
    capex_override: Optional[float] = None
    opex_override: Optional[float] = None
    
    @property
    def capex(self) -> float:
        return self.capex_override if self.capex_override is not None else self.capex_default
    
    @property
    def opex_annual(self) -> float:
        return self.opex_override if self.opex_override is not None else self.opex_annual_default


# =============================================================================
# Off-Spec Pathways
# =============================================================================

class OffSpecPathway(Enum):
    """Disposition options for off-spec / contaminated loads."""
    # Disposal-only (baseline)
    HAUL_OFF_DISPOSAL = "haul_off_disposal"   # External disposal at WWTP/HHW
    
    # Recoverable
    THERMAL_DESTRUCTION = "thermal_destruction"    # Metered pyrolysis injection
    BLEND_BACK = "blend_back"                      # Controlled blending into EQ
    
    # Mid-term
    QUARANTINE_CAMPAIGNS = "quarantine_campaigns"  # Batch processing with low-grade char


OFFSPEC_PATHWAY_INFO = {
    OffSpecPathway.HAUL_OFF_DISPOSAL: {
        "tier": PathwayTier.DISPOSAL_ONLY,
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "External haul-off to licensed disposal",
    },
    OffSpecPathway.THERMAL_DESTRUCTION: {
        "tier": PathwayTier.RECOVERABLE,
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "Metered injection into pyrolysis reactor",
    },
    OffSpecPathway.BLEND_BACK: {
        "tier": PathwayTier.RECOVERABLE,
        "maturity": PathwayMaturity.NEAR_TERM,
        "description": "Controlled blending into normal feed stream",
    },
    OffSpecPathway.QUARANTINE_CAMPAIGNS: {
        "tier": PathwayTier.RECOVERABLE,
        "maturity": PathwayMaturity.MID_TERM,
        "description": "Dedicated batch processing campaigns",
    },
}


@dataclass(frozen=True)
class OffSpecThermalParams:
    """Parameters for off-spec thermal destruction via pyrolysis."""
    enabled: bool = False
    maturity: PathwayMaturity = PathwayMaturity.NEAR_TERM
    tier: PathwayTier = PathwayTier.RECOVERABLE
    
    # Process limits
    max_injection_rate_fraction: float = 0.05  # Max 5% of feed rate
    requires_screening: bool = True
    
    # Char routing
    char_to_tier3_only: bool = True            # Force low-grade char routing
    
    # Economics (avoided haul-off)
    haul_off_cost_per_m3: float = 85.0         # Avoided cost
    
    capex_default: float = 0.0                 # No extra CAPEX (existing reactor)
    opex_annual_default: float = 0.0
    
    capex_override: Optional[float] = None
    opex_override: Optional[float] = None
    
    @property
    def capex(self) -> float:
        return self.capex_override if self.capex_override is not None else self.capex_default
    
    @property
    def opex_annual(self) -> float:
        return self.opex_override if self.opex_override is not None else self.opex_annual_default


# =============================================================================
# Circular Loop (Phase 2 Stub)
# =============================================================================

@dataclass(frozen=True)
class CircularLoopParams:
    """Centrate → Algae → Pyrolysis → Char circularity (Phase 2 stub).
    
    This is flagged as SPECULATIVE and disabled by default.
    Phase 2 will implement dynamic mass recirculation modeling.
    """
    enabled: bool = False
    maturity: PathwayMaturity = PathwayMaturity.SPECULATIVE
    tier: PathwayTier = PathwayTier.UPGRADABLE
    
    # Static assumptions (Phase 2 will make dynamic)
    algae_yield_kg_per_m3_centrate: float = 2.5  # Conservative dry biomass yield
    algae_ts_fraction: float = 0.20              # Harvested algae solids
    recirculation_fraction: float = 0.0          # 0 = no loop, 1 = full loop
    
    # Placeholder for dynamic coupling
    dynamic_model_enabled: bool = False          # Phase 2 flag
    
    # Economics (speculative)
    capex_default: float = 150_000.0             # Photobioreactor + harvesting
    opex_annual_default: float = 20_000.0        # Power, nutrients, maintenance
    
    capex_override: Optional[float] = None
    opex_override: Optional[float] = None
    
    @property
    def capex(self) -> float:
        return self.capex_override if self.capex_override is not None else self.capex_default
    
    @property
    def opex_annual(self) -> float:
        return self.opex_override if self.opex_override is not None else self.opex_annual_default


# =============================================================================
# Meta-Products (Economic Outputs, Not Physical Streams)
# =============================================================================

@dataclass(frozen=True)
class MetaProductParams:
    """Non-physical economic value streams."""
    
    # Avoided disposal credits (already primary lever)
    avoided_disposal_enabled: bool = True
    
    # Carbon removal certificates
    carbon_credits_enabled: bool = False
    carbon_credit_price_per_tonne_co2e: float = 50.0  # $/tonne CO2e
    char_carbon_fraction: float = 0.70                # C content of char
    permanence_discount: float = 0.80                 # Accounting for permanence
    
    # Regulatory compliance as a service
    compliance_service_enabled: bool = False
    compliance_premium_per_m3: float = 15.0           # Premium for problem loads


# =============================================================================
# Aggregate Pathway Configuration
# =============================================================================

@dataclass(frozen=True)
class StreamPathwayConfig:
    """Complete pathway configuration for all waste streams."""
    
    # Centrate pathways
    centrate_primary: CentratePathway = CentratePathway.LOCAL_DISCHARGE
    struvite: StruvitePathwayParams = StruvitePathwayParams()
    ammonia_stripping: AmmoniaStrippingParams = AmmoniaStrippingParams()
    nutrient_concentrate: NutrientConcentrateParams = NutrientConcentrateParams()
    
    # Char pathways
    char_primary: CharPathway = CharPathway.BULK_SOIL_AMENDMENT
    char_activation: CharActivationParams = CharActivationParams()
    septic_media: SepticMediaParams = SepticMediaParams()
    
    # Syngas/energy pathways
    syngas_primary: SyngasPathway = SyngasPathway.PROCESS_HEAT_ONLY
    chp: CHPParams = CHPParams()
    heat_export: HeatExportParams = HeatExportParams()
    
    # Screenings/grit/ash
    screenings_primary: ScreeningsPathway = ScreeningsPathway.LANDFILL_DISPOSAL
    screenings_reuse: ScreeningsReuseParams = ScreeningsReuseParams()
    
    # Off-spec
    offspec_primary: OffSpecPathway = OffSpecPathway.HAUL_OFF_DISPOSAL
    offspec_thermal: OffSpecThermalParams = OffSpecThermalParams()
    
    # Circular loop (Phase 2)
    circular_loop: CircularLoopParams = CircularLoopParams()
    
    # Meta-products
    meta_products: MetaProductParams = MetaProductParams()
    
    def get_enabled_pathways(self, risk: ScenarioRisk = ScenarioRisk.CONSERVATIVE) -> list:
        """Return list of enabled pathways that pass maturity filter."""
        enabled = []
        
        # Check each pathway param
        pathway_params = [
            self.struvite,
            self.ammonia_stripping,
            self.nutrient_concentrate,
            self.char_activation,
            self.septic_media,
            self.chp,
            self.heat_export,
            self.screenings_reuse,
            self.offspec_thermal,
            self.circular_loop,
        ]
        
        for p in pathway_params:
            if p.enabled and pathway_allowed(p.maturity, risk):
                enabled.append(p)
        
        return enabled
    
    def total_pathway_capex(self, risk: ScenarioRisk = ScenarioRisk.CONSERVATIVE) -> float:
        """Sum CAPEX for all enabled pathways under given risk level."""
        return sum(p.capex for p in self.get_enabled_pathways(risk))
    
    def total_pathway_opex(self, risk: ScenarioRisk = ScenarioRisk.CONSERVATIVE) -> float:
        """Sum annual OPEX for all enabled pathways under given risk level."""
        return sum(p.opex_annual for p in self.get_enabled_pathways(risk))


# =============================================================================
# Default Configurations
# =============================================================================

# Baseline: disposal-only, no value-add
BASELINE_PATHWAYS = StreamPathwayConfig()

# Conservative: near-term value-add only
CONSERVATIVE_PATHWAYS = StreamPathwayConfig(
    struvite=StruvitePathwayParams(enabled=True),
    heat_export=HeatExportParams(enabled=True),
    septic_media=SepticMediaParams(enabled=True),
    offspec_thermal=OffSpecThermalParams(enabled=True),
)

# Moderate: near-term + mid-term
MODERATE_PATHWAYS = StreamPathwayConfig(
    struvite=StruvitePathwayParams(enabled=True),
    ammonia_stripping=AmmoniaStrippingParams(enabled=True),
    heat_export=HeatExportParams(enabled=True),
    chp=CHPParams(enabled=True),
    char_activation=CharActivationParams(enabled=True),
    septic_media=SepticMediaParams(enabled=True),
    offspec_thermal=OffSpecThermalParams(enabled=True),
    screenings_reuse=ScreeningsReuseParams(enabled=True, pathway=ScreeningsPathway.ALTERNATIVE_COVER),
)

# Full circular: all pathways including speculative
FULL_CIRCULAR_PATHWAYS = StreamPathwayConfig(
    struvite=StruvitePathwayParams(enabled=True),
    ammonia_stripping=AmmoniaStrippingParams(enabled=True),
    nutrient_concentrate=NutrientConcentrateParams(enabled=True),
    heat_export=HeatExportParams(enabled=True),
    chp=CHPParams(enabled=True, grid_export_enabled=True),
    char_activation=CharActivationParams(enabled=True),
    septic_media=SepticMediaParams(enabled=True),
    offspec_thermal=OffSpecThermalParams(enabled=True),
    screenings_reuse=ScreeningsReuseParams(enabled=True, pathway=ScreeningsPathway.ROAD_BASE),
    circular_loop=CircularLoopParams(enabled=True, recirculation_fraction=0.5),
    meta_products=MetaProductParams(carbon_credits_enabled=True),
)


# =============================================================================
# Heat Stream Management
# =============================================================================

@dataclass(frozen=True)
class HeatStream:
    """
    Represents a heat stream with quantity, quality grade, and source tracking.
    
    Heat streams are produced by thermal processes and consumed by downstream
    pathways. The grade determines compatibility with consumer requirements.
    """
    mj_per_hour: float
    grade: HeatGrade
    source: str  # e.g., "pyrolysis_exhaust", "chp_jacket", "condenser"
    
    def can_supply(self, required_grade: HeatGrade) -> bool:
        """Check if this stream can supply the required heat grade."""
        return heat_grade_compatible(self.grade, required_grade)


# Heat requirements by consumer pathway
HEAT_REQUIREMENTS: Dict[str, HeatGrade] = {
    "dryer": HeatGrade.MEDIUM,              # 100-200°C for evaporation
    "ammonia_stripping": HeatGrade.LOW,     # Steam assist, <100°C
    "char_activation": HeatGrade.HIGH,      # >600°C for steam activation
    "heat_export": HeatGrade.LOW,           # Building/greenhouse heat
    "evaporator": HeatGrade.MEDIUM,         # Centrate concentration
}


# =============================================================================
# Circular Pathway Framework (Phase 2 Stub)
# =============================================================================

# Circular pathways require DRL-5+ to avoid premature feedback loops
CIRCULAR_PATHWAY_MIN_DRL = 5


class CircularPathway(ABC):
    """
    Abstract base class for pathways with feedback loops.
    
    Circular pathways recycle outputs back to inputs, requiring iterative
    convergence. This is a Phase 2 stub - actual iteration is blocked until
    DRL-5 validation complete.
    
    Design principle: Stub the framework now, no actual cycles until Phase 2.
    This lets us write the interface and tests without creating false precision.
    
    Subclasses must implement:
        - convergence_metric(): Returns current convergence error
        - apply(state): Applies one iteration of the pathway
    """
    
    # Phase 2: Increase for actual convergence
    MAX_ITERATIONS = 1
    CONVERGENCE_TOLERANCE = 0.01
    
    @abstractmethod
    def convergence_metric(self) -> float:
        """Return the current convergence error (0 = converged)."""
        pass
    
    @abstractmethod
    def apply(self, state: 'PathwayExecutionState') -> 'PathwayExecutionState':
        """Apply one iteration of the pathway, returning updated state."""
        pass
    
    @classmethod
    def is_allowed(cls, drl_level: int, allow_circular: bool = False) -> bool:
        """
        Check if circular pathways are allowed at current DRL level.
        
        Args:
            drl_level: Current Design Readiness Level (1-9)
            allow_circular: Override flag to enable circular pathways
            
        Returns:
            True if circular pathways are allowed
        """
        if allow_circular:
            return drl_level >= CIRCULAR_PATHWAY_MIN_DRL
        return False


# Forward reference for type hints (actual class in state.py)
PathwayExecutionState = 'PathwayExecutionState'


# =============================================================================
# Deployment-Mode Pathway Presets
# =============================================================================

def create_product_pathways() -> StreamPathwayConfig:
    """Create pathway config appropriate for PRODUCT (owner-operated) deployment.

    Product mode targets owner-operators with limited technical staff.
    Only near-term, low-complexity pathways are enabled:
        - Struvite recovery (semi-automated, proven)
        - Heat export (passive, low maintenance)
        - Off-spec thermal (integrated, no extra staff)
        - Screenings reuse — alternative cover (simple logistics)

    Disabled deliberately:
        - CHP (requires grid-tie engineering, O&M staff)
        - Char activation (steam system complexity)
        - Ammonia stripping (chemical handling, operator certification)
        - Carbon credits (MRV complexity beyond owner-serviceable)
    """
    return StreamPathwayConfig(
        struvite=StruvitePathwayParams(enabled=True),
        heat_export=HeatExportParams(enabled=True),
        offspec_thermal=OffSpecThermalParams(enabled=True),
        screenings_reuse=ScreeningsReuseParams(
            enabled=True,
            pathway=ScreeningsPathway.ALTERNATIVE_COVER,
        ),
        septic_media=SepticMediaParams(enabled=True),
    )


def create_hub_pathways() -> StreamPathwayConfig:
    """Create pathway config appropriate for REGIONAL_HUB deployment.

    Hub mode targets staffed regional facilities with throughput that
    justifies capital-intensive value-add infrastructure:
        - All near-term pathways (struvite, heat export, off-spec, screenings)
        - CHP with grid export (staff can manage grid-tie)
        - Char activation (steam system O&M within staff capability)
        - Ammonia stripping (certified operators available)
        - Carbon credits (MRV overhead amortised over throughput)
        - Road-base screenings reuse (volume justifies logistics)
    """
    return StreamPathwayConfig(
        struvite=StruvitePathwayParams(enabled=True),
        ammonia_stripping=AmmoniaStrippingParams(enabled=True),
        chp=CHPParams(enabled=True, grid_export_enabled=True),
        heat_export=HeatExportParams(enabled=True),
        char_activation=CharActivationParams(enabled=True),
        septic_media=SepticMediaParams(enabled=True),
        offspec_thermal=OffSpecThermalParams(enabled=True),
        screenings_reuse=ScreeningsReuseParams(
            enabled=True,
            pathway=ScreeningsPathway.ROAD_BASE,
        ),
        meta_products=MetaProductParams(carbon_credits_enabled=True),
    )


def create_pathways_for_mode(mode: str) -> StreamPathwayConfig:
    """Dispatch to deployment-mode-specific pathway preset.

    Args:
        mode: ``"product"`` or ``"regional_hub"`` (matches
              :class:`~septage_model.core.parameters.DeploymentMode` values).

    Returns:
        :class:`StreamPathwayConfig` with mode-appropriate defaults.

    Raises:
        ValueError: If *mode* is not a recognised deployment mode.
    """
    if mode == "product":
        return create_product_pathways()
    elif mode == "regional_hub":
        return create_hub_pathways()
    else:
        raise ValueError(
            f"Unknown deployment mode: {mode!r}. "
            f"Expected 'product' or 'regional_hub'."
        )
