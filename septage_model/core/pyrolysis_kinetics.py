"""
Pyrolysis Kinetics Module - Design-grade conversion and yield calculations.

Provides:
    - Tier-1 global kinetics solver: dX/dt = A * exp(-Ea/RT) * (1-X)^n
    - Yield derivation from conversion and feedstock proximate analysis
    - Residence time calculation from reactor holdup
    - Validation governance and warnings

Design Intent:
    - Tier-1 is always runnable (even with literature defaults)
    - Tier-2 parallel reactions are structured but gated by validation
    - Unvalidated kinetics raise warnings, not errors (for design exploration)
    - DRL-4+ claims are blocked by CI gates (see gates.py)

References:
    - ref_sludge_kinetics_daem_2012
    - ref_sludge_parallel_reactions_2008
    - ref_wood_pyrolysis_di_blasi_2008
"""

from dataclasses import dataclass
from typing import Tuple, Optional, List
import math
import warnings

from .parameters import (
    KineticsParams,
    FeedstockProperties,
    ReactorParams,
    UnvalidatedKineticsWarning,
)


# Physical constants
R_GAS = 8.314  # J/(mol·K) - Universal gas constant


@dataclass
class ConversionResult:
    """Result of kinetics solver."""
    X: float                        # Achieved conversion (0-1)
    X_min: float                    # Required minimum conversion
    feasible: bool                  # X >= X_min
    residence_time_s: float         # Residence time used
    temperature_k: float            # Reactor temperature
    rate_constant_s_inv: float      # k(T) value
    stream_id: str                  # Which feedstock stream
    
    @property
    def conversion_margin(self) -> float:
        """How much conversion exceeds minimum (negative if under)."""
        return self.X - self.X_min
    
    @property
    def conversion_pct(self) -> float:
        """Conversion as percentage."""
        return self.X * 100


@dataclass
class YieldsResult:
    """Product yields derived from conversion and feedstock properties."""
    yield_char: float               # Char yield (dry basis)
    yield_gas: float                # Gas/volatiles yield (dry basis)
    yield_tar: float                # Tar/condensate yield (dry basis)
    yield_ash: float                # Ash yield (dry basis, passthrough)
    
    # Mass balance check
    total_yield: float              # Should be 1.0
    
    # Quality indicators
    char_carbon_fraction: float     # Carbon content of char
    organic_conversion: float       # Fraction of organic matter converted
    
    def __post_init__(self):
        if abs(self.total_yield - 1.0) > 0.01:
            raise ValueError(
                f"Yields must sum to 1.0, got {self.total_yield:.3f}"
            )


def calc_rate_constant(T_k: float, kinetics: KineticsParams) -> float:
    """
    Calculate Arrhenius rate constant k(T).
    
    k(T) = A * exp(-Ea / (R * T))
    
    Args:
        T_k: Temperature in Kelvin
        kinetics: Kinetics parameters
    
    Returns:
        Rate constant in 1/s
    """
    if T_k <= 0:
        raise ValueError(f"Temperature must be positive, got {T_k} K")
    
    exponent = -kinetics.Ea_J_per_mol / (R_GAS * T_k)
    
    # Guard against overflow
    if exponent < -700:
        return 0.0
    if exponent > 700:
        return float('inf')
    
    return kinetics.A_s_inv * math.exp(exponent)


def calc_conversion_analytical(
    tau_s: float,
    T_k: float,
    kinetics: KineticsParams,
) -> float:
    """
    Calculate conversion analytically for simple reaction orders.
    
    For n=1 (first order):
        X = 1 - exp(-k*tau)
    
    For n≠1:
        X = 1 - [1 + k*tau*(n-1)]^(1/(1-n))
    
    Args:
        tau_s: Residence time in seconds
        T_k: Temperature in Kelvin
        kinetics: Kinetics parameters
    
    Returns:
        Conversion X (0 to 1)
    """
    k = calc_rate_constant(T_k, kinetics)
    n = kinetics.reaction_order
    
    if k <= 0 or tau_s <= 0:
        return 0.0
    
    # First-order kinetics (most common)
    if abs(n - 1.0) < 1e-6:
        X = 1.0 - math.exp(-k * tau_s)
    else:
        # General order
        term = 1.0 + k * tau_s * (n - 1.0)
        if term <= 0:
            X = 1.0  # Complete conversion
        else:
            X = 1.0 - term ** (1.0 / (1.0 - n))
    
    # Clamp to valid range
    return max(0.0, min(1.0, X))


def calc_conversion(
    kinetics: KineticsParams,
    reactor: ReactorParams,
    m_dot_kg_s: float,
    warn_if_unvalidated: bool = True,
) -> ConversionResult:
    """
    Calculate pyrolysis conversion for given operating conditions.
    
    Uses plug-flow reactor (PFR) assumption with global Tier-1 kinetics.
    Raises UnvalidatedKineticsWarning if kinetics are literature-based.
    
    Args:
        kinetics: Kinetics parameters for this stream
        reactor: Reactor geometry and conditions
        m_dot_kg_s: Solids mass flow rate (kg/s)
        warn_if_unvalidated: Whether to raise warning for unvalidated kinetics
    
    Returns:
        ConversionResult with achieved conversion and feasibility
    
    Raises:
        ValueError: If Tier-2 is requested but not validated
    """
    # Governance: warn on unvalidated kinetics
    if not kinetics.validated and warn_if_unvalidated:
        refs = ", ".join(kinetics.source_refs) if kinetics.source_refs else "none"
        warnings.warn(
            f"Kinetics for stream '{kinetics.stream_id}' are literature-based and unvalidated. "
            f"DRL-4+ claims are blocked. Sources: [{refs}]",
            UnvalidatedKineticsWarning,
        )
    
    # Governance: Tier-2 requires validation (hard error)
    if kinetics.tier == "TIER2_PARALLEL":
        raise ValueError(
            f"Tier-2 parallel kinetics for stream '{kinetics.stream_id}' are not yet implemented. "
            "Use TIER1_GLOBAL until lab validation is complete."
        )
    
    # Calculate residence time
    tau_s = reactor.calc_residence_time_s(m_dot_kg_s)
    
    # Use reactor wall temperature as reaction temperature
    # (simplified - assumes isothermal bed at wall temp)
    T_k = kinetics.temperature_k
    
    # Calculate conversion
    X = calc_conversion_analytical(tau_s, T_k, kinetics)
    
    # Calculate rate constant for reporting
    k = calc_rate_constant(T_k, kinetics)
    
    return ConversionResult(
        X=X,
        X_min=kinetics.X_min,
        feasible=X >= kinetics.X_min,
        residence_time_s=tau_s,
        temperature_k=T_k,
        rate_constant_s_inv=k,
        stream_id=kinetics.stream_id,
    )


def calc_yields_from_conversion(
    conversion: float,
    feedstock: FeedstockProperties,
    char_retention_factor: float = 0.15,
) -> YieldsResult:
    """
    Derive product yields from conversion and feedstock proximate analysis.
    
    Model:
        - Ash passes through unchanged
        - Fixed carbon largely becomes char (with some loss to gas)
        - Volatile matter splits between gas and tar based on conversion
        - Higher conversion → more gas, less tar
    
    Args:
        conversion: Achieved conversion X (0-1)
        feedstock: Feedstock properties with proximate analysis
        char_retention_factor: Fraction of unconverted organic remaining as char
    
    Returns:
        YieldsResult with product distribution
    """
    prox = feedstock.proximate
    
    # Ash passes through
    yield_ash = prox.ash
    
    # Organic fraction (VM + FC)
    organic = 1.0 - prox.ash
    
    # Fixed carbon behavior:
    # - Most FC becomes char
    # - Small fraction converts to gas at high temperatures
    fc_to_char = prox.fixed_carbon * 0.90  # 90% of FC goes to char
    fc_to_gas = prox.fixed_carbon * 0.10   # 10% of FC volatilizes
    
    # Volatile matter behavior:
    # - Converted VM splits between gas and tar
    # - Unconverted VM remains as char-like residue
    vm_converted = prox.volatile_matter * conversion
    vm_unconverted = prox.volatile_matter * (1.0 - conversion)
    
    # Primary cracking: VM → Gas + Tar
    # Ratio depends on severity (temperature, residence time)
    # At ~550°C: roughly 60% gas, 40% tar
    gas_fraction = 0.60 + 0.20 * conversion  # Higher conversion → more gas
    tar_fraction = 1.0 - gas_fraction
    
    vm_to_gas = vm_converted * gas_fraction
    vm_to_tar = vm_converted * tar_fraction
    
    # Unconverted VM becomes char-like residue
    vm_to_char = vm_unconverted * char_retention_factor
    vm_lost = vm_unconverted * (1.0 - char_retention_factor)  # Light volatiles escape
    
    # Sum up yields
    yield_char = fc_to_char + vm_to_char
    yield_gas = fc_to_gas + vm_to_gas + vm_lost
    yield_tar = vm_to_tar
    
    # Normalize to ensure mass balance (rounding errors)
    total = yield_char + yield_gas + yield_tar + yield_ash
    yield_char /= total
    yield_gas /= total
    yield_tar /= total
    yield_ash /= total
    
    # Char carbon content
    # Char is enriched in carbon vs feedstock
    # Approximation: char is 60-80% carbon depending on feedstock
    char_carbon = feedstock.ultimate.carbon * 1.4  # Enrichment factor
    char_carbon = min(char_carbon, 0.85)  # Cap at realistic max
    
    # Organic conversion (for reporting)
    organic_conversion = conversion
    
    return YieldsResult(
        yield_char=yield_char,
        yield_gas=yield_gas,
        yield_tar=yield_tar,
        yield_ash=yield_ash,
        total_yield=yield_char + yield_gas + yield_tar + yield_ash,
        char_carbon_fraction=char_carbon,
        organic_conversion=organic_conversion,
    )


def calc_residence_time_required(
    X_target: float,
    T_k: float,
    kinetics: KineticsParams,
) -> float:
    """
    Calculate residence time required to achieve target conversion.
    
    Inverse of conversion calculation.
    
    Args:
        X_target: Target conversion (0-1)
        T_k: Temperature in Kelvin
        kinetics: Kinetics parameters
    
    Returns:
        Required residence time in seconds
    
    Raises:
        ValueError: If X_target >= 1.0 or infeasible
    """
    if X_target >= 1.0:
        raise ValueError("Cannot achieve 100% conversion - infinite time required")
    if X_target <= 0.0:
        return 0.0
    
    k = calc_rate_constant(T_k, kinetics)
    if k <= 0:
        raise ValueError(f"Rate constant is zero at T={T_k}K - reaction won't proceed")
    
    n = kinetics.reaction_order
    
    # First-order kinetics
    if abs(n - 1.0) < 1e-6:
        tau_s = -math.log(1.0 - X_target) / k
    else:
        # General order
        term = (1.0 - X_target) ** (1.0 - n)
        tau_s = (term - 1.0) / (k * (n - 1.0))
    
    return max(0.0, tau_s)


def calc_temperature_required(
    X_target: float,
    tau_s: float,
    kinetics: KineticsParams,
    T_min_k: float = 573.15,   # 300°C
    T_max_k: float = 1073.15,  # 800°C
    tolerance: float = 1e-4,
) -> float:
    """
    Calculate temperature required to achieve target conversion at given residence time.
    
    Uses bisection method to find T such that X(tau, T) = X_target.
    
    Args:
        X_target: Target conversion (0-1)
        tau_s: Fixed residence time in seconds
        kinetics: Kinetics parameters
        T_min_k: Minimum search temperature (K)
        T_max_k: Maximum search temperature (K)
        tolerance: Convergence tolerance on conversion
    
    Returns:
        Required temperature in Kelvin
    
    Raises:
        ValueError: If target cannot be achieved in temperature range
    """
    # Check bounds
    X_at_min = calc_conversion_analytical(tau_s, T_min_k, kinetics)
    X_at_max = calc_conversion_analytical(tau_s, T_max_k, kinetics)
    
    if X_target < X_at_min:
        return T_min_k  # Target already met at minimum temp
    if X_target > X_at_max:
        raise ValueError(
            f"Target conversion {X_target:.3f} cannot be achieved even at {T_max_k}K "
            f"(max achievable: {X_at_max:.3f})"
        )
    
    # Bisection search
    T_low, T_high = T_min_k, T_max_k
    for _ in range(50):  # Max iterations
        T_mid = (T_low + T_high) / 2
        X_mid = calc_conversion_analytical(tau_s, T_mid, kinetics)
        
        if abs(X_mid - X_target) < tolerance:
            return T_mid
        
        if X_mid < X_target:
            T_low = T_mid
        else:
            T_high = T_mid
    
    return (T_low + T_high) / 2


def print_conversion_summary(result: ConversionResult) -> None:
    """Print human-readable conversion summary."""
    status = "FEASIBLE" if result.feasible else "INFEASIBLE"
    margin = result.conversion_margin * 100
    
    print("=" * 60)
    print(f"CONVERSION ANALYSIS: {result.stream_id}")
    print("=" * 60)
    print(f"Temperature:     {result.temperature_k:.1f} K ({result.temperature_k - 273.15:.1f}°C)")
    print(f"Residence time:  {result.residence_time_s:.1f} s ({result.residence_time_s / 60:.2f} min)")
    print(f"Rate constant:   {result.rate_constant_s_inv:.3e} 1/s")
    print()
    print(f"Conversion:      {result.conversion_pct:.1f}%")
    print(f"Required:        {result.X_min * 100:.1f}%")
    print(f"Margin:          {margin:+.1f}%")
    print()
    print(f"Status:          {status}")
    print("=" * 60)


def print_yields_summary(yields: YieldsResult, feedstock_name: str = "") -> None:
    """Print human-readable yields summary."""
    print("=" * 60)
    print(f"PRODUCT YIELDS: {feedstock_name}")
    print("=" * 60)
    print(f"Char:            {yields.yield_char * 100:.1f}% (C: {yields.char_carbon_fraction * 100:.0f}%)")
    print(f"Gas:             {yields.yield_gas * 100:.1f}%")
    print(f"Tar/Condensate:  {yields.yield_tar * 100:.1f}%")
    print(f"Ash:             {yields.yield_ash * 100:.1f}%")
    print("-" * 60)
    print(f"Total:           {yields.total_yield * 100:.1f}%")
    print(f"Organic conv:    {yields.organic_conversion * 100:.1f}%")
    print("=" * 60)


# =============================================================================
# Physics Assumptions Dashboard
# =============================================================================

@dataclass
class UnvalidatedAssumption:
    """A single unvalidated physics assumption."""
    stream_id: str
    parameter: str
    value: str
    source_refs: Tuple[str, ...]
    drl_impact: str
    notes: Optional[str] = None


def list_unvalidated_physics_assumptions(
    kinetics_list: list,  # List[KineticsParams]
    reactor: Optional['ReactorParams'] = None,
) -> list:  # List[UnvalidatedAssumption]
    """
    List all unvalidated physics assumptions for audit dashboard.
    
    Returns a list of UnvalidatedAssumption showing:
        - What parameter is assumed
        - What value is being used
        - What literature source it comes from
        - What DRL advancement it blocks
    
    Args:
        kinetics_list: List of KineticsParams for all streams
        reactor: Optional ReactorParams (if design_mode)
    
    Returns:
        List of UnvalidatedAssumption for all unvalidated physics
    """
    from .parameters import ReactorParams
    
    assumptions = []
    
    # Check kinetics for each stream
    for k in kinetics_list:
        if not k.validated:
            # Ea assumption
            assumptions.append(UnvalidatedAssumption(
                stream_id=k.stream_id,
                parameter="Ea_J_per_mol",
                value=f"{k.Ea_J_per_mol/1000:.0f} kJ/mol",
                source_refs=k.source_refs,
                drl_impact="Blocks DRL-4+",
                notes=k.notes,
            ))
            
            # A assumption
            assumptions.append(UnvalidatedAssumption(
                stream_id=k.stream_id,
                parameter="A_s_inv",
                value=f"{k.A_s_inv:.1e} 1/s",
                source_refs=k.source_refs,
                drl_impact="Blocks DRL-4+",
                notes=k.notes,
            ))
            
            # n assumption
            assumptions.append(UnvalidatedAssumption(
                stream_id=k.stream_id,
                parameter="reaction_order",
                value=f"{k.reaction_order}",
                source_refs=k.source_refs,
                drl_impact="Blocks DRL-4+",
                notes=k.notes,
            ))
            
            # X_min assumption
            assumptions.append(UnvalidatedAssumption(
                stream_id=k.stream_id,
                parameter="X_min",
                value=f"{k.X_min * 100:.0f}%",
                source_refs=k.source_refs,
                drl_impact="Affects conversion gate",
                notes="Minimum required conversion for design feasibility",
            ))
    
    # Check reactor if provided
    if reactor is not None and not reactor.validated:
        assumptions.append(UnvalidatedAssumption(
            stream_id="reactor",
            parameter="U_w_m2k",
            value=f"{reactor.U_w_m2k} W/m²K",
            source_refs=reactor.source_refs,
            drl_impact="Blocks DRL-5+",
            notes="Overall heat transfer coefficient - requires vendor data",
        ))
        
        assumptions.append(UnvalidatedAssumption(
            stream_id="reactor",
            parameter="heat_transfer_area",
            value=f"{reactor.heat_transfer_area_m2:.2f} m²",
            source_refs=reactor.source_refs,
            drl_impact="Blocks DRL-5+",
            notes="Effective heat transfer area - requires vendor data",
        ))
    
    return assumptions


def print_unvalidated_assumptions(assumptions: list) -> None:
    """Print dashboard of unvalidated physics assumptions."""
    if not assumptions:
        print("=" * 70)
        print("PHYSICS ASSUMPTIONS DASHBOARD")
        print("=" * 70)
        print("All physics parameters are validated. Ready for DRL-4+.")
        print("=" * 70)
        return
    
    print("=" * 70)
    print("UNVALIDATED PHYSICS ASSUMPTIONS")
    print("=" * 70)
    print()
    print(f"{'Stream':<15} {'Parameter':<20} {'Value':<20} {'DRL Impact':<15}")
    print("-" * 70)
    
    for a in assumptions:
        print(f"{a.stream_id:<15} {a.parameter:<20} {a.value:<20} {a.drl_impact:<15}")
    
    print()
    print("LITERATURE SOURCES:")
    seen_refs = set()
    for a in assumptions:
        for ref in a.source_refs:
            if ref not in seen_refs:
                print(f"  - {ref}")
                seen_refs.add(ref)
    
    print()
    print("ACTION REQUIRED: Provide lab/vendor data to validate these assumptions")
    print("=" * 70)
