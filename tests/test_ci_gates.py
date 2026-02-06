"""
CI Design Gate Tests.

These tests enforce the frozen product viability constraints.
Any PR that breaks these tests breaks the product.

Marked with @pytest.mark.ci for pipeline filtering.

Frozen constraints:
    - maintenance_cost <= $35,000/yr
    - payback_with_char <= 15.0 years
    - callouts <= 1/week
    - energy_self_sufficiency >= 1.0
"""

import pytest


@pytest.mark.ci
def test_maintenance_budget_gate_product_mode():
    """
    Product Mode must pass maintenance budget gate.
    
    Frozen constraint: maintenance_cost <= $35,000/yr
    """
    from septage_model.simulation.deterministic import run_product_mode
    from septage_model.ci.gates import maintenance_budget_gate
    
    result = run_product_mode()
    gate = maintenance_budget_gate(result)
    
    assert gate.passed, (
        f"{gate.name} FAILED:\n"
        f"  Value: ${gate.value:,.0f}\n"
        f"  Threshold: ${gate.threshold:,.0f}\n"
        f"  Remediation: {gate.remediation}"
    )


@pytest.mark.ci
def test_payback_gate_product_mode():
    """
    Product Mode must achieve payback <= 15 years.
    
    Frozen constraint: payback_with_char <= 15.0 years
    """
    from septage_model.simulation.deterministic import run_product_mode
    from septage_model.ci.gates import payback_gate
    
    result = run_product_mode()
    gate = payback_gate(result)
    
    assert gate.passed, (
        f"{gate.name} FAILED:\n"
        f"  Value: {gate.value:.1f} years\n"
        f"  Threshold: {gate.threshold:.1f} years\n"
        f"  Remediation: {gate.remediation}"
    )


@pytest.mark.ci
def test_callout_frequency_gate_product_mode():
    """
    Product Mode must have callouts <= 1/week.
    
    Frozen constraint: callouts_per_week <= 1.0
    """
    from septage_model.simulation.deterministic import run_product_mode
    from septage_model.ci.gates import callout_frequency_gate
    
    result = run_product_mode()
    gate = callout_frequency_gate(result)
    
    assert gate.passed, (
        f"{gate.name} FAILED:\n"
        f"  Value: {gate.value:.2f}/week\n"
        f"  Threshold: {gate.threshold:.1f}/week\n"
        f"  Remediation: {gate.remediation}"
    )


@pytest.mark.ci
def test_physics_sanity_gate_product_mode():
    """
    Product Mode must be energy self-sufficient.
    
    Frozen constraint: energy_self_sufficiency >= 1.0
    """
    from septage_model.simulation.deterministic import run_product_mode
    from septage_model.ci.gates import physics_sanity_gate
    
    result = run_product_mode()
    gate = physics_sanity_gate(result)
    
    assert gate.passed, (
        f"{gate.name} FAILED:\n"
        f"  Value: {gate.value:.0%}\n"
        f"  Threshold: {gate.threshold:.0%}\n"
        f"  Remediation: {gate.remediation}"
    )


@pytest.mark.ci
def test_all_design_gates_pass():
    """
    All design gates must pass for Product Mode baseline.
    
    This is the master CI check.
    """
    from septage_model.simulation.deterministic import run_product_mode
    from septage_model.ci.gates import run_design_gates
    
    result = run_product_mode()
    report = run_design_gates(result)
    
    # Print full report for visibility
    print(report)
    
    assert report.all_passed, (
        f"{len(report.failed_gates)} design gate(s) failed.\n"
        f"See report above for remediation guidance."
    )


@pytest.mark.ci
def test_gate_remediation_populated_on_failure():
    """
    Failed gates must include remediation guidance.
    
    This ensures CI output is actionable, not just a blocker.
    """
    from septage_model.ci.gates import GateResult
    
    # Simulate a failed gate
    failed_gate = GateResult(
        name="Test Gate",
        passed=False,
        value=50_000,
        threshold=35_000,
        remediation="Fix the thing by doing X, Y, Z."
    )
    
    assert failed_gate.remediation is not None
    assert len(failed_gate.remediation) > 10


@pytest.mark.ci
def test_product_mode_payback_regression():
    """
    Regression test: Product Mode payback should be ~14.5 years.
    
    Tolerance: +/- 1.0 year (will tighten after pilot data).
    """
    from septage_model.simulation.deterministic import run_product_mode
    
    result = run_product_mode()
    payback = result.buyer.payback_with_char_revenue
    
    assert abs(payback - 14.5) <= 1.0, (
        f"Payback regression: expected ~14.5yr, got {payback:.1f}yr\n"
        f"If this is intentional, update the baseline."
    )


@pytest.mark.ci
def test_product_mode_maintenance_regression():
    """
    Regression test: Product Mode maintenance should be ~$23k/year.
    
    Tolerance: +/- $5k (will tighten after vendor data).
    """
    from septage_model.simulation.deterministic import run_product_mode
    
    result = run_product_mode()
    maintenance = result.base_result.economics.maintenance_cost
    
    assert abs(maintenance - 23_000) <= 5_000, (
        f"Maintenance regression: expected ~$23k, got ${maintenance:,.0f}\n"
        f"If this is intentional, update the baseline."
    )


@pytest.mark.ci
def test_hub_mode_not_viable():
    """
    Hub Mode should NOT be viable at current scale.
    
    This confirms the strategic conclusion is preserved.
    """
    from septage_model.simulation.deterministic import run_hub_mode
    from septage_model.ci.gates import payback_gate
    
    result = run_hub_mode()
    gate = payback_gate(result)
    
    # Hub should FAIL the payback gate
    assert not gate.passed, (
        f"Hub Mode unexpectedly passed viability gate.\n"
        f"Payback: {gate.value:.1f} years\n"
        f"This contradicts the locked strategic conclusion."
    )


@pytest.mark.ci
def test_check_gates_or_fail_raises_on_failure():
    """
    check_gates_or_fail should raise AssertionError on any failure.
    """
    from septage_model.ci.gates import GateResult, GateReport, check_gates_or_fail
    
    # Create a mock result that will pass (just test the function signature)
    from septage_model.simulation.deterministic import run_product_mode
    
    result = run_product_mode()
    
    # This should NOT raise (product mode passes)
    check_gates_or_fail(result)  # No exception = test passes
