"""
Core Utilities Module
=====================

Centralized utility functions for the simulation, including:
- State saturation/clipping (enforces physical bounds)
- Unit conversions
- Validation helpers
- Numerical safeguards

CRITICAL DESIGN RULE:
All clip() and saturation logic MUST be centralized here.
This prevents missed bounds checks scattered across control loops.

Engineering Notes:
- Every state variable must be bounded (≥0, ≤capacity)
- Flow rates must be non-negative and ≤ equipment capacity
- Clipping must preserve mass balance (logged when triggered)
"""

from dataclasses import dataclass
from typing import Optional, Tuple, Union, List
from enum import Enum
import math


class ClipReason(Enum):
    """Reasons why clipping occurred - for traceability."""
    NONE = "no_clip"
    FLOOR_ZERO = "floor_at_zero"
    CEILING_MAX = "ceiling_at_max"
    RATE_LIMIT = "rate_limit_applied"
    CAPACITY_LIMIT = "capacity_limit"


@dataclass
class ClipResult:
    """Result of a clipping operation with full traceability."""
    value: float
    original: float
    was_clipped: bool
    reason: ClipReason
    delta: float  # Amount clipped (positive if reduced, negative if raised)
    
    def __post_init__(self):
        self.delta = self.original - self.value


def clip_positive(value: float, name: str = "value") -> ClipResult:
    """
    Clip value to non-negative.
    
    Physical reality: Mass, volume, and flow rates cannot be negative.
    """
    if value < 0:
        return ClipResult(
            value=0.0,
            original=value,
            was_clipped=True,
            reason=ClipReason.FLOOR_ZERO,
            delta=value
        )
    return ClipResult(
        value=value,
        original=value,
        was_clipped=False,
        reason=ClipReason.NONE,
        delta=0.0
    )


def clip_range(
    value: float, 
    min_val: float, 
    max_val: float,
    name: str = "value"
) -> ClipResult:
    """Clip value to [min_val, max_val] range."""
    if value < min_val:
        return ClipResult(
            value=min_val,
            original=value,
            was_clipped=True,
            reason=ClipReason.FLOOR_ZERO if min_val == 0 else ClipReason.CAPACITY_LIMIT,
            delta=value - min_val
        )
    elif value > max_val:
        return ClipResult(
            value=max_val,
            original=value,
            was_clipped=True,
            reason=ClipReason.CEILING_MAX,
            delta=value - max_val
        )
    return ClipResult(
        value=value,
        original=value,
        was_clipped=False,
        reason=ClipReason.NONE,
        delta=0.0
    )


def clip_rate_of_change(
    new_value: float,
    old_value: float,
    max_rate: float,
    dt: float,
    name: str = "value"
) -> ClipResult:
    """Apply slew-rate limiting to prevent instantaneous changes."""
    max_change = max_rate * dt
    actual_change = new_value - old_value
    
    if abs(actual_change) > max_change:
        if actual_change > 0:
            limited_value = old_value + max_change
        else:
            limited_value = old_value - max_change
        return ClipResult(
            value=limited_value,
            original=new_value,
            was_clipped=True,
            reason=ClipReason.RATE_LIMIT,
            delta=new_value - limited_value
        )
    
    return ClipResult(
        value=new_value,
        original=new_value,
        was_clipped=False,
        reason=ClipReason.NONE,
        delta=0.0
    )


def apply_deadband(error: float, deadband: float, name: str = "error") -> float:
    """Apply deadband to error signal for control stability."""
    if abs(error) <= deadband:
        return 0.0
    elif error > 0:
        return error - deadband
    else:
        return error + deadband


# Unit Conversions
def m3_to_kg(volume_m3: float, density_kg_m3: float = 1000.0) -> float:
    return volume_m3 * density_kg_m3

def kg_to_m3(mass_kg: float, density_kg_m3: float = 1000.0) -> float:
    return mass_kg / density_kg_m3

def m3_to_liters(m3: float) -> float:
    return m3 * 1000.0

def liters_to_m3(liters: float) -> float:
    return liters / 1000.0

def tonnes_to_kg(tonnes: float) -> float:
    return tonnes * 1000.0

def kg_to_tonnes(kg: float) -> float:
    return kg / 1000.0

def mj_to_kwh(mj: float) -> float:
    return mj / 3.6

def kwh_to_mj(kwh: float) -> float:
    return kwh * 3.6

def annual_to_daily(annual: float, operating_days: float = 365.0) -> float:
    return annual / operating_days

def annual_to_hourly(annual: float, operating_hours: float = 8760.0) -> float:
    return annual / operating_hours


# Validation Helpers
def validate_fraction(value: float, name: str = "fraction") -> None:
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"{name} must be between 0 and 1, got {value}")

def validate_positive(value: float, name: str = "value") -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")

def validate_non_negative(value: float, name: str = "value") -> None:
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")

def validate_yields_sum(yields: List[float], tolerance: float = 0.001) -> None:
    total = sum(yields)
    if abs(total - 1.0) > tolerance:
        raise ValueError(f"Yield fractions must sum to 1.0, got {total:.4f}")


# Mass Balance Closure Check
@dataclass
class MassBalanceCheck:
    """Result of mass balance closure verification."""
    mass_in: float
    mass_out: float
    accumulation: float
    closure_error: float
    is_closed: bool
    tolerance: float
    
    def __str__(self) -> str:
        status = "CLOSED" if self.is_closed else "FAILED"
        return (
            f"Mass Balance [{status}]: "
            f"In={self.mass_in:.2f}, Out={self.mass_out:.2f}, "
            f"Accum={self.accumulation:.2f}, "
            f"Error={self.closure_error:.4f} (tol={self.tolerance})"
        )


def check_mass_balance(
    mass_in: float,
    mass_out: float,
    accumulation: float,
    tolerance: float = 1e-6
) -> MassBalanceCheck:
    """Verify mass balance closure: In - Out - Accumulation = 0 ± tolerance."""
    closure_error = abs(mass_in - mass_out - accumulation)
    is_closed = closure_error <= tolerance
    
    return MassBalanceCheck(
        mass_in=mass_in,
        mass_out=mass_out,
        accumulation=accumulation,
        closure_error=closure_error,
        is_closed=is_closed,
        tolerance=tolerance
    )


def assert_mass_balance(
    mass_in: float,
    mass_out: float,
    context: str = "",
    tolerance: float = 1e-3,
    accumulation: float = 0.0
) -> None:
    """Assert mass balance closure. Raises if violated."""
    check = check_mass_balance(mass_in, mass_out, accumulation, tolerance)
    if not check.is_closed:
        raise AssertionError(f"Mass balance violation {context}: {check}")
