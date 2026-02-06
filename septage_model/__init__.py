"""
Septage-to-Biochar Continuous Hub Simulation Model
===================================================

A two-stage engineering simulation for designing and evaluating 
continuous septage-to-biochar regional processing hubs.

Model Version: 1.0.0
Baseline: Tiny Township / North Simcoe (5,000 m³/yr)

Architecture:
    - Physics ≠ Control ≠ Economics (strict separation)
    - State evolves, Parameters do not
    - Deterministic first (Stage 1), Stochastic later (Stage 2)

Modules:
    - config/: Baseline parameters and scenario definitions
    - core/: Parameters, state, mass/energy balance equations
    - units/: Process unit operations (stateless)
    - control/: Control policies (P-control, co-feed, discharge)
    - economics/: CAPEX, OPEX, revenue, proforma
    - simulation/: Deterministic and discrete-event solvers
    - analysis/: KPIs, constraints, sizing, carbon accounting
    - outputs/: Dashboard, reports, comparisons
    - ui/: Decision mode and engineering mode interfaces
    - tests/: Invariant, behavioral, regression tests

Author: Engineering Design Team
Date: February 2026
"""

__version__ = "1.0.0"
__model_name__ = "SeptageToChar"

from dataclasses import dataclass
from typing import Dict, Any
import hashlib
import json


def compute_parameter_hash(params: Dict[str, Any]) -> str:
    """
    Generate a deterministic hash of parameter set for versioning.
    
    This enables:
    - Reproducibility verification
    - Scenario comparison
    - Audit trails for regulatory review
    """
    # Sort keys for deterministic ordering
    serialized = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()[:12]


def get_model_fingerprint(version: str, param_hash: str) -> str:
    """
    Create a unique fingerprint for this model run.
    
    Format: {model_name}_v{version}_{param_hash}
    Example: SeptageToChar_v1.0.0_a3b2c1d4e5f6
    """
    return f"{__model_name__}_v{version}_{param_hash}"


# Convenience imports
from .core import (
    ModelParameters,
    create_baseline_parameters,
    create_initial_state,
    SimulationState,
)

from .simulation import (
    run_stage1,
    run_sanity_checks,
    print_stage1_summary,
    Stage1Result,
)

from .analysis import (
    calc_system_sizing,
    size_equipment,
    SystemSizing,
)

__all__ = [
    "__version__",
    "__model_name__",
    "compute_parameter_hash",
    "get_model_fingerprint",
    # Core
    "ModelParameters",
    "create_baseline_parameters",
    "create_initial_state",
    "SimulationState",
    # Simulation
    "run_stage1",
    "run_sanity_checks",
    "print_stage1_summary",
    "Stage1Result",
    # Analysis
    "calc_system_sizing",
    "size_equipment",
    "SystemSizing",
]