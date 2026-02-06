#!/usr/bin/env python3
"""
Septage-to-Biochar Simulation - Entry Point

Usage:
    python run.py                    # Run full Stage 1 analysis
    python run.py --sanity           # Quick sanity checks only
    python run.py --scenario cofeed  # Run co-feed scenario
    python run.py --help             # Show help

Examples:
    python run.py
    python run.py --sanity
    python run.py --scenario high_discharge
"""

import argparse
import sys

from septage_model import (
    run_stage1,
    run_sanity_checks,
    print_stage1_summary,
    create_baseline_parameters,
)
from septage_model.core.parameters import (
    create_cofeed_scenario,
    create_high_discharge_scenario,
)


def main():
    parser = argparse.ArgumentParser(
        description="Septage-to-Biochar Regional Hub Simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Scenarios:
  baseline       Conservative baseline (5000 m³/yr, Q_permit=3.0 m³/hr)
  cofeed         Baseline with winter co-feed enabled
  high_discharge Baseline with Q_permit=5.0 m³/hr

Examples:
  python run.py                     Run baseline Stage 1 analysis
  python run.py --sanity            Quick parameter validation
  python run.py --scenario cofeed   Run with co-feed enabled
        """
    )
    
    parser.add_argument(
        "--sanity",
        action="store_true",
        help="Run sanity checks only (fast validation)"
    )
    
    parser.add_argument(
        "--scenario",
        choices=["baseline", "cofeed", "high_discharge"],
        default="baseline",
        help="Parameter scenario to use (default: baseline)"
    )
    
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Minimal output (status only)"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version="Septage-to-Biochar Simulation v1.0.0"
    )
    
    args = parser.parse_args()
    
    # Select scenario
    if args.scenario == "baseline":
        params = create_baseline_parameters()
    elif args.scenario == "cofeed":
        params = create_cofeed_scenario()
    elif args.scenario == "high_discharge":
        params = create_high_discharge_scenario()
    else:
        params = create_baseline_parameters()
    
    if args.sanity:
        print("=" * 60)
        print("SANITY CHECKS")
        print("=" * 60)
        print(f"Parameter Set: {params.name}")
        print(f"Hash: {params.compute_hash()}")
        print()
        
        passed, issues = run_sanity_checks(params)
        
        if passed:
            print("✓ All sanity checks passed!")
            return 0
        else:
            print("✗ Sanity check failures:")
            for issue in issues:
                print(f"  - {issue}")
            return 1
    
    # Run full Stage 1 analysis
    if not args.quiet:
        print("Running Stage 1 Deterministic Analysis...")
        print()
    
    result = run_stage1(params)
    
    if args.quiet:
        status_map = {
            "VIABLE": "✓ VIABLE",
            "MARGINAL": "⚠ MARGINAL", 
            "NOT_VIABLE": "✗ NOT VIABLE"
        }
        print(f"Status: {status_map.get(result.overall_status.name, result.overall_status.name)}")
        print(f"Payback: {result.economics.simple_payback_years:.1f} years")
        print(f"CAPEX: ${result.economics.total_capex:,.0f}")
    else:
        print_stage1_summary(result)
    
    # Return appropriate exit code
    if result.overall_status.name == "NOT_VIABLE":
        return 2
    elif result.overall_status.name == "MARGINAL":
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
