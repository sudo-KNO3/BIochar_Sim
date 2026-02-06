"""
Vendor Engagement Packet Generator.

Auto-generates a complete, versioned packet for vendor engagement containing:
    - MVP engineering spec
    - FMEA (with mitigation status)
    - CI gate report
    - DRL report
    - Validation task table (with acceptance criteria)
    - Version hashes for everything

This packet represents the data contract vendors must satisfy.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import json

from septage_model.artifacts.fmea import (
    analyze_fmea, 
    DEFAULT_FAILURE_MODES,
    MitigationStatus,
)
from septage_model.artifacts.versioning import compute_content_hash
from septage_model.artifacts.validation_tasks import (
    get_validation_registry,
    ValidationStatus,
)


@dataclass
class VendorPacket:
    """A complete vendor engagement packet."""
    generated_at: datetime
    version_hash: str
    mvp_spec: Dict[str, Any]
    fmea_summary: Dict[str, Any]
    gate_report: Dict[str, Any]
    drl_report: Dict[str, Any]
    validation_tasks: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "packet_metadata": {
                "generated_at": self.generated_at.isoformat(),
                "version_hash": self.version_hash,
                "format_version": "1.0.0",
            },
            "mvp_spec": self.mvp_spec,
            "fmea_summary": self.fmea_summary,
            "gate_report": self.gate_report,
            "drl_report": self.drl_report,
            "validation_tasks": self.validation_tasks,
        }


def generate_mvp_spec() -> Dict[str, Any]:
    """Generate MVP engineering specification."""
    from septage_model.simulation.deterministic import run_product_mode
    from septage_model.core.parameters import DeploymentMode
    
    result = run_product_mode()
    
    return {
        "title": "Septage-to-Biochar Processing System - Product Mode",
        "revision": "1.0",
        "deployment_mode": "PRODUCT (Owner-Operated)",
        
        "system_overview": {
            "description": (
                "Continuous septage-to-biochar processing system designed for "
                "owner-operated deployment at rural waste handling facilities. "
                "System converts septage and wood co-feed into marketable biochar "
                "while achieving energy self-sufficiency."
            ),
            "primary_constraint": "Serviceability (not thermodynamics)",
            "design_philosophy": "Owner-serviceable with minimal contractor callouts",
        },
        
        "scale_parameters": {
            "annual_septage_m3": 2000,
            "annual_cofeed_tds": 600,
            "operating_days_per_year": 250,
            "operating_hours_per_day": 8,
        },
        
        "performance_requirements": {
            "energy_self_sufficiency": {
                "value": round(result.base_result.energy.energy_self_sufficiency, 2),
                "requirement": ">= 1.0",
                "unit": "ratio",
            },
            "char_production": {
                "value": round(result.base_result.char.annual_char_total_tonnes, 1),
                "unit": "tonnes/year",
            },
            "maintenance_cost": {
                "value": round(result.base_result.economics.maintenance_cost, 0),
                "requirement": "<= 35,000",
                "unit": "$/year",
            },
            "callout_frequency": {
                "value": round(result.base_result.params.maintenance.callouts_per_year / 52, 2),
                "requirement": "<= 1.0",
                "unit": "callouts/week",
            },
        },
        
        "economic_envelope": {
            "target_capex": {
                "value": round(result.base_result.economics.total_capex, 0),
                "tolerance": "±25%",
                "unit": "$",
            },
            "target_payback": {
                "value": round(result.buyer.payback_with_char_revenue, 1),
                "requirement": "<= 15.0",
                "unit": "years",
            },
            "capex_multiplier": {
                "value": 0.6,
                "description": "Product mode vs full-scale hub",
            },
        },
        
        "subsystem_requirements": {
            "receiving": {
                "capacity_m3_hr": 3.0,
                "operating_window": "Mon-Fri, 8hr/day",
            },
            "dewatering": {
                "type": "Screw press or equivalent",
                "cake_ts_target": "20% TS",
                "solids_capture": ">= 95%",
                "owner_serviceable": True,
            },
            "drying": {
                "type": "Indirect heated rotary or paddle",
                "outlet_moisture": "< 10%",
                "heat_source": "Syngas combustion",
                "owner_serviceable": True,
            },
            "pyrolysis": {
                "type": "Continuous auger or rotary",
                "temperature_range": "500-600°C",
                "residence_time": "15-30 min",
                "owner_serviceable": "Partial (seals, discharge)",
            },
            "char_handling": {
                "cooling": "Water-jacketed screw",
                "storage": "Covered silo with discharge",
                "owner_serviceable": True,
            },
            "syngas_system": {
                "combustion": "Direct-fired to dryer",
                "backup": "Propane pilot/aux",
                "flare": "Required for upset conditions",
            },
            "controls": {
                "type": "PLC with HMI",
                "remote_monitoring": "Required",
                "safety_systems": "E-stop, gas detection, fire suppression",
            },
        },
        
        "critical_design_constraints": {
            "owner_serviceability": (
                "All routine maintenance tasks (< 4hr interval) must be "
                "performable by owner with standard tools. Contractor callouts "
                "limited to < 1/week average."
            ),
            "modular_replacement": (
                "High-wear components (auger flights, seals, bearings) must be "
                "designed for modular replacement without specialized equipment."
            ),
            "condition_monitoring": (
                "Vibration, temperature, and torque monitoring required on "
                "all rotating equipment. O2 monitoring required on pyrolyzer."
            ),
        },
    }


def generate_fmea_summary() -> Dict[str, Any]:
    """Generate FMEA summary for packet."""
    analysis = analyze_fmea(DEFAULT_FAILURE_MODES)
    
    # Group by risk level
    critical = [m for m in DEFAULT_FAILURE_MODES if m.is_critical]
    moderate = [m for m in DEFAULT_FAILURE_MODES if m.is_moderate]
    
    # Mitigation status breakdown
    proposed = sum(1 for m in DEFAULT_FAILURE_MODES 
                   if m.mitigation_status == MitigationStatus.PROPOSED)
    implemented = sum(1 for m in DEFAULT_FAILURE_MODES 
                      if m.mitigation_status == MitigationStatus.IMPLEMENTED)
    validated = sum(1 for m in DEFAULT_FAILURE_MODES 
                    if m.mitigation_status == MitigationStatus.VALIDATED)
    
    return {
        "summary": {
            "total_failure_modes": len(DEFAULT_FAILURE_MODES),
            "critical_count": analysis.critical_count,
            "moderate_count": analysis.moderate_count,
            "acceptable_count": analysis.acceptable_count,
            "average_rpn": round(analysis.avg_rpn, 1),
            "owner_serviceable_pct": round(analysis.owner_serviceable_pct, 0),
        },
        "mitigation_status": {
            "proposed": proposed,
            "implemented": implemented,
            "validated": validated,
        },
        "critical_modes": [
            {
                "component": m.component,
                "failure_mode": m.failure_mode,
                "rpn": m.rpn,
                "mitigation": m.mitigation,
                "mitigation_status": m.mitigation_status.value,
            }
            for m in critical
        ],
        "high_rpn_modes": [
            {
                "component": m.component,
                "failure_mode": m.failure_mode,
                "rpn": m.rpn,
                "owner_serviceable": m.owner_serviceable,
            }
            for m in sorted(moderate, key=lambda x: x.rpn, reverse=True)[:5]
        ],
        "vendor_attention_required": (
            "The following components require vendor confirmation of MTBF, "
            "spare parts availability, and maintenance procedures: " +
            ", ".join(set(m.component for m in moderate[:5]))
        ),
    }


def generate_gate_report_summary() -> Dict[str, Any]:
    """Generate CI gate report for packet."""
    from septage_model.simulation.deterministic import run_product_mode
    from septage_model.ci.gates import run_design_gates, MAX_MAINTENANCE_BUDGET, MAX_PAYBACK_YEARS
    
    result = run_product_mode()
    report = run_design_gates(result)
    
    return {
        "status": "PASS" if report.all_passed else "FAIL",
        "gates_passed": len(report.passed_gates),
        "gates_total": len(report.gates),
        "frozen_constraints": {
            "max_maintenance_budget": f"${MAX_MAINTENANCE_BUDGET:,}/year",
            "max_payback_years": f"{MAX_PAYBACK_YEARS} years",
            "max_callouts_per_week": "1.0",
            "energy_self_sufficiency": ">= 100%",
        },
        "gate_results": [
            {
                "name": g.name,
                "status": "PASS" if g.passed else "FAIL",
                "value": round(g.value, 2),
                "threshold": round(g.threshold, 2),
            }
            for g in report.gates
        ],
        "enforcement_statement": (
            "These gates are enforced automatically in CI. Any design change "
            "that violates these constraints will be rejected. Vendor equipment "
            "that cannot meet these requirements is not suitable for this application."
        ),
    }


def generate_drl_summary() -> Dict[str, Any]:
    """Generate DRL report for packet."""
    from septage_model.ci.design_readiness import evaluate_drl_from_results
    
    assessment = evaluate_drl_from_results()
    
    return {
        "achieved_level": assessment.achieved_drl,
        "phase": assessment.achieved_drl_enum.phase if assessment.achieved_drl_enum else "Unknown",
        "description": assessment.achieved_drl_enum.description if assessment.achieved_drl_enum else "",
        "criteria_summary": {
            "total": len(assessment.criteria),
            "passing": len(assessment.passing_criteria),
            "failing": len(assessment.failing_criteria),
        },
        "blocking_for_next_level": [
            {
                "criterion": c.name,
                "description": c.description,
                "required_for_drl": c.required_for_drl,
            }
            for c in assessment.blocking_criteria
        ],
        "interpretation": (
            f"The system is at DRL-{assessment.achieved_drl}, meaning the design is "
            f"analytically validated but awaiting empirical confirmation. "
            f"Advancement to DRL-{assessment.next_drl} requires vendor/lab data "
            f"for {len(assessment.blocking_criteria)} validation tasks."
        ),
    }


def generate_validation_tasks_summary() -> Dict[str, Any]:
    """Generate validation tasks table for packet."""
    registry = get_validation_registry()
    
    tasks_by_drl = {}
    for task in registry.tasks.values():
        drl = task.required_for_drl
        if drl not in tasks_by_drl:
            tasks_by_drl[drl] = []
        
        tasks_by_drl[drl].append({
            "task_id": task.task_id,
            "name": task.name,
            "description": task.description,
            "data_type": task.data_type.value,
            "status": task.status.value,
            "acceptance_criteria": [
                {
                    "parameter": c.parameter,
                    "description": c.description,
                    "expected_value": c.expected_value,
                    "min_value": c.min_value,
                    "max_value": c.max_value,
                    "tolerance_pct": c.tolerance_pct,
                    "unit": c.unit,
                }
                for c in task.acceptance_criteria
            ],
            "notes": task.notes,
        })
    
    return {
        "summary": {
            "total_tasks": len(registry.tasks),
            "validated": len([t for t in registry.tasks.values() 
                            if t.status == ValidationStatus.VALIDATED]),
            "not_started": len([t for t in registry.tasks.values() 
                               if t.status == ValidationStatus.NOT_STARTED]),
        },
        "tasks_by_drl": tasks_by_drl,
        "vendor_action_required": (
            "Vendors are requested to provide data demonstrating that their "
            "equipment meets the acceptance criteria listed below. Data must "
            "include test methodology, sample characteristics, and measured values."
        ),
    }


def generate_vendor_packet(output_dir: Optional[Path] = None) -> VendorPacket:
    """
    Generate complete vendor engagement packet.
    
    Args:
        output_dir: Optional directory to write packet files
    
    Returns:
        VendorPacket with all components
    """
    # Generate all components
    mvp_spec = generate_mvp_spec()
    fmea_summary = generate_fmea_summary()
    gate_report = generate_gate_report_summary()
    drl_report = generate_drl_summary()
    validation_tasks = generate_validation_tasks_summary()
    
    # Compute version hash of entire packet
    all_content = {
        "mvp_spec": mvp_spec,
        "fmea_summary": fmea_summary,
        "gate_report": gate_report,
        "drl_report": drl_report,
        "validation_tasks": validation_tasks,
    }
    version_hash = compute_content_hash(all_content)
    
    packet = VendorPacket(
        generated_at=datetime.now(),
        version_hash=version_hash,
        mvp_spec=mvp_spec,
        fmea_summary=fmea_summary,
        gate_report=gate_report,
        drl_report=drl_report,
        validation_tasks=validation_tasks,
    )
    
    # Write to files if output_dir specified
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Write JSON packet
        json_path = output_dir / f"vendor_packet_{version_hash}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(packet.to_dict(), f, indent=2)
        
        # Write markdown summary
        md_path = output_dir / f"vendor_packet_{version_hash}.md"
        markdown = generate_packet_markdown(packet)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(markdown)
    
    return packet


def generate_packet_markdown(packet: VendorPacket) -> str:
    """Generate markdown version of vendor packet."""
    lines = [
        "# Vendor Engagement Packet",
        "",
        f"**Generated**: {packet.generated_at.strftime('%Y-%m-%d %H:%M')}",
        f"**Version Hash**: `{packet.version_hash}`",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "This packet defines the requirements for vendor equipment to be integrated ",
        "into the Septage-to-Biochar Processing System (Product Mode). Equipment that ",
        "does not meet these requirements cannot be used.",
        "",
        f"**Current Design Readiness Level**: DRL-{packet.drl_report['achieved_level']} ({packet.drl_report['phase']})",
        f"**CI Gate Status**: {packet.gate_report['status']} ({packet.gate_report['gates_passed']}/{packet.gate_report['gates_total']} gates)",
        f"**Critical Failure Modes**: {packet.fmea_summary['summary']['critical_count']}",
        "",
        "---",
        "",
        "## 1. MVP Engineering Specification",
        "",
        f"### {packet.mvp_spec['title']}",
        "",
        f"{packet.mvp_spec['system_overview']['description']}",
        "",
        "### Scale Parameters",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
    ]
    
    for key, value in packet.mvp_spec['scale_parameters'].items():
        lines.append(f"| {key.replace('_', ' ').title()} | {value} |")
    
    lines.extend([
        "",
        "### Performance Requirements",
        "",
        "| Requirement | Value | Threshold |",
        "|-------------|-------|-----------|",
    ])
    
    for key, data in packet.mvp_spec['performance_requirements'].items():
        req = data.get('requirement', '-')
        lines.append(f"| {key.replace('_', ' ').title()} | {data['value']} {data['unit']} | {req} |")
    
    lines.extend([
        "",
        "### Critical Design Constraints",
        "",
    ])
    
    for key, value in packet.mvp_spec['critical_design_constraints'].items():
        lines.append(f"**{key.replace('_', ' ').title()}**: {value}")
        lines.append("")
    
    # Gate Report
    lines.extend([
        "---",
        "",
        "## 2. CI Gate Report",
        "",
        f"**Status**: {packet.gate_report['status']}",
        "",
        "### Frozen Constraints",
        "",
        "| Constraint | Value |",
        "|------------|-------|",
    ])
    
    for key, value in packet.gate_report['frozen_constraints'].items():
        lines.append(f"| {key.replace('_', ' ').title()} | {value} |")
    
    lines.extend([
        "",
        "### Gate Results",
        "",
        "| Gate | Status | Value | Threshold |",
        "|------|--------|-------|-----------|",
    ])
    
    for gate in packet.gate_report['gate_results']:
        status = "✅" if gate['status'] == "PASS" else "❌"
        lines.append(f"| {gate['name']} | {status} | {gate['value']} | {gate['threshold']} |")
    
    lines.extend([
        "",
        f"> {packet.gate_report['enforcement_statement']}",
        "",
    ])
    
    # FMEA Summary
    lines.extend([
        "---",
        "",
        "## 3. FMEA Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Failure Modes | {packet.fmea_summary['summary']['total_failure_modes']} |",
        f"| Critical (RPN > 100) | {packet.fmea_summary['summary']['critical_count']} |",
        f"| Moderate (RPN 50-100) | {packet.fmea_summary['summary']['moderate_count']} |",
        f"| Average RPN | {packet.fmea_summary['summary']['average_rpn']} |",
        f"| Owner Serviceable | {packet.fmea_summary['summary']['owner_serviceable_pct']}% |",
        "",
    ])
    
    if packet.fmea_summary['high_rpn_modes']:
        lines.extend([
            "### Top Risk Modes (Vendor Attention Required)",
            "",
            "| Component | Failure Mode | RPN | Serviceable |",
            "|-----------|--------------|-----|-------------|",
        ])
        for mode in packet.fmea_summary['high_rpn_modes']:
            svc = "✅" if mode['owner_serviceable'] else "❌"
            lines.append(f"| {mode['component']} | {mode['failure_mode']} | {mode['rpn']} | {svc} |")
        lines.append("")
    
    # Validation Tasks
    lines.extend([
        "---",
        "",
        "## 4. Validation Requirements",
        "",
        f"> {packet.validation_tasks['vendor_action_required']}",
        "",
    ])
    
    for drl, tasks in sorted(packet.validation_tasks['tasks_by_drl'].items()):
        lines.extend([
            f"### DRL-{drl} Requirements",
            "",
        ])
        
        for task in tasks:
            lines.extend([
                f"#### {task['name']}",
                "",
                f"**Data Type**: {task['data_type']}",
                f"**Status**: {task['status']}",
                "",
                f"{task['description']}",
                "",
                "**Acceptance Criteria**:",
                "",
                "| Parameter | Expected | Range | Tolerance | Unit |",
                "|-----------|----------|-------|-----------|------|",
            ])
            
            for c in task['acceptance_criteria']:
                lines.append(
                    f"| {c['parameter']} | {c['expected_value']} | "
                    f"{c['min_value']}-{c['max_value']} | ±{c['tolerance_pct']}% | {c['unit']} |"
                )
            
            if task['notes']:
                lines.extend(["", f"*Note: {task['notes']}*"])
            lines.append("")
    
    # Footer
    lines.extend([
        "---",
        "",
        "## 5. DRL Status",
        "",
        f"**Current Level**: DRL-{packet.drl_report['achieved_level']}",
        f"**Phase**: {packet.drl_report['phase']}",
        f"**Description**: {packet.drl_report['description']}",
        "",
        f"{packet.drl_report['interpretation']}",
        "",
        "### Blocking for Next Level",
        "",
    ])
    
    for blocker in packet.drl_report['blocking_for_next_level']:
        lines.append(f"- **{blocker['criterion']}**: {blocker['description']}")
    
    lines.extend([
        "",
        "---",
        "",
        "## Version Control",
        "",
        f"- **Packet Hash**: `{packet.version_hash}`",
        f"- **Generated**: {packet.generated_at.isoformat()}",
        "",
        "This packet is version-controlled. Any modifications will generate a new hash. ",
        "Vendors should reference this hash when submitting data.",
        "",
        "---",
        "",
        "*Generated by Biochar_Sim Vendor Engagement System*",
    ])
    
    return "\n".join(lines)


def print_packet_summary(packet: VendorPacket) -> None:
    """Print packet summary to console."""
    print("=" * 70)
    print("VENDOR ENGAGEMENT PACKET GENERATED")
    print("=" * 70)
    print()
    print(f"Version Hash: {packet.version_hash}")
    print(f"Generated: {packet.generated_at.strftime('%Y-%m-%d %H:%M')}")
    print()
    print("-" * 70)
    print("CONTENTS")
    print("-" * 70)
    print()
    print(f"1. MVP Spec: {packet.mvp_spec['title']}")
    print(f"   - Scale: {packet.mvp_spec['scale_parameters']['annual_septage_m3']} m³/yr septage")
    print(f"   - CAPEX: ${packet.mvp_spec['economic_envelope']['target_capex']['value']:,.0f}")
    print()
    print(f"2. CI Gates: {packet.gate_report['status']} ({packet.gate_report['gates_passed']}/{packet.gate_report['gates_total']})")
    print()
    print(f"3. FMEA: {packet.fmea_summary['summary']['critical_count']} critical, "
          f"{packet.fmea_summary['summary']['moderate_count']} moderate modes")
    print()
    print(f"4. DRL: Level {packet.drl_report['achieved_level']} ({packet.drl_report['phase']})")
    print(f"   - Blocking: {len(packet.drl_report['blocking_for_next_level'])} validation tasks")
    print()
    print(f"5. Validation Tasks: {packet.validation_tasks['summary']['total_tasks']} tasks defined")
    print(f"   - Validated: {packet.validation_tasks['summary']['validated']}")
    print(f"   - Pending: {packet.validation_tasks['summary']['not_started']}")
    print()
    print("=" * 70)
