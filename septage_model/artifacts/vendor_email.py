"""
Vendor Email Generator.

Generates structured outreach emails for vendor validation requests.
Uses rich vendor data from vendors.json while keeping Vendor dataclass minimal.

Key Functions:
    - load_vendor_details(vendor_id): Get full vendor record from JSON
    - generate_vendor_request_email(vendor_id, task_ids): Create email for outreach
    - get_response_schema_dewatering(): Expected JSON format for dewatering data
    - get_response_schema_pyrolysis(): Expected JSON format for pyrolysis data
    - print_email(email): Format for copy-paste into email client
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime
import json

from septage_model.artifacts.validation_tasks import (
    get_validation_registry,
    ValidationTask,
    AcceptanceCriterion,
)


def get_current_packet_hash() -> str:
    """
    Get the current vendor packet hash.
    
    Looks for existing packet files in docs/vendor/ and extracts hash from filename.
    If no packet exists, generates one and returns its hash.
    """
    packet_dir = Path(__file__).parent.parent.parent / "docs" / "vendor"
    packet_files = list(packet_dir.glob("vendor_packet_*.json"))
    
    if packet_files:
        # Extract hash from most recent packet filename
        # Format: vendor_packet_<hash>.json
        latest = sorted(packet_files)[-1]
        filename = latest.stem  # vendor_packet_1ee87b8d691d
        parts = filename.split("_")
        if len(parts) >= 3:
            return parts[2]  # The hash part
    
    # No existing packet - generate one to get hash
    from septage_model.artifacts.vendor_packet import generate_vendor_packet
    packet = generate_vendor_packet()
    return packet.version_hash


# =============================================================================
# Configuration
# =============================================================================

VENDORS_JSON_PATH = Path(__file__).parent.parent.parent / "docs" / "vendor" / "vendors.json"
PROJECT_NAME = "Biochar Septage Processing System"
REQUESTER_NAME = "Kiefer Galliford"
REQUESTER_TITLE = "Pricing"
REQUESTER_ORG = "Azimuth"
REQUESTER_EMAIL = "kgalliford@azimuthenvironmental.com"
REQUESTER_PHONE = "705-331-6677"


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class VendorEmail:
    """A structured vendor outreach email."""
    vendor_id: str
    legal_name: str
    to_address: str
    subject: str
    body: str
    task_ids: List[str]
    packet_hash: str
    generated_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "vendor_id": self.vendor_id,
            "legal_name": self.legal_name,
            "to_address": self.to_address,
            "subject": self.subject,
            "body": self.body,
            "task_ids": self.task_ids,
            "packet_hash": self.packet_hash,
            "generated_at": self.generated_at.isoformat(),
        }


# =============================================================================
# Vendor Details Helper
# =============================================================================

def load_vendor_details(vendor_id: str) -> Dict[str, Any]:
    """
    Load full vendor record from vendors.json.
    
    This returns the complete vendor entry including all extended fields
    (phone, emails, address, named_contacts, data_capability, etc.)
    that are not stored in the minimal Vendor dataclass.
    
    Args:
        vendor_id: The vendor identifier (e.g., 'fournier_industries')
        
    Returns:
        Full vendor dictionary from JSON
        
    Raises:
        ValueError: If vendor_id not found in registry
        FileNotFoundError: If vendors.json doesn't exist
    """
    if not VENDORS_JSON_PATH.exists():
        raise FileNotFoundError(f"Vendor registry not found at {VENDORS_JSON_PATH}")
    
    with open(VENDORS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if vendor_id not in data:
        available = [k for k in data.keys() if not k.startswith("_")]
        raise ValueError(
            f"Vendor '{vendor_id}' not found. "
            f"Available: {available}"
        )
    
    return data[vendor_id]


def list_all_vendor_ids() -> List[str]:
    """Return all vendor IDs in the registry."""
    if not VENDORS_JSON_PATH.exists():
        return []
    
    with open(VENDORS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return [k for k in data.keys() if not k.startswith("_")]


def list_vendors_by_category(category: str) -> List[str]:
    """Return vendor IDs filtered by category ('dewatering' or 'pyrolysis')."""
    if not VENDORS_JSON_PATH.exists():
        return []
    
    with open(VENDORS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return [
        k for k, v in data.items() 
        if not k.startswith("_") and v.get("category") == category
    ]


# =============================================================================
# Response Schema Definitions
# =============================================================================

def get_response_schema_dewatering() -> Dict[str, Any]:
    """
    Return the expected JSON schema for dewatering vendor responses.
    
    This schema maps to the acceptance criteria in validation task
    'dewatering_params_validated'.
    """
    return {
        "_schema_version": "1.0.0",
        "_description": "Dewatering validation data submission format",
        "packet_hash": "<string: hash from vendor packet header>",
        "validation_task": "dewatering_params_validated",
        "evidence_type": "bench_test | pilot_test | field_data",
        "test_conditions": {
            "feedstock_description": "<septage source and characteristics>",
            "feedstock_ts_fraction": "<inlet total solids, fraction>",
            "equipment_model": "<dewatering equipment used>",
            "test_date": "<YYYY-MM-DD>",
            "n_batches": "<number of test batches>",
        },
        "results": {
            "cake_ts_fraction": "<0.18-0.25 fraction, required>",
            "solids_capture": "<0.90-1.0 fraction, required>",
            "polymer_kg_per_tds": "<3-8 kg/TDS, required>",
            "power_kwh_per_m3": "<1-4 kWh/m³, required>",
        },
        "supporting_documents": [
            {"filename": "<string>", "description": "<string>"}
        ],
        "vendor_notes": "<any additional context>",
    }


def get_response_schema_pyrolysis() -> Dict[str, Any]:
    """
    Return the expected JSON schema for pyrolysis vendor responses.
    
    This schema maps to the acceptance criteria in validation task
    'pyrolysis_yields_validated'.
    """
    return {
        "_schema_version": "1.0.0",
        "_description": "Pyrolysis validation data submission format",
        "packet_hash": "<string: hash from vendor packet header>",
        "validation_task": "pyrolysis_yields_validated",
        "evidence_type": "lab_test | pilot_test | field_data",
        "test_conditions": {
            "feedstock_description": "<dewatered septage cake and/or wood co-feed>",
            "feedstock_ts_fraction": "<inlet total solids, fraction>",
            "pyrolysis_temp_c": "<500-600°C typical>",
            "residence_time_min": "<15-30 min typical>",
            "equipment_model": "<pyrolysis equipment used>",
            "test_date": "<YYYY-MM-DD>",
        },
        "results": {
            "char_yield_septage": "<0.35-0.55 kg char/kg TDS, if tested>",
            "char_yield_cofeed": "<0.25-0.45 kg char/kg TDS, if tested>",
            "syngas_yield_septage": "<2.5-4.5 MJ/kg TDS, if tested>",
            "syngas_yield_cofeed": "<4.0-6.5 MJ/kg TDS, if tested>",
        },
        "char_quality": {
            "carbon_content_pct": "<optional, % by mass>",
            "ash_content_pct": "<optional, % by mass>",
            "surface_area_m2_g": "<optional, BET surface area>",
        },
        "supporting_documents": [
            {"filename": "<string>", "description": "<string>"}
        ],
        "vendor_notes": "<any additional context>",
    }


# =============================================================================
# Email Generation
# =============================================================================

def _format_acceptance_criteria(criteria: List[AcceptanceCriterion]) -> str:
    """Format acceptance criteria as readable table."""
    lines = []
    lines.append("  Parameter                      | Expected   | Range            | Unit")
    lines.append("  -------------------------------|------------|------------------|--------")
    for c in criteria:
        param = c.parameter.ljust(30)
        expected = f"{c.expected_value:.3g}".ljust(10)
        range_str = f"{c.min_value:.2g} – {c.max_value:.2g}".ljust(16)
        lines.append(f"  {param} | {expected} | {range_str} | {c.unit}")
    return "\n".join(lines)


def generate_vendor_request_email(
    vendor_id: str,
    task_ids: Optional[List[str]] = None,
) -> VendorEmail:
    """
    Generate a structured vendor outreach email.
    
    Args:
        vendor_id: The vendor to contact (must exist in vendors.json)
        task_ids: Specific validation tasks to request. If None, infers from
                  vendor category (dewatering → dewatering_params_validated,
                  pyrolysis → pyrolysis_yields_validated)
    
    Returns:
        VendorEmail dataclass with all fields populated
    """
    vendor = load_vendor_details(vendor_id)
    category = vendor.get("category", "unknown")
    legal_name = vendor.get("legal_name", vendor_id)
    
    # Determine to address
    to_address = vendor.get("contact_email", "")
    if not to_address and vendor.get("emails"):
        to_address = vendor["emails"][0]
    
    # Infer task IDs if not provided
    if task_ids is None:
        if category == "dewatering":
            task_ids = ["dewatering_params_validated"]
        elif category == "pyrolysis":
            task_ids = ["pyrolysis_yields_validated"]
        else:
            task_ids = []
    
    # Get validation task details
    val_registry = get_validation_registry()
    
    packet_hash = get_current_packet_hash()
    
    # Build email content
    subject = f"Technical Data Request: {PROJECT_NAME} – {category.title()} Validation"
    
    body_parts = []
    
    # Greeting
    named_contacts = vendor.get("named_contacts", [])
    if named_contacts:
        contact_name = named_contacts[0].get("name", "")
        if contact_name:
            body_parts.append(f"Dear {contact_name},")
        else:
            body_parts.append(f"Dear {legal_name} Team,")
    else:
        body_parts.append(f"Dear {legal_name} Team,")
    
    body_parts.append("")
    
    # Introduction
    body_parts.append(
        f"I am reaching out regarding a technical design validation project for a "
        f"septage-to-biochar processing system. We are evaluating {category} equipment "
        f"and would like to request performance data to validate our engineering model."
    )
    body_parts.append("")
    
    # Project context
    body_parts.append("PROJECT CONTEXT:")
    body_parts.append("-" * 40)
    body_parts.append(
        "We are developing a small-scale septage processing system designed for "
        "rural owner-operator deployment. The system converts septage and wood "
        "co-feed into marketable biochar while achieving thermal self-sufficiency."
    )
    body_parts.append("")
    
    # Validation requirements per task
    for task_id in task_ids:
        task = val_registry.get(task_id)
        if task is None:
            continue
        
        body_parts.append(f"VALIDATION REQUIREMENT: {task.name}")
        body_parts.append("-" * 40)
        body_parts.append(task.description)
        body_parts.append("")
        body_parts.append("Acceptance Criteria:")
        body_parts.append(_format_acceptance_criteria(task.acceptance_criteria))
        body_parts.append("")
        body_parts.append(f"Evidence Type: {task.data_type.value}")
        if task.notes:
            body_parts.append(f"Notes: {task.notes}")
        body_parts.append("")
    
    # Data request
    body_parts.append("DATA REQUEST:")
    body_parts.append("-" * 40)
    body_parts.append(
        "If you have performance data from bench tests, pilot studies, or customer "
        "installations that could help validate these parameters, we would greatly "
        "appreciate any information you can share."
    )
    body_parts.append("")
    body_parts.append("Specifically, we are looking for:")
    if category == "dewatering":
        body_parts.append("  • Cake solids content achievable with septage feedstock")
        body_parts.append("  • Solids capture efficiency")
        body_parts.append("  • Polymer consumption rates")
        body_parts.append("  • Power consumption data")
    elif category == "pyrolysis":
        body_parts.append("  • Char yields from biosolids or similar organic feedstocks")
        body_parts.append("  • Syngas production and energy content")
        body_parts.append("  • Char quality characteristics")
        body_parts.append("  • Operating temperature and residence time data")
    body_parts.append("")
    
    # Reference info
    body_parts.append("REFERENCE INFORMATION:")
    body_parts.append("-" * 40)
    body_parts.append(f"Packet Hash: {packet_hash}")
    body_parts.append(
        "This hash identifies the specific version of our engineering model. "
        "Please include it in any data submission for traceability."
    )
    body_parts.append("")
    
    # Response format
    body_parts.append("RESPONSE FORMAT:")
    body_parts.append("-" * 40)
    body_parts.append(
        "We can accept data in any format (PDF reports, spreadsheets, etc.). "
        "If possible, structured data (JSON or tabular) helps accelerate our "
        "validation process. A template schema is available upon request."
    )
    body_parts.append("")
    
    # Closing
    body_parts.append(
        "We understand that detailed performance data may be proprietary. We are "
        "happy to sign an NDA if required, and any data shared will be used solely "
        "for model validation purposes."
    )
    body_parts.append("")
    body_parts.append("Thank you for your consideration.")
    body_parts.append("")
    body_parts.append("Best regards,")
    body_parts.append(REQUESTER_NAME)
    body_parts.append(REQUESTER_TITLE)
    body_parts.append(REQUESTER_ORG)
    body_parts.append(REQUESTER_EMAIL)
    body_parts.append(REQUESTER_PHONE)
    
    body = "\n".join(body_parts)
    
    return VendorEmail(
        vendor_id=vendor_id,
        legal_name=legal_name,
        to_address=to_address,
        subject=subject,
        body=body,
        task_ids=task_ids,
        packet_hash=packet_hash,
        generated_at=datetime.now(),
    )


def print_email(email: VendorEmail) -> None:
    """
    Print email in copy-paste format for email client.
    
    Args:
        email: The VendorEmail to format and print
    """
    print("=" * 70)
    print(f"TO: {email.to_address}")
    print(f"SUBJECT: {email.subject}")
    print("=" * 70)
    print()
    print(email.body)
    print()
    print("=" * 70)
    print(f"[Generated {email.generated_at.isoformat()} | Packet: {email.packet_hash}]")
    print(f"[Vendor: {email.vendor_id} | Tasks: {', '.join(email.task_ids)}]")
    print("=" * 70)


def generate_all_priority_emails() -> Dict[str, VendorEmail]:
    """
    Generate emails for priority vendors (Canadian first, then US).
    
    Returns:
        Dict mapping vendor_id to VendorEmail
    """
    priority_order = [
        # Canadian vendors first
        "fournier_industries",      # CA, dewatering, named contact
        "klean_industries",         # CA, pyrolysis, pilot-capable
        "flottweg_canada",          # CA, dewatering, backup
        "airex_energy",             # CA, pyrolysis (form-only)
        # US vendors
        "phoenix_process_equipment", # US, dewatering
        "biomass_controls",          # US, pyrolysis, high-moisture
        "aries_clean_technologies",  # US, pyrolysis, biosolids-focused
        # European
        "pyreg",                     # DE, pyrolysis, pilot-capable
    ]
    
    emails = {}
    for vendor_id in priority_order:
        try:
            emails[vendor_id] = generate_vendor_request_email(vendor_id)
        except (ValueError, FileNotFoundError) as e:
            print(f"Warning: Could not generate email for {vendor_id}: {e}")
    
    return emails


# =============================================================================
# Overnight Follow-Up Email Generation
# =============================================================================

PYROLYSIS_VENDOR_IDS = [
    "klean_industries",
    "pyreg",
    # "airex_energy",  # form_only, skip
    "biomass_controls",
    "beston_group",
    "aries_clean_technologies",
]


def generate_pyrolysis_overnight_followup_email(vendor_id: str) -> VendorEmail:
    """
    Follow-up email for pyrolysis vendors: unattended/overnight operation capability.
    """
    vendor = load_vendor_details(vendor_id)
    packet_hash = get_current_packet_hash()

    # Greeting: use first named contact if available
    named_contacts = vendor.get("named_contacts") or []
    greeting_name = None
    if isinstance(named_contacts, list) and named_contacts:
        first = named_contacts[0]
        if isinstance(first, dict):
            greeting_name = first.get("name")
    greeting = f"Dear {greeting_name}," if greeting_name else "Dear Team,"

    # Email address
    emails = vendor.get("emails")
    to_email = emails[0] if isinstance(emails, list) and emails else vendor.get("email")
    if not to_email:
        raise ValueError(f"Vendor '{vendor_id}' has no email address on record.")

    legal_name = vendor.get("legal_name", vendor_id)

    subject = f"Follow-Up Technical Questions – Unattended / Overnight Operation ({legal_name})"

    body = f"""{greeting}

Following up on our earlier technical data request regarding the septage-to-biochar system (Packet Hash {packet_hash}), we have a short set of clarifying questions specific to unattended / overnight operation.

Our deployment model assumes a 9–5 light-operations facility, with no overnight staffing and only alarm notification after hours. Reactor stability and fail-safe behavior during unattended periods are therefore critical design constraints.

Please advise on the following for your pyrolysis system:

1) Unattended hold mode
   - Can the system safely enter a hold/idle mode when feed is stopped?
   - In hold mode, does the reactor:
     ☐ remain hot
     ☐ cool down in a controlled manner
     ☐ require purge and/or inerting (N₂/steam) before/during hold

2) Alarm vs auto-shutdown philosophy
   For off-hours operation, does the system:
     ☐ alarm only (requires operator intervention next day)
     ☐ automatically reduce feed / ramp down
     ☐ automatically shut down to a safe state
   Please list which parameters trigger automatic action (e.g., temperature deviation, pressure, oxygen ingress, auger torque, burner fault, flare fault).

3) Overnight thermal stability
   - Does the reactor require continuous heat input overnight to maintain integrity?
   - If heat is lost or the system cools:
     - Are there risks of tar condensation, plugging, corrosion, or refractory/liner damage?
     - Any minimum temperature you recommend to avoid operational issues?

4) Restart after overnight hold
   - Typical restart time from:
     ☐ hot hold
     ☐ warm standby
     ☐ cold shutdown
   - Does restart require operator presence throughout, or only for initiation?

5) Reference installations (if available)
   - Do you have reference installations operating with daytime staffing only and automated overnight hold?
   - If yes: feedstocks, throughput, and typical operating temperature range.

We understand some information may be proprietary; high-level answers are sufficient at this stage. Please reference Packet Hash {packet_hash} in any response for traceability.

Best regards,
Kiefer Galliford
Azimuth Environmental
kgalliford@azimuthenvironmental.com
705-331-6677
"""

    return VendorEmail(
        vendor_id=vendor_id,
        legal_name=legal_name,
        to_address=to_email,
        subject=subject,
        body=body,
        task_ids=["FOLLOWUP-OVERNIGHT"],
        packet_hash=packet_hash,
        generated_at=datetime.now(),
    )


def generate_all_pyrolysis_overnight_followups() -> List[VendorEmail]:
    """Generate overnight follow-up emails for all pyrolysis vendors (excluding form-only)."""
    return [generate_pyrolysis_overnight_followup_email(vid) for vid in PYROLYSIS_VENDOR_IDS]


# =============================================================================
# CLI Entry Point
# =============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m septage_model.artifacts.vendor_email <vendor_id>")
        print("       python -m septage_model.artifacts.vendor_email --followup-overnight")
        print()
        print("Available vendors:")
        for vid in list_all_vendor_ids():
            vendor = load_vendor_details(vid)
            cat = vendor.get("category", "?")
            country = vendor.get("country", "?")
            print(f"  {vid:<40} [{cat:<10}] ({country})")
        sys.exit(0)

    if sys.argv[1] == "--followup-overnight":
        emails = generate_all_pyrolysis_overnight_followups()
        for email in emails:
            print("=" * 60)
            print_email(email)
        print(f"\n[Generated {len(emails)} overnight follow-up emails]")
        sys.exit(0)

    vendor_id = sys.argv[1]

    try:
        email = generate_vendor_request_email(vendor_id)
        print_email(email)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}")
        sys.exit(1)
