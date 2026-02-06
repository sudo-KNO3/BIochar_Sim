"""
Simulation Module - Stage 1 (Deterministic) and Stage 2 (Discrete-Event) solvers.

Stage 1: Deterministic steady-state solver
    - Uses average flows and locked parameters
    - Validates feasibility before adding complexity
    - Fast sanity checks and constraint analysis

Stage 2: Discrete-event simulation (future)
    - SimPy-based stochastic arrivals
    - Full controller dynamics
    - Monte Carlo scenarios
"""

from .deterministic import (
    Stage1Result,
    Constraint,
    ViabilityStatus,
    run_stage1,
    run_sanity_checks,
    print_stage1_summary,
)

__all__ = [
    "Stage1Result",
    "Constraint",
    "ViabilityStatus",
    "run_stage1",
    "run_sanity_checks",
    "print_stage1_summary",
]
