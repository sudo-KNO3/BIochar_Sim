"""
Pathway Analysis CLI - Compare value-add pathways for waste stream optimization.

This module provides CLI tools and analysis functions for evaluating value-add
pathways for secondary feedstocks (centrate, char, syngas, screenings).

Commands:
    compare-pathways: Compare multiple scenarios with NPV delta table
    sweep-struvite: 1D sensitivity sweep on struvite recovery economics
    sweep-chp: 1D sensitivity sweep on CHP viability
    circular-scenario: Full circular economy scenario analysis

Usage:
    python -m septage_model.artifacts.pathway_analysis compare-pathways
    python -m septage_model.artifacts.pathway_analysis sweep-struvite --p-price 0.5 1.5 0.1
    python -m septage_model.artifacts.pathway_analysis circular-scenario --years 20

Design Philosophy:
    "You are no longer 'disposing waste' — you are managing secondary feedstocks."
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, NamedTuple
from enum import Enum
from pathlib import Path
import csv
import argparse
import sys

from ..core.stream_pathways import (
    PathwayMaturity,
    ScenarioRisk,
    CentratePathway,
    CharPathway,
    SyngasPathway,
    StreamPathwayConfig,
    BASELINE_PATHWAYS,
    CONSERVATIVE_PATHWAYS,
    MODERATE_PATHWAYS,
    FULL_CIRCULAR_PATHWAYS,
)
from ..core.balances import (
    calc_struvite_recovery,
    calc_ammonia_stripping,
    calc_syngas_chp,
    calc_heat_export,
    calc_char_activation,
    calc_screenings_reuse,
    calc_carbon_credits,
)
from ..ci.gates import (
    run_pathway_viability_gates,
    GateReport,
)
from ..analysis.pathway_scenarios import (
    ValueAddScenario,
    ScenarioResult,
    ScenarioComparison,
    OperatingInputs,
    evaluate_scenario,
    compare_scenarios,
    sweep_pathway_1d,
    SCENARIO_BASELINE,
    SCENARIO_CONSERVATIVE,
    SCENARIO_MODERATE,
    SCENARIO_FULL_CIRCULAR,
)


# =============================================================================
# CLI Output Formatting
# =============================================================================

class OutputFormat(Enum):
    """Output format for CLI results."""
    TABLE = "table"
    CSV = "csv"
    JSON = "json"


def format_currency(value: float) -> str:
    """Format value as currency."""
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    elif abs(value) >= 1_000:
        return f"${value / 1_000:.1f}k"
    else:
        return f"${value:.0f}"


def format_delta(value: float) -> str:
    """Format value as delta (with +/- sign)."""
    sign = "+" if value >= 0 else ""
    return f"{sign}{format_currency(value)}"


def print_table_row(columns: List[str], widths: List[int]) -> str:
    """Format a table row with fixed column widths."""
    return " | ".join(
        col.ljust(w) if i == 0 else col.rjust(w)
        for i, (col, w) in enumerate(zip(columns, widths))
    )


def print_separator(widths: List[int]) -> str:
    """Print table separator line."""
    return "-+-".join("-" * w for w in widths)


# =============================================================================
# Pathway Comparison Analysis
# =============================================================================

@dataclass
class PathwayComparisonResult:
    """Result of comparing multiple pathway scenarios."""
    baseline_npv: float
    scenarios: Dict[str, ScenarioResult]
    gate_reports: Dict[str, GateReport]
    recommended_scenario: str
    recommendation_rationale: str


def run_pathway_comparison(
    inputs: OperatingInputs,
    scenarios: Optional[Dict[str, ValueAddScenario]] = None,
    discount_rate: float = 0.08,
    project_years: int = 20,
) -> PathwayComparisonResult:
    """
    Compare multiple pathway scenarios against baseline.
    
    Args:
        inputs: Operating inputs (volumes, concentrations, etc.)
        scenarios: Dict of scenario name -> ValueAddScenario (default: built-in set)
        discount_rate: Discount rate for NPV calculation
        project_years: Project lifetime in years
        
    Returns:
        PathwayComparisonResult with all scenario evaluations
    """
    if scenarios is None:
        scenarios = {
            "Baseline (No Value-Add)": SCENARIO_BASELINE,
            "Conservative (Near-Term Only)": SCENARIO_CONSERVATIVE,
            "Moderate (+ Mid-Term)": SCENARIO_MODERATE,
            "Full Circular": SCENARIO_FULL_CIRCULAR,
        }
    
    # Evaluate all scenarios
    results = {}
    for name, scenario in scenarios.items():
        results[name] = evaluate_scenario(
            scenario, inputs, discount_rate, project_years
        )
    
    # Run viability gates
    gate_reports = {}
    for name, scenario in scenarios.items():
        gate_reports[name] = run_pathway_viability_gates(
            centrate_m3_annual=inputs.centrate_m3_annual,
            p_conc_mg_l=inputs.p_conc_mg_l,
            syngas_excess_mj_annual=inputs.syngas_excess_mj_annual,
            char_kg_annual=inputs.char_kg_annual,
            steam_available_kg_annual=inputs.steam_kg_annual,
            excess_heat_mj_annual=inputs.excess_heat_mj_annual,
            has_discharge_permit=True,  # Conservative default
            grid_interconnect_available=scenario.enable_chp,
            heat_customer_available=scenario.enable_heat_export,
        )
    
    # Find best scenario (highest NPV with all gates passed)
    baseline_npv = results.get("Baseline (No Value-Add)", results[list(results.keys())[0]]).npv
    
    viable_scenarios = [
        (name, result.npv)
        for name, result in results.items()
        if gate_reports[name].all_passed
    ]
    
    if viable_scenarios:
        recommended, best_npv = max(viable_scenarios, key=lambda x: x[1])
        delta = best_npv - baseline_npv
        recommendation_rationale = (
            f"All viability gates pass. NPV delta: {format_delta(delta)} vs baseline."
        )
    else:
        # Fall back to best NPV if no scenarios pass all gates
        recommended = max(results.keys(), key=lambda k: results[k].npv)
        recommendation_rationale = (
            "No scenario passes all viability gates. "
            "Review gate failures and address infrastructure gaps."
        )
    
    return PathwayComparisonResult(
        baseline_npv=baseline_npv,
        scenarios=results,
        gate_reports=gate_reports,
        recommended_scenario=recommended,
        recommendation_rationale=recommendation_rationale,
    )


def print_comparison_table(result: PathwayComparisonResult) -> None:
    """Print formatted comparison table to stdout."""
    headers = ["Scenario", "NPV", "Δ vs Base", "Payback", "Gates"]
    widths = [30, 12, 12, 10, 8]
    
    print("\n" + "=" * 80)
    print("PATHWAY SCENARIO COMPARISON")
    print("=" * 80)
    
    print(print_table_row(headers, widths))
    print(print_separator(widths))
    
    for name, scenario_result in result.scenarios.items():
        gate_report = result.gate_reports[name]
        delta = scenario_result.npv - result.baseline_npv
        
        # Format payback
        if scenario_result.simple_payback_years is None:
            payback_str = "N/A"
        elif scenario_result.simple_payback_years > 99:
            payback_str = ">99 yr"
        else:
            payback_str = f"{scenario_result.simple_payback_years:.1f} yr"
        
        # Gate status
        passed_count = sum(1 for g in gate_report.gates if g.passed)
        total_count = len(gate_report.gates)
        gate_str = f"{passed_count}/{total_count}"
        if gate_report.all_passed:
            gate_str += " ✓"
        
        # Highlight recommended
        name_display = name
        if name == result.recommended_scenario:
            name_display = f"→ {name}"
        
        row = [
            name_display[:widths[0]],
            format_currency(scenario_result.npv),
            format_delta(delta),
            payback_str,
            gate_str,
        ]
        print(print_table_row(row, widths))
    
    print(print_separator(widths))
    print(f"\nRecommendation: {result.recommended_scenario}")
    print(f"Rationale: {result.recommendation_rationale}")
    
    # Print gate failures
    for name, gate_report in result.gate_reports.items():
        if not gate_report.all_passed:
            print(f"\n{name} - Gate Failures:")
            for gate in gate_report.gates:
                if not gate.passed:
                    print(f"  • {gate.name}: {gate.remediation}")


def export_comparison_csv(
    result: PathwayComparisonResult,
    output_path: Path,
) -> None:
    """Export comparison results to CSV."""
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        
        # Header
        writer.writerow([
            "Scenario",
            "NPV ($)",
            "Delta vs Baseline ($)",
            "Revenue Delta ($/yr)",
            "Simple Payback (yr)",
            "Gates Passed",
            "Total Gates",
            "All Gates Passed",
        ])
        
        # Data rows
        for name, scenario_result in result.scenarios.items():
            gate_report = result.gate_reports[name]
            passed_count = sum(1 for g in gate_report.gates if g.passed)
            
            writer.writerow([
                name,
                f"{scenario_result.npv:.2f}",
                f"{scenario_result.npv - result.baseline_npv:.2f}",
                f"{scenario_result.revenue_delta:.2f}",
                f"{scenario_result.simple_payback_years:.2f}" if scenario_result.simple_payback_years else "N/A",
                passed_count,
                len(gate_report.gates),
                gate_report.all_passed,
            ])
    
    print(f"Exported to: {output_path}")


# =============================================================================
# Sensitivity Sweep Functions
# =============================================================================

@dataclass
class SweepResult:
    """Result of 1D sensitivity sweep."""
    parameter_name: str
    parameter_values: List[float]
    npv_values: List[float]
    breakeven_value: Optional[float]
    optimal_value: float
    optimal_npv: float


def sweep_struvite_price(
    inputs: OperatingInputs,
    base_scenario: ValueAddScenario,
    price_range: Tuple[float, float, float],  # (min, max, step)
    discount_rate: float = 0.08,
    project_years: int = 20,
) -> SweepResult:
    """
    Sweep struvite price to find breakeven and optimal points.
    
    Args:
        inputs: Operating inputs
        base_scenario: Base scenario with struvite enabled
        price_range: (min_price, max_price, step) in $/kg
        discount_rate: Discount rate for NPV
        project_years: Project lifetime
        
    Returns:
        SweepResult with price sensitivity data
    """
    min_p, max_p, step = price_range
    prices = []
    npvs = []
    
    # Generate price range
    price = min_p
    while price <= max_p + 0.001:  # Small epsilon for float precision
        prices.append(price)
        
        # Modify scenario with this price
        modified_scenario = ValueAddScenario(
            name=base_scenario.name,
            enable_struvite=base_scenario.enable_struvite,
            enable_ammonia_stripping=base_scenario.enable_ammonia_stripping,
            enable_chp=base_scenario.enable_chp,
            enable_heat_export=base_scenario.enable_heat_export,
            enable_char_activation=base_scenario.enable_char_activation,
            enable_screenings_reuse=base_scenario.enable_screenings_reuse,
            enable_carbon_credits=base_scenario.enable_carbon_credits,
            struvite_price_per_kg=price,
            ammonia_sulfate_price_per_kg=base_scenario.ammonia_sulfate_price_per_kg,
            electricity_price_per_kwh=base_scenario.electricity_price_per_kwh,
            heat_price_per_mj=base_scenario.heat_price_per_mj,
            activated_char_price_per_kg=base_scenario.activated_char_price_per_kg,
            carbon_credit_per_tonne_co2=base_scenario.carbon_credit_per_tonne_co2,
        )
        
        result = evaluate_scenario(
            modified_scenario, inputs, discount_rate, project_years
        )
        npvs.append(result.npv)
        
        price += step
    
    # Find breakeven (where NPV crosses zero)
    breakeven = None
    for i in range(1, len(npvs)):
        if (npvs[i-1] < 0 and npvs[i] >= 0) or (npvs[i-1] <= 0 and npvs[i] > 0):
            # Linear interpolation
            breakeven = prices[i-1] + (prices[i] - prices[i-1]) * (
                -npvs[i-1] / (npvs[i] - npvs[i-1])
            )
            break
    
    # Find optimal
    max_idx = npvs.index(max(npvs))
    
    return SweepResult(
        parameter_name="Struvite Price ($/kg)",
        parameter_values=prices,
        npv_values=npvs,
        breakeven_value=breakeven,
        optimal_value=prices[max_idx],
        optimal_npv=npvs[max_idx],
    )


def sweep_chp_capacity(
    inputs: OperatingInputs,
    base_scenario: ValueAddScenario,
    capacity_range: Tuple[float, float, float],  # (min_kw, max_kw, step)
    discount_rate: float = 0.08,
    project_years: int = 20,
) -> SweepResult:
    """
    Sweep CHP capacity to find optimal sizing.
    
    Args:
        inputs: Operating inputs
        base_scenario: Base scenario with CHP enabled
        capacity_range: (min_kw, max_kw, step) in kW
        discount_rate: Discount rate for NPV
        project_years: Project lifetime
        
    Returns:
        SweepResult with capacity sensitivity data
    """
    min_c, max_c, step = capacity_range
    capacities = []
    npvs = []
    
    capacity = min_c
    while capacity <= max_c + 0.001:
        capacities.append(capacity)
        
        # Modify inputs with this capacity factor
        scale_factor = capacity / 50.0  # Normalize to 50 kW base
        modified_inputs = OperatingInputs(
            centrate_m3_annual=inputs.centrate_m3_annual,
            p_conc_mg_l=inputs.p_conc_mg_l,
            n_conc_mg_l=inputs.n_conc_mg_l,
            syngas_excess_mj_annual=inputs.syngas_excess_mj_annual * scale_factor,
            char_kg_annual=inputs.char_kg_annual,
            steam_kg_annual=inputs.steam_kg_annual,
            screenings_kg_annual=inputs.screenings_kg_annual,
            grit_kg_annual=inputs.grit_kg_annual,
            ash_kg_annual=inputs.ash_kg_annual,
            excess_heat_mj_annual=inputs.excess_heat_mj_annual * scale_factor,
        )
        
        result = evaluate_scenario(
            base_scenario, modified_inputs, discount_rate, project_years
        )
        npvs.append(result.npv)
        
        capacity += step
    
    # Find breakeven and optimal
    breakeven = None
    for i in range(1, len(npvs)):
        if (npvs[i-1] < 0 and npvs[i] >= 0):
            breakeven = capacities[i-1] + (capacities[i] - capacities[i-1]) * (
                -npvs[i-1] / (npvs[i] - npvs[i-1])
            )
            break
    
    max_idx = npvs.index(max(npvs))
    
    return SweepResult(
        parameter_name="CHP Capacity (kW)",
        parameter_values=capacities,
        npv_values=npvs,
        breakeven_value=breakeven,
        optimal_value=capacities[max_idx],
        optimal_npv=npvs[max_idx],
    )


def print_sweep_result(result: SweepResult) -> None:
    """Print formatted sweep result."""
    print("\n" + "=" * 60)
    print(f"SENSITIVITY SWEEP: {result.parameter_name}")
    print("=" * 60)
    
    headers = [result.parameter_name, "NPV"]
    widths = [25, 15]
    
    print(print_table_row(headers, widths))
    print(print_separator(widths))
    
    for val, npv in zip(result.parameter_values, result.npv_values):
        marker = ""
        if result.breakeven_value and abs(val - result.breakeven_value) < 0.01:
            marker = " ← breakeven"
        if val == result.optimal_value:
            marker = " ← optimal"
        
        row = [f"{val:.2f}", f"{format_currency(npv)}{marker}"]
        print(print_table_row(row, widths))
    
    print(print_separator(widths))
    
    if result.breakeven_value:
        print(f"Breakeven: {result.breakeven_value:.2f}")
    else:
        print("Breakeven: Not found in range")
    print(f"Optimal: {result.optimal_value:.2f} → NPV: {format_currency(result.optimal_npv)}")


def export_sweep_csv(result: SweepResult, output_path: Path) -> None:
    """Export sweep results to CSV."""
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([result.parameter_name, "NPV ($)"])
        for val, npv in zip(result.parameter_values, result.npv_values):
            writer.writerow([f"{val:.4f}", f"{npv:.2f}"])
    print(f"Exported to: {output_path}")


# =============================================================================
# Circular Economy Scenario Analysis
# =============================================================================

@dataclass
class CircularEconomyReport:
    """Full circular economy scenario analysis report."""
    scenario_name: str
    total_revenue_annual: float
    revenue_by_stream: Dict[str, float]
    mass_balance_closure: float  # Should be ~1.0
    energy_balance_closure: float  # Should be ~1.0
    carbon_sequestered_kg_annual: float
    co2e_avoided_kg_annual: float
    circular_economy_score: float  # 0-100 composite score
    pathway_utilization: Dict[str, float]  # % utilization per pathway
    gate_report: GateReport
    recommendations: List[str]


def analyze_circular_scenario(
    inputs: OperatingInputs,
    scenario: ValueAddScenario = SCENARIO_FULL_CIRCULAR,
    discount_rate: float = 0.08,
    project_years: int = 20,
) -> CircularEconomyReport:
    """
    Comprehensive circular economy scenario analysis.
    
    This function evaluates all value-add pathways and provides a
    complete picture of circular economy performance.
    
    Args:
        inputs: Operating inputs
        scenario: Scenario to analyze (default: FULL_CIRCULAR)
        discount_rate: Discount rate
        project_years: Project lifetime
        
    Returns:
        CircularEconomyReport with complete analysis
    """
    # Evaluate the scenario
    result = evaluate_scenario(scenario, inputs, discount_rate, project_years)
    
    # Calculate individual pathway revenues
    revenue_by_stream = {}
    pathway_utilization = {}
    
    # Struvite
    if scenario.enable_struvite:
        struvite = calc_struvite_recovery(
            inputs.centrate_m3_annual,
            inputs.p_conc_mg_l,
        )
        revenue_by_stream["Struvite"] = struvite.struvite_kg * scenario.struvite_price_per_kg
        pathway_utilization["Struvite"] = struvite.p_recovery_fraction * 100
    
    # Ammonia
    if scenario.enable_ammonia_stripping:
        ammonia = calc_ammonia_stripping(
            inputs.centrate_m3_annual,
            inputs.n_conc_mg_l,
        )
        revenue_by_stream["Ammonia Sulfate"] = (
            ammonia.ammonium_sulfate_kg * scenario.ammonia_sulfate_price_per_kg
        )
        pathway_utilization["Ammonia"] = ammonia.n_recovery_fraction * 100
    
    # CHP
    if scenario.enable_chp:
        chp = calc_syngas_chp(
            inputs.syngas_excess_mj_annual,
        )
        revenue_by_stream["CHP Electricity"] = (
            chp.electricity_kwh * scenario.electricity_price_per_kwh
        )
        pathway_utilization["CHP"] = chp.electrical_efficiency * 100
    
    # Heat Export
    if scenario.enable_heat_export:
        heat = calc_heat_export(
            inputs.excess_heat_mj_annual,
        )
        revenue_by_stream["Heat Export"] = (
            heat.exported_heat_mj * scenario.heat_price_per_mj
        )
        pathway_utilization["Heat Export"] = (
            heat.exported_heat_mj / max(inputs.excess_heat_mj_annual, 1) * 100
        )
    
    # Char Activation
    if scenario.enable_char_activation:
        char = calc_char_activation(
            inputs.char_kg_annual,
            inputs.steam_kg_annual,
        )
        revenue_by_stream["Activated Carbon"] = (
            char.activated_carbon_kg * scenario.activated_char_price_per_kg
        )
        pathway_utilization["Char Activation"] = (
            char.activated_carbon_kg / max(inputs.char_kg_annual, 1) * 100
        )
    
    # Screenings Reuse
    if scenario.enable_screenings_reuse:
        screenings = calc_screenings_reuse(
            inputs.screenings_kg_annual,
            inputs.grit_kg_annual,
            inputs.ash_kg_annual,
        )
        # Revenue from avoided disposal
        revenue_by_stream["Screenings Reuse"] = screenings.disposal_avoided_kg * 0.05  # ~$50/tonne
        pathway_utilization["Screenings"] = screenings.reuse_fraction * 100
    
    # Carbon Credits
    if scenario.enable_carbon_credits:
        carbon = calc_carbon_credits(
            inputs.char_kg_annual,
        )
        revenue_by_stream["Carbon Credits"] = (
            carbon.credits_earned * scenario.carbon_credit_per_tonne_co2
        )
        pathway_utilization["Carbon Credits"] = 100.0  # Full utilization if enabled
    
    total_revenue = sum(revenue_by_stream.values())
    
    # Calculate mass balance closure (simplified)
    # In a full implementation, this would trace all mass flows
    mass_in = (
        inputs.centrate_m3_annual * 1000 +  # ~1000 kg/m³
        inputs.char_kg_annual +
        inputs.screenings_kg_annual +
        inputs.grit_kg_annual +
        inputs.ash_kg_annual
    )
    mass_out = sum([
        revenue_by_stream.get("Struvite", 0) / scenario.struvite_price_per_kg,
        revenue_by_stream.get("Ammonia Sulfate", 0) / scenario.ammonia_sulfate_price_per_kg,
        revenue_by_stream.get("Activated Carbon", 0) / scenario.activated_char_price_per_kg,
    ])
    mass_balance_closure = mass_out / max(mass_in, 1)  # Will be << 1 for this simplified calc
    
    # Energy balance closure
    energy_in = inputs.syngas_excess_mj_annual + inputs.excess_heat_mj_annual
    energy_out = 0.0
    if scenario.enable_chp:
        chp = calc_syngas_chp(inputs.syngas_excess_mj_annual)
        energy_out += chp.electricity_kwh * 3.6 + chp.waste_heat_mj
    if scenario.enable_heat_export:
        heat = calc_heat_export(inputs.excess_heat_mj_annual)
        energy_out += heat.exported_heat_mj
    energy_balance_closure = energy_out / max(energy_in, 1)
    
    # Carbon sequestration
    carbon_result = calc_carbon_credits(inputs.char_kg_annual)
    carbon_sequestered = carbon_result.co2e_sequestered_kg
    
    # CO2e avoided (from displaced fossil energy)
    co2e_avoided = 0.0
    if scenario.enable_chp:
        chp = calc_syngas_chp(inputs.syngas_excess_mj_annual)
        co2e_avoided += chp.electricity_kwh * 0.4  # ~0.4 kg CO2e/kWh grid average
    if scenario.enable_heat_export:
        heat = calc_heat_export(inputs.excess_heat_mj_annual)
        co2e_avoided += heat.exported_heat_mj * 0.056  # ~56 kg CO2e/GJ natural gas
    
    # Circular economy score (0-100)
    # Weighted composite of pathway utilization
    weights = {
        "Struvite": 0.15,
        "Ammonia": 0.10,
        "CHP": 0.20,
        "Heat Export": 0.15,
        "Char Activation": 0.20,
        "Screenings": 0.10,
        "Carbon Credits": 0.10,
    }
    score = sum(
        pathway_utilization.get(k, 0) * w
        for k, w in weights.items()
    )
    
    # Run viability gates
    gate_report = run_pathway_viability_gates(
        centrate_m3_annual=inputs.centrate_m3_annual,
        p_conc_mg_l=inputs.p_conc_mg_l,
        syngas_excess_mj_annual=inputs.syngas_excess_mj_annual,
        char_kg_annual=inputs.char_kg_annual,
        steam_available_kg_annual=inputs.steam_kg_annual,
        excess_heat_mj_annual=inputs.excess_heat_mj_annual,
        grid_interconnect_available=scenario.enable_chp,
        heat_customer_available=scenario.enable_heat_export,
    )
    
    # Generate recommendations
    recommendations = []
    for gate in gate_report.gates:
        if not gate.passed and gate.remediation:
            recommendations.append(gate.remediation)
    
    if score < 50:
        recommendations.append(
            "Circular economy score below 50%. Consider enabling additional pathways."
        )
    if total_revenue < 10000:
        recommendations.append(
            "Annual pathway revenue below $10k. Review feedstock volumes and pricing."
        )
    
    return CircularEconomyReport(
        scenario_name=scenario.name,
        total_revenue_annual=total_revenue,
        revenue_by_stream=revenue_by_stream,
        mass_balance_closure=mass_balance_closure,
        energy_balance_closure=energy_balance_closure,
        carbon_sequestered_kg_annual=carbon_sequestered,
        co2e_avoided_kg_annual=co2e_avoided,
        circular_economy_score=score,
        pathway_utilization=pathway_utilization,
        gate_report=gate_report,
        recommendations=recommendations,
    )


def print_circular_report(report: CircularEconomyReport) -> None:
    """Print formatted circular economy report."""
    print("\n" + "=" * 80)
    print("CIRCULAR ECONOMY SCENARIO ANALYSIS")
    print(f"Scenario: {report.scenario_name}")
    print("=" * 80)
    
    print("\n--- REVENUE BY STREAM ---")
    for stream, revenue in sorted(report.revenue_by_stream.items(), key=lambda x: -x[1]):
        pct = revenue / max(report.total_revenue_annual, 1) * 100
        print(f"  {stream:25s} {format_currency(revenue):>12s}  ({pct:5.1f}%)")
    print(f"  {'TOTAL':25s} {format_currency(report.total_revenue_annual):>12s}")
    
    print("\n--- PATHWAY UTILIZATION ---")
    for pathway, util in sorted(report.pathway_utilization.items(), key=lambda x: -x[1]):
        bar = "█" * int(util / 5) + "░" * (20 - int(util / 5))
        print(f"  {pathway:20s} [{bar}] {util:5.1f}%")
    
    print("\n--- ENVIRONMENTAL METRICS ---")
    print(f"  Carbon Sequestered:    {report.carbon_sequestered_kg_annual:,.0f} kg CO2e/yr")
    print(f"  Fossil CO2e Avoided:   {report.co2e_avoided_kg_annual:,.0f} kg CO2e/yr")
    print(f"  Total Climate Benefit: {report.carbon_sequestered_kg_annual + report.co2e_avoided_kg_annual:,.0f} kg CO2e/yr")
    
    print("\n--- BALANCE CLOSURE ---")
    print(f"  Mass Balance:   {report.mass_balance_closure * 100:.1f}% (simplified estimate)")
    print(f"  Energy Balance: {report.energy_balance_closure * 100:.1f}%")
    
    print(f"\n--- CIRCULAR ECONOMY SCORE: {report.circular_economy_score:.0f}/100 ---")
    
    # Gate summary
    passed = sum(1 for g in report.gate_report.gates if g.passed)
    total = len(report.gate_report.gates)
    print(f"\n--- VIABILITY GATES: {passed}/{total} PASSED ---")
    for gate in report.gate_report.gates:
        status = "✓" if gate.passed else "✗"
        print(f"  [{status}] {gate.name}")
    
    if report.recommendations:
        print("\n--- RECOMMENDATIONS ---")
        for i, rec in enumerate(report.recommendations, 1):
            print(f"  {i}. {rec}")


# =============================================================================
# CLI Entry Point
# =============================================================================

def create_default_inputs() -> OperatingInputs:
    """Create default operating inputs for CLI demo."""
    return OperatingInputs(
        centrate_m3_annual=1500.0,  # ~1500 m³/yr centrate
        p_conc_mg_l=80.0,  # 80 mg/L P
        n_conc_mg_l=500.0,  # 500 mg/L N
        syngas_excess_mj_annual=200_000.0,  # 200 GJ/yr excess
        char_kg_annual=5000.0,  # 5 tonnes/yr char
        steam_kg_annual=15000.0,  # 15 tonnes/yr steam
        screenings_kg_annual=2000.0,
        grit_kg_annual=1500.0,
        ash_kg_annual=500.0,
        excess_heat_mj_annual=150_000.0,
    )


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="pathway_analysis",
        description="Analyze value-add pathways for waste stream optimization",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # compare-pathways command
    compare_parser = subparsers.add_parser(
        "compare-pathways",
        help="Compare multiple pathway scenarios",
    )
    compare_parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output CSV file path",
    )
    compare_parser.add_argument(
        "--discount-rate",
        type=float,
        default=0.08,
        help="Discount rate for NPV (default: 0.08)",
    )
    compare_parser.add_argument(
        "--years",
        type=int,
        default=20,
        help="Project lifetime in years (default: 20)",
    )
    
    # sweep-struvite command
    struvite_parser = subparsers.add_parser(
        "sweep-struvite",
        help="1D sensitivity sweep on struvite price",
    )
    struvite_parser.add_argument(
        "--min-price",
        type=float,
        default=0.20,
        help="Minimum struvite price $/kg (default: 0.20)",
    )
    struvite_parser.add_argument(
        "--max-price",
        type=float,
        default=1.50,
        help="Maximum struvite price $/kg (default: 1.50)",
    )
    struvite_parser.add_argument(
        "--step",
        type=float,
        default=0.10,
        help="Price step $/kg (default: 0.10)",
    )
    struvite_parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output CSV file path",
    )
    
    # sweep-chp command
    chp_parser = subparsers.add_parser(
        "sweep-chp",
        help="1D sensitivity sweep on CHP capacity",
    )
    chp_parser.add_argument(
        "--min-kw",
        type=float,
        default=10.0,
        help="Minimum CHP capacity kW (default: 10)",
    )
    chp_parser.add_argument(
        "--max-kw",
        type=float,
        default=100.0,
        help="Maximum CHP capacity kW (default: 100)",
    )
    chp_parser.add_argument(
        "--step",
        type=float,
        default=10.0,
        help="Capacity step kW (default: 10)",
    )
    chp_parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output CSV file path",
    )
    
    # circular-scenario command
    circular_parser = subparsers.add_parser(
        "circular-scenario",
        help="Full circular economy scenario analysis",
    )
    circular_parser.add_argument(
        "--years",
        type=int,
        default=20,
        help="Project lifetime in years (default: 20)",
    )
    circular_parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output file path (for future export support)",
    )
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return 1
    
    # Create default inputs
    inputs = create_default_inputs()
    
    if args.command == "compare-pathways":
        result = run_pathway_comparison(
            inputs,
            discount_rate=args.discount_rate,
            project_years=args.years,
        )
        print_comparison_table(result)
        
        if args.output:
            export_comparison_csv(result, args.output)
    
    elif args.command == "sweep-struvite":
        result = sweep_struvite_price(
            inputs,
            SCENARIO_MODERATE,
            (args.min_price, args.max_price, args.step),
        )
        print_sweep_result(result)
        
        if args.output:
            export_sweep_csv(result, args.output)
    
    elif args.command == "sweep-chp":
        result = sweep_chp_capacity(
            inputs,
            SCENARIO_MODERATE,
            (args.min_kw, args.max_kw, args.step),
        )
        print_sweep_result(result)
        
        if args.output:
            export_sweep_csv(result, args.output)
    
    elif args.command == "circular-scenario":
        report = analyze_circular_scenario(
            inputs,
            SCENARIO_FULL_CIRCULAR,
            project_years=args.years,
        )
        print_circular_report(report)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
