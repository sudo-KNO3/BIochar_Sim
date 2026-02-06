"""
Physics Assumptions Appendix Generator.

Produces a formal, versionable document listing all physics assumptions,
their literature sources, validation status, and DRL impact.

Use this to freeze the physics basis for design review.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import json

from septage_model.core.parameters import (
    KineticsParams,
    ReactorParams,
    FeedstockProperties,
    SEPTAGE_KINETICS_DEFAULT,
    WOOD_KINETICS_DEFAULT,
    SEPTAGE_SOLIDS_DEFAULT,
    WOOD_CHIPS_DEFAULT,
    REACTOR_DEFAULT,
)
from septage_model.core.pyrolysis_kinetics import list_unvalidated_physics_assumptions


# Literature-backed parameter ranges from the review
LITERATURE_RANGES = {
    # Kinetics - sewage sludge
    "Ea_J_per_mol_sludge": {
        "min": 110e3,
        "max": 310e3,
        "unit": "J/mol",
        "note": "Parallel reactions observed; DAEM studies show up to 400 kJ/mol at high conversion",
    },
    "A_s_inv_sludge": {
        "min": 1e15,
        "max": 1e20,
        "unit": "1/s",
        "note": "Compensates high Ea (compensation effect)",
    },
    "reaction_order": {
        "min": 1.0,
        "max": 1.0,
        "unit": "-",
        "note": "First-order dominant in literature",
    },
    # Conversion requirements
    "X_min_sludge": {
        "min": 0.90,
        "max": 0.95,
        "unit": "-",
        "note": "Required for pathogen destruction, odor elimination",
    },
    "X_min_wood": {
        "min": 0.85,
        "max": 0.90,
        "unit": "-",
        "note": "Char quality priority",
    },
    # Residence time
    "tau_auger": {
        "min": 300,
        "max": 3600,
        "unit": "s",
        "note": "Indirect auger: 5-60 min typical",
    },
    "tau_kiln": {
        "min": 1800,
        "max": 10800,
        "unit": "s",
        "note": "Rotary kiln: 30-180 min typical",
    },
    # Heat transfer
    "U_auger": {
        "min": 200,
        "max": 400,
        "unit": "W/m²·K",
        "note": "CEJ modeling studies for indirect auger",
    },
    "U_kiln": {
        "min": 30,
        "max": 50,
        "unit": "W/m²·K",
        "note": "Applied Thermal Eng. for indirect rotary kiln",
    },
    # Yields - sludge slow pyrolysis ~500°C
    "yield_char_sludge": {
        "min": 0.35,
        "max": 0.55,
        "unit": "kg/kg TDS",
        "note": "High ash inflates char yield",
    },
    "yield_gas_energy_sludge": {
        "min": 2.5,
        "max": 4.5,
        "unit": "MJ/kg TDS",
        "note": "Composition varies widely",
    },
}


@dataclass
class AppendixMetadata:
    """Metadata for the physics appendix document."""
    version: str
    generated_at: str
    generator: str = "Biochar_Sim physics_appendix.py"
    status: str = "UNVALIDATED"  # or "VALIDATED" after lab confirmation


def generate_appendix_markdown(
    kinetics_list: list[KineticsParams],
    reactor: ReactorParams,
    feedstock_list: list[FeedstockProperties],
    version: str = "1.0.0",
    notes: str = "",
) -> str:
    """
    Generate a formal Physics Assumptions Appendix as Markdown.
    
    Args:
        kinetics_list: All KineticsParams in use
        reactor: ReactorParams in use
        feedstock_list: All FeedstockProperties in use
        version: Version string for the appendix
        notes: Additional notes to include
        
    Returns:
        Markdown string suitable for saving to file
    """
    timestamp = datetime.now().isoformat(timespec="seconds")
    
    # Count validation status
    unvalidated_kinetics = [k for k in kinetics_list if not k.validated]
    validated_kinetics = [k for k in kinetics_list if k.validated]
    
    # Get all unvalidated assumptions
    assumptions = list_unvalidated_physics_assumptions(kinetics_list, reactor)
    
    # Collect all source refs
    all_refs = set()
    for k in kinetics_list:
        all_refs.update(k.source_refs)
    
    # Build markdown
    lines = [
        f"# Physics Assumptions Appendix",
        f"",
        f"**Version:** {version}  ",
        f"**Generated:** {timestamp}  ",
        f"**Status:** {'⚠️ UNVALIDATED' if unvalidated_kinetics else '✅ VALIDATED'}  ",
        f"",
        f"---",
        f"",
        f"## 1. Executive Summary",
        f"",
        f"This document records all physics assumptions used in the design-grade",
        f"pyrolysis model. Parameters marked unvalidated are literature-based and",
        f"**block DRL-4+ claims** until confirmed by lab testing.",
        f"",
        f"| Category | Count |",
        f"|----------|-------|",
        f"| Kinetics streams | {len(kinetics_list)} |",
        f"| Validated kinetics | {len(validated_kinetics)} |",
        f"| Unvalidated kinetics | {len(unvalidated_kinetics)} |",
        f"| Unvalidated parameters | {len(assumptions)} |",
        f"| Literature sources | {len(all_refs)} |",
        f"",
        f"---",
        f"",
        f"## 2. Kinetics Parameters",
        f"",
    ]
    
    for k in kinetics_list:
        status = "✅ Validated" if k.validated else "⚠️ Unvalidated"
        lines.extend([
            f"### 2.{kinetics_list.index(k)+1} Stream: `{k.stream_id}`",
            f"",
            f"**Status:** {status}  ",
            f"**Tier:** {k.tier}  ",
            f"",
            f"| Parameter | Value | Literature Range | Unit |",
            f"|-----------|-------|------------------|------|",
            f"| Activation Energy (Ea) | {k.Ea_J_per_mol/1000:.0f} | 110–310 | kJ/mol |",
            f"| Pre-exponential (A) | {k.A_s_inv:.1e} | 10¹⁵–10²⁰ | 1/s |",
            f"| Reaction Order (n) | {k.reaction_order:.1f} | ~1.0 | - |",
            f"| Min Conversion (X_min) | {k.X_min:.2f} | 0.85–0.95 | - |",
            f"",
        ])
        if k.source_refs:
            lines.append(f"**Literature Sources:**")
            for ref in k.source_refs:
                lines.append(f"- `{ref}`")
            lines.append("")
        
        if k.tier == "TIER2_PARALLEL" and k.tier2_Ea_char_J_per_mol:
            lines.extend([
                f"**Tier-2 Parallel Reaction Parameters:**",
                f"",
                f"| Pathway | Ea (kJ/mol) | A (1/s) |",
                f"|---------|-------------|---------|",
                f"| Char | {k.tier2_Ea_char_J_per_mol/1000:.0f} | {k.tier2_A_char_s_inv:.1e} |",
                f"| Volatile | {k.tier2_Ea_vol_J_per_mol/1000:.0f} | {k.tier2_A_vol_s_inv:.1e} |",
                f"",
            ])
    
    lines.extend([
        f"---",
        f"",
        f"## 3. Reactor Parameters",
        f"",
        f"**Type:** {reactor.reactor_type.value}  ",
        f"**RTD Model:** {reactor.rtd_model}  ",
        f"**Validated:** {'✅ Yes' if reactor.validated else '⚠️ No'}  ",
        f"",
        f"### 3.1 Geometry",
        f"",
        f"| Parameter | Value | Unit |",
        f"|-----------|-------|------|",
        f"| Length | {reactor.length_m:.2f} | m |",
        f"| Diameter | {reactor.diameter_m:.3f} | m |",
        f"| Total Volume | {reactor.total_volume_m3:.4f} | m³ |",
        f"| Fill Fraction | {reactor.fill_fraction:.0%} | - |",
        f"| Filled Volume | {reactor.filled_volume_m3:.4f} | m³ |",
        f"",
        f"### 3.2 Heat Transfer",
        f"",
        f"| Parameter | Value | Literature Range | Unit |",
        f"|-----------|-------|------------------|------|",
        f"| Overall U | {reactor.U_w_m2k:.0f} | 30–400 | W/m²·K |",
        f"| Heat Transfer Area | {reactor.heat_transfer_area_m2:.2f} | (calculated) | m² |",
        f"| Wall Temperature | {reactor.T_wall_k - 273.15:.0f} | - | °C |",
        f"| Feed Temperature | {reactor.T_feed_k - 273.15:.0f} | - | °C |",
        f"",
    ])
    
    if reactor.source_refs:
        lines.append(f"**Literature Sources:**")
        for ref in reactor.source_refs:
            lines.append(f"- `{ref}`")
        lines.append("")
    
    lines.extend([
        f"---",
        f"",
        f"## 4. Feedstock Properties",
        f"",
    ])
    
    for i, fs in enumerate(feedstock_list):
        lines.extend([
            f"### 4.{i+1} Feedstock: `{fs.name}`",
            f"",
            f"**Proximate Analysis (dry basis):**",
            f"",
            f"| Component | Value |",
            f"|-----------|-------|",
            f"| Volatile Matter | {fs.proximate.volatile_matter:.1%} |",
            f"| Fixed Carbon | {fs.proximate.fixed_carbon:.1%} |",
            f"| Ash | {fs.proximate.ash:.1%} |",
            f"",
        ])
        if fs.ultimate:
            lines.extend([
                f"**Ultimate Analysis (DAF basis):**",
                f"",
                f"| Element | Value |",
                f"|---------|-------|",
                f"| C | {fs.ultimate.carbon:.1%} |",
                f"| H | {fs.ultimate.hydrogen:.1%} |",
                f"| O | {fs.ultimate.oxygen:.1%} |",
                f"| N | {fs.ultimate.nitrogen:.1%} |",
                f"| S | {fs.ultimate.sulfur:.1%} |",
                f"",
            ])
    
    lines.extend([
        f"---",
        f"",
        f"## 5. Unvalidated Assumptions Summary",
        f"",
        f"The following parameters are literature-based and require lab validation",
        f"before DRL-4+ claims can be made:",
        f"",
        f"| Stream | Parameter | Current Value | DRL Impact |",
        f"|--------|-----------|---------------|------------|",
    ])
    
    for a in assumptions:
        lines.append(f"| {a.stream_id} | {a.parameter} | {a.value} | {a.drl_impact} |")
    
    lines.extend([
        f"",
        f"---",
        f"",
        f"## 6. Literature Sources Registry",
        f"",
        f"All parameters reference entries in `references.json`:",
        f"",
    ])
    
    for ref in sorted(all_refs):
        lines.append(f"- `{ref}`")
    
    lines.extend([
        f"",
        f"---",
        f"",
        f"## 7. Validation Requirements",
        f"",
        f"To advance to DRL-4, the following validation tasks must be completed:",
        f"",
        f"| Task ID | Description | Status |",
        f"|---------|-------------|--------|",
        f"| `kinetics_params_validated` | TGA/DSC for A, Ea, n | ❌ Pending |",
        f"| `tier2_kinetics_validated` | Parallel-reaction model fit | ❌ Pending |",
        f"| `reactor_ua_validated` | Vendor-confirmed U, A | ❌ Pending |",
        f"",
    ])
    
    if notes:
        lines.extend([
            f"---",
            f"",
            f"## 8. Notes",
            f"",
            notes,
            f"",
        ])
    
    lines.extend([
        f"---",
        f"",
        f"*This appendix was auto-generated by `physics_appendix.py`.*  ",
        f"*Do not edit manually; regenerate from code when parameters change.*",
    ])
    
    return "\n".join(lines)


def save_appendix(
    filepath: Path | str,
    kinetics_list: Optional[list[KineticsParams]] = None,
    reactor: Optional[ReactorParams] = None,
    feedstock_list: Optional[list[FeedstockProperties]] = None,
    version: str = "1.0.0",
    notes: str = "",
) -> Path:
    """
    Generate and save the Physics Assumptions Appendix to a file.
    
    Uses defaults if parameters not provided.
    
    Args:
        filepath: Where to save the markdown file
        kinetics_list: KineticsParams list (default: septage + wood)
        reactor: ReactorParams (default: REACTOR_DEFAULT)
        feedstock_list: FeedstockProperties list (default: septage + wood)
        version: Version string
        notes: Additional notes
        
    Returns:
        Path to saved file
    """
    if kinetics_list is None:
        kinetics_list = [SEPTAGE_KINETICS_DEFAULT, WOOD_KINETICS_DEFAULT]
    if reactor is None:
        reactor = REACTOR_DEFAULT
    if feedstock_list is None:
        feedstock_list = [SEPTAGE_SOLIDS_DEFAULT, WOOD_CHIPS_DEFAULT]
    
    content = generate_appendix_markdown(
        kinetics_list=kinetics_list,
        reactor=reactor,
        feedstock_list=feedstock_list,
        version=version,
        notes=notes,
    )
    
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding="utf-8")
    
    return filepath


def print_appendix_summary(
    kinetics_list: Optional[list[KineticsParams]] = None,
    reactor: Optional[ReactorParams] = None,
) -> None:
    """Print a brief summary of the physics assumptions status."""
    if kinetics_list is None:
        kinetics_list = [SEPTAGE_KINETICS_DEFAULT, WOOD_KINETICS_DEFAULT]
    if reactor is None:
        reactor = REACTOR_DEFAULT
    
    assumptions = list_unvalidated_physics_assumptions(kinetics_list, reactor)
    unvalidated_count = len([k for k in kinetics_list if not k.validated])
    
    print("=" * 60)
    print("PHYSICS ASSUMPTIONS STATUS")
    print("=" * 60)
    print(f"Kinetics streams:        {len(kinetics_list)}")
    print(f"Unvalidated streams:     {unvalidated_count}")
    print(f"Unvalidated parameters:  {len(assumptions)}")
    print(f"DRL status:              {'DRL-3 (screening)' if unvalidated_count > 0 else 'DRL-4+ eligible'}")
    print("=" * 60)
    
    if assumptions:
        print("\n⚠️  UNVALIDATED - Lab data required for DRL-4+")
    else:
        print("\n✅ All physics assumptions validated")


# Convenience function for freezing v1.0
def freeze_design_physics_v1(
    output_dir: Path | str = Path("docs"),
    notes: str = "Initial design physics freeze. All kinetics literature-based.",
) -> Path:
    """
    Freeze the current physics as Design Physics v1.0.
    
    Creates a versioned appendix document for design review.
    
    Args:
        output_dir: Directory to save the appendix
        notes: Notes to include in the document
        
    Returns:
        Path to the saved appendix file
    """
    output_dir = Path(output_dir)
    timestamp = datetime.now().strftime("%Y%m%d")
    filename = f"physics_appendix_v1.0_{timestamp}.md"
    
    return save_appendix(
        filepath=output_dir / filename,
        version="1.0.0",
        notes=notes,
    )
