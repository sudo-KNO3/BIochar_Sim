"""
CI Design Gates - Automated product viability enforcement.

This module provides hard pass/fail checks that encode the frozen
engineering constraints. Any change that breaks viability fails CI.

Includes:
    - Design Gates (maintenance, payback, callouts, physics)
    - Design Readiness Level (DRL) evaluation
"""

from .gates import (
    GateResult,
    GateReport,
    maintenance_budget_gate,
    payback_gate,
    callout_frequency_gate,
    physics_sanity_gate,
    run_design_gates,
    check_gates_or_fail,
    operating_envelope_gate,
    MAX_MAINTENANCE_BUDGET,
    MAX_CALLOUTS_PER_WEEK,
    MAX_PAYBACK_YEARS,
    OWNER_SERVICEABLE_REQUIRED,
)

from .design_readiness import (
    DRLLevel,
    DRLCriterion,
    DRLAssessment,
    create_standard_criteria,
    evaluate_drl,
    evaluate_drl_from_results,
    generate_drl_report,
    generate_drl_badge_url,
    generate_drl_markdown,
)

__all__ = [
    # Gates
    'GateResult',
    'GateReport',
    'maintenance_budget_gate',
    'payback_gate',
    'callout_frequency_gate',
    'physics_sanity_gate',
    'run_design_gates',
    'check_gates_or_fail',
    'MAX_MAINTENANCE_BUDGET',
    'MAX_CALLOUTS_PER_WEEK',
    'MAX_PAYBACK_YEARS',
    'OWNER_SERVICEABLE_REQUIRED',
    # DRL
    'DRLLevel',
    'DRLCriterion',
    'DRLAssessment',
    'create_standard_criteria',
    'evaluate_drl',
    'evaluate_drl_from_results',
    'generate_drl_report',
    'generate_drl_badge_url',
    'generate_drl_markdown',
]
