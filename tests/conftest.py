"""
Shared test infrastructure — fixtures, helpers, diagnostic assertions.

Usage:
    # In any test file:
    from conftest import assert_close, assert_gate_passed

    def test_something(baseline_params, baseline_result):
        assert_close("payback", baseline_result.economics.simple_payback_years, 10.0, rel=0.05)
"""

import pytest


# =============================================================================
# Diagnostic assertion helpers
# =============================================================================

def assert_close(name: str, got: float, expected: float, *, rel: float = 1e-3, abs_tol: float = 0.0):
    """
    Assert that `got` is close to `expected` with a diagnostic failure message.

    Parameters
    ----------
    name : str
        Human-readable label for the value (shown on failure).
    got : float
        Actual value.
    expected : float
        Expected value.
    rel : float
        Relative tolerance (default 0.1%).
    abs_tol : float
        Absolute tolerance (default 0, meaning pure relative check).
    """
    if expected == 0:
        error = abs(got)
        threshold = abs_tol or rel
    else:
        error = abs((got - expected) / expected)
        threshold = rel

    if abs(got - expected) <= abs_tol:
        return  # passes absolute tolerance

    assert error <= threshold, (
        f"{name} out of tolerance:\n"
        f"  Got:      {got}\n"
        f"  Expected: {expected}\n"
        f"  Rel err:  {error:.6f} (threshold: {threshold})\n"
        f"  Δ:        {got - expected:+.6f}"
    )


def assert_gate_passed(gate):
    """
    Assert that a GateResult passed, with structured diagnostic output
    matching the CI gate test pattern.

    Parameters
    ----------
    gate : GateResult
        Gate result from septage_model.ci.gates.
    """
    assert gate.passed, (
        f"{gate.name} FAILED:\n"
        f"  Value:       {gate.value:,.4f}\n"
        f"  Threshold:   {gate.threshold:,.4f}\n"
        f"  Remediation: {gate.remediation}"
    )


# =============================================================================
# Shared fixtures
# =============================================================================

@pytest.fixture(scope="session")
def baseline_params():
    """Baseline ModelParameters — created once per test session."""
    from septage_model import create_baseline_parameters
    return create_baseline_parameters()


@pytest.fixture(scope="session")
def baseline_result():
    """Baseline Stage1Result — created once per test session."""
    from septage_model import create_baseline_parameters, run_stage1
    params = create_baseline_parameters()
    return run_stage1(params)
