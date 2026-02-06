"""
Vendor Inbox Monitor.

Monitors Outlook inbox for vendor responses and processes validation data.
Supports both interactive mode (check once) and watch mode (continuous polling).

Usage:
    # Check inbox once
    python -m septage_model.artifacts.vendor_inbox_monitor
    
    # Watch mode (polls every 5 minutes)
    python -m septage_model.artifacts.vendor_inbox_monitor --watch
    
    # Process a specific email by subject
    python -m septage_model.artifacts.vendor_inbox_monitor --subject "Re: Technical Data Request"
"""

import win32com.client
import json
import re
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum

from septage_model.artifacts.vendor_email import (
    load_vendor_details,
    list_all_vendor_ids,
    get_current_packet_hash,
)
from septage_model.artifacts.vendor_intake import (
    VendorSubmission,
    validate_vendor_submission,
    persist_submission,
    ParameterResult,
)
from septage_model.artifacts.vendor_registry import get_vendor_registry


# =============================================================================
# Configuration
# =============================================================================

INBOX_FOLDER = "Inbox"
PROCESSED_LOG_PATH = Path(__file__).parent.parent.parent / "docs" / "vendor" / "processed_emails.json"
SUBMISSIONS_DIR = Path(__file__).parent.parent.parent / "docs" / "vendor" / "submissions"
ATTACHMENTS_DIR = Path(__file__).parent.parent.parent / "docs" / "vendor" / "attachments"

# Vendor email domains for matching
VENDOR_DOMAINS = {
    "fournierindustries.com": "fournier_industries",
    "dewater.com": "phoenix_process_equipment",
    "alarcorp.com": "alar_engineering_ovivo",
    "ovivowater.com": "alar_engineering_ovivo",
    "ecologixsystems.com": "ecologix_environmental_systems",
    "flottweg.net": "flottweg_canada",
    "flottweg.com": "flottweg_canada",
    "huber.de": "huber_global",
    "huber-se.com": "huber_global",
    "hhusa.net": "huber_global",
    "andritz.com": "andritz_dewatering_service",
    "kleanindustries.com": "klean_industries",
    "pyreg.de": "pyreg",
    "pyreg.com": "pyreg",
    "airex-energy.com": "airex_energy",
    "biomasscontrols.com": "biomass_controls",
    "bestongroup.com": "beston_group",
    "ariescleantech.com": "aries_clean_technologies",
}


# =============================================================================
# Data Structures
# =============================================================================

class EmailStatus(Enum):
    NEW = "new"
    PROCESSED = "processed"
    IGNORED = "ignored"
    ERROR = "error"


@dataclass
class VendorEmailMatch:
    """A matched vendor email from inbox."""
    subject: str
    sender_email: str
    sender_name: str
    received_time: datetime
    body: str
    attachments: List[str]
    vendor_id: Optional[str]
    entry_id: str  # Outlook EntryID for tracking


@dataclass 
class ParsedSubmission:
    """Parsed data from vendor email."""
    vendor_id: str
    validation_task: str
    evidence_type: str
    results: Dict[str, float]
    test_conditions: Dict[str, Any]
    raw_text: str
    attachments: List[str]
    confidence: float  # 0-1, how confident we are in the parse


# =============================================================================
# Email Matching
# =============================================================================

def get_vendor_id_from_email(email_address: str) -> Optional[str]:
    """Match an email address to a vendor ID based on domain."""
    if not email_address:
        return None
    
    # Extract domain
    match = re.search(r'@([\w.-]+)', email_address.lower())
    if not match:
        return None
    
    domain = match.group(1)
    
    # Direct domain match
    if domain in VENDOR_DOMAINS:
        return VENDOR_DOMAINS[domain]
    
    # Try matching subdomains
    for vendor_domain, vendor_id in VENDOR_DOMAINS.items():
        if domain.endswith(vendor_domain) or vendor_domain.endswith(domain):
            return vendor_id
    
    return None


def is_vendor_response(subject: str, body: str) -> bool:
    """Check if email appears to be a vendor response to our request."""
    subject_lower = subject.lower()
    body_lower = body.lower()
    
    # Check for our request indicators
    indicators = [
        "technical data request" in subject_lower,
        "biochar" in subject_lower or "biochar" in body_lower,
        "septage" in subject_lower or "septage" in body_lower,
        "dewatering" in subject_lower or "dewatering" in body_lower,
        "pyrolysis" in subject_lower or "pyrolysis" in body_lower,
        "1ee87b8d691d" in body,  # packet hash
        "validation" in subject_lower,
    ]
    
    return sum(indicators) >= 2


# =============================================================================
# Data Extraction
# =============================================================================

def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Try to extract JSON data from email text."""
    # Look for JSON blocks
    json_patterns = [
        r'\{[^{}]*"results"[^{}]*\{[^{}]*\}[^{}]*\}',  # nested results object
        r'\{[^{}]*"cake_ts_fraction"[^{}]*\}',  # dewatering params
        r'\{[^{}]*"char_yield"[^{}]*\}',  # pyrolysis params
        r'```json\s*(.*?)\s*```',  # markdown code blocks
        r'```\s*(.*?)\s*```',  # generic code blocks
    ]
    
    for pattern in json_patterns:
        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
        for match in matches:
            try:
                if isinstance(match, tuple):
                    match = match[0]
                data = json.loads(match)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue
    
    return None


def extract_tabular_data(text: str) -> Dict[str, float]:
    """Extract parameter values from tabular or inline text."""
    results = {}
    
    # Common parameter patterns
    patterns = {
        # Dewatering
        "cake_ts_fraction": [
            r'cake\s*(?:ts|solids|total\s*solids)[^\d]*(\d+\.?\d*)\s*%',
            r'(?:ts|solids)\s*(?:content|fraction)[^\d]*(\d+\.?\d*)\s*%',
            r'(\d+\.?\d*)\s*%\s*(?:ts|solids|dry)',
        ],
        "solids_capture": [
            r'(?:solids?\s*)?capture[^\d]*(\d+\.?\d*)\s*%',
            r'recovery[^\d]*(\d+\.?\d*)\s*%',
            r'(\d+\.?\d*)\s*%\s*capture',
        ],
        "polymer_kg_per_tds": [
            r'polymer[^\d]*(\d+\.?\d*)\s*(?:kg|kilograms?)',
            r'(\d+\.?\d*)\s*(?:kg|kilograms?)\s*(?:polymer|per\s*t)',
        ],
        "power_kwh_per_m3": [
            r'power[^\d]*(\d+\.?\d*)\s*(?:kwh|kw)',
            r'energy[^\d]*(\d+\.?\d*)\s*(?:kwh|kw)',
            r'(\d+\.?\d*)\s*kwh',
        ],
        # Pyrolysis
        "char_yield_septage": [
            r'char\s*yield[^\d]*(\d+\.?\d*)\s*%',
            r'biochar[^\d]*(\d+\.?\d*)\s*%',
            r'(\d+\.?\d*)\s*%\s*char',
        ],
        "syngas_yield_septage": [
            r'syngas[^\d]*(\d+\.?\d*)\s*(?:mj|megajoules?)',
            r'gas\s*(?:energy|yield)[^\d]*(\d+\.?\d*)',
        ],
    }
    
    text_lower = text.lower()
    
    for param, param_patterns in patterns.items():
        for pattern in param_patterns:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    value = float(match.group(1))
                    # Convert percentages to fractions where appropriate
                    if param in ["cake_ts_fraction", "solids_capture", "char_yield_septage", "char_yield_cofeed"]:
                        if value > 1:
                            value = value / 100
                    results[param] = value
                    break
                except ValueError:
                    continue
    
    return results


def parse_vendor_response(
    vendor_id: str,
    body: str,
    attachments: List[str],
) -> Optional[ParsedSubmission]:
    """
    Parse vendor email into structured submission data.
    
    Returns None if insufficient data found.
    """
    vendor = load_vendor_details(vendor_id)
    category = vendor.get("category", "unknown")
    
    # Determine validation task
    if category == "dewatering":
        validation_task = "dewatering_params_validated"
        required_params = ["cake_ts_fraction", "solids_capture"]
    elif category == "pyrolysis":
        validation_task = "pyrolysis_yields_validated"
        required_params = ["char_yield_septage"]
    else:
        return None
    
    # Try JSON extraction first
    json_data = extract_json_from_text(body)
    
    if json_data and "results" in json_data:
        results = json_data["results"]
        evidence_type = json_data.get("evidence_type", "vendor_data")
        test_conditions = json_data.get("test_conditions", {})
        confidence = 0.9
    else:
        # Fall back to text extraction
        results = extract_tabular_data(body)
        evidence_type = "vendor_data"
        test_conditions = {}
        confidence = 0.5
    
    # Check if we have minimum required data
    has_required = any(p in results for p in required_params)
    
    if not has_required:
        return None
    
    return ParsedSubmission(
        vendor_id=vendor_id,
        validation_task=validation_task,
        evidence_type=evidence_type,
        results=results,
        test_conditions=test_conditions,
        raw_text=body,
        attachments=attachments,
        confidence=confidence,
    )


# =============================================================================
# Outlook Integration
# =============================================================================

def connect_outlook():
    """Connect to Outlook application."""
    return win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")


def get_inbox_folder(namespace):
    """Get the Inbox folder."""
    # 6 = olFolderInbox
    return namespace.GetDefaultFolder(6)


def scan_inbox_for_vendor_emails(
    hours_back: int = 168,  # 7 days
) -> List[VendorEmailMatch]:
    """
    Scan Outlook inbox for vendor responses.
    
    Args:
        hours_back: How many hours back to search
        
    Returns:
        List of matched vendor emails
    """
    namespace = connect_outlook()
    inbox = get_inbox_folder(namespace)
    
    # Filter by date
    cutoff = datetime.now() - timedelta(hours=hours_back)
    cutoff_str = cutoff.strftime("%m/%d/%Y %H:%M %p")
    
    messages = inbox.Items
    messages.Sort("[ReceivedTime]", True)  # Most recent first
    
    matches = []
    
    for msg in messages:
        try:
            received = msg.ReceivedTime
            # Convert COM datetime
            received_dt = datetime(
                received.year, received.month, received.day,
                received.hour, received.minute, received.second
            )
            
            if received_dt < cutoff:
                break  # Messages are sorted, so we're done
            
            sender_email = ""
            try:
                sender_email = msg.SenderEmailAddress
                if msg.SenderEmailType == "EX":
                    # Exchange address - try to get SMTP
                    try:
                        sender_email = msg.Sender.GetExchangeUser().PrimarySmtpAddress
                    except:
                        pass
            except:
                pass
            
            # Check if from a vendor
            vendor_id = get_vendor_id_from_email(sender_email)
            
            if vendor_id or is_vendor_response(msg.Subject, msg.Body):
                # Get attachments
                attachment_names = []
                for att in msg.Attachments:
                    attachment_names.append(att.FileName)
                
                matches.append(VendorEmailMatch(
                    subject=msg.Subject,
                    sender_email=sender_email,
                    sender_name=msg.SenderName,
                    received_time=received_dt,
                    body=msg.Body,
                    attachments=attachment_names,
                    vendor_id=vendor_id,
                    entry_id=msg.EntryID,
                ))
                
        except Exception as e:
            continue  # Skip problematic messages
    
    return matches


def save_attachments(msg_entry_id: str, target_dir: Path) -> List[Path]:
    """Save email attachments to disk."""
    namespace = connect_outlook()
    msg = namespace.GetItemFromID(msg_entry_id)
    
    saved = []
    target_dir.mkdir(parents=True, exist_ok=True)
    
    for att in msg.Attachments:
        filename = att.FileName
        # Sanitize filename
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', filename)
        target_path = target_dir / safe_name
        
        # Avoid overwrites
        counter = 1
        while target_path.exists():
            stem = target_path.stem
            suffix = target_path.suffix
            target_path = target_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        
        att.SaveAsFile(str(target_path))
        saved.append(target_path)
    
    return saved


# =============================================================================
# Processing Pipeline
# =============================================================================

def load_processed_log() -> Dict[str, Any]:
    """Load log of processed emails."""
    if PROCESSED_LOG_PATH.exists():
        with open(PROCESSED_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"processed": []}


def save_processed_log(log: Dict[str, Any]) -> None:
    """Save processed emails log."""
    PROCESSED_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROCESSED_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, default=str)


def is_already_processed(entry_id: str, log: Dict[str, Any]) -> bool:
    """Check if email was already processed."""
    return any(p.get("entry_id") == entry_id for p in log.get("processed", []))


def process_vendor_email(
    match: VendorEmailMatch,
    auto_submit: bool = False,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Process a matched vendor email.
    
    Args:
        match: The matched email
        auto_submit: If True, automatically validate and persist
        
    Returns:
        (success, message, validation_result)
    """
    if not match.vendor_id:
        return False, "Could not identify vendor from email", None
    
    # Parse the response
    parsed = parse_vendor_response(
        match.vendor_id,
        match.body,
        match.attachments,
    )
    
    if not parsed:
        return False, "Could not extract validation data from email", None
    
    # Save attachments
    attachment_dir = ATTACHMENTS_DIR / match.vendor_id / datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_attachments = []
    if match.attachments:
        try:
            saved_attachments = save_attachments(match.entry_id, attachment_dir)
        except Exception as e:
            print(f"  Warning: Could not save attachments: {e}")
    
    # Create submission
    packet_hash = get_current_packet_hash()
    
    submission = VendorSubmission(
        vendor_id=match.vendor_id,
        packet_hash=packet_hash,
        validation_task=parsed.validation_task,
        evidence_type=parsed.evidence_type,
        results=parsed.results,
        submitted_at=datetime.now(),
        raw_data=json.dumps({
            "source": "email",
            "subject": match.subject,
            "sender": match.sender_email,
            "received": match.received_time.isoformat(),
            "parse_confidence": parsed.confidence,
            "attachments": [str(p) for p in saved_attachments],
        }),
    )
    
    # Validate
    validation = validate_vendor_submission(submission)
    
    result = {
        "vendor_id": match.vendor_id,
        "validation_task": parsed.validation_task,
        "extracted_results": parsed.results,
        "parse_confidence": parsed.confidence,
        "validation_outcome": validation.outcome.value,
        "parameter_results": {k: v.value for k, v in validation.parameter_results.items()},
        "attachments_saved": [str(p) for p in saved_attachments],
    }
    
    if auto_submit:
        persist_submission(submission, validation)
        result["persisted"] = True
    
    return True, f"Extracted {len(parsed.results)} parameters, validation: {validation.outcome.value}", result


def display_email_summary(match: VendorEmailMatch) -> None:
    """Display summary of a matched email."""
    print(f"\n{'='*60}")
    print(f"FROM: {match.sender_name} <{match.sender_email}>")
    print(f"DATE: {match.received_time}")
    print(f"SUBJECT: {match.subject}")
    print(f"VENDOR ID: {match.vendor_id or 'UNKNOWN'}")
    if match.attachments:
        print(f"ATTACHMENTS: {', '.join(match.attachments)}")
    print(f"{'='*60}")
    
    # Show first 500 chars of body
    body_preview = match.body[:500].replace('\r\n', '\n').strip()
    if len(match.body) > 500:
        body_preview += "\n... [truncated]"
    print(body_preview)


def interactive_process(matches: List[VendorEmailMatch]) -> None:
    """Interactive mode for processing emails."""
    log = load_processed_log()
    
    new_matches = [m for m in matches if not is_already_processed(m.entry_id, log)]
    
    if not new_matches:
        print("No new vendor emails to process.")
        return
    
    print(f"\nFound {len(new_matches)} new vendor email(s) to process.\n")
    
    for i, match in enumerate(new_matches, 1):
        print(f"\n[{i}/{len(new_matches)}]")
        display_email_summary(match)
        
        print("\nOptions:")
        print("  [p] Process and validate")
        print("  [s] Skip (mark as ignored)")
        print("  [v] View full email body")
        print("  [q] Quit")
        
        choice = input("\nChoice: ").strip().lower()
        
        if choice == 'q':
            break
        elif choice == 'v':
            print("\n--- FULL EMAIL BODY ---")
            print(match.body)
            print("--- END ---\n")
            choice = input("Process this email? [y/n]: ").strip().lower()
            if choice != 'y':
                continue
        elif choice == 's':
            log["processed"].append({
                "entry_id": match.entry_id,
                "vendor_id": match.vendor_id,
                "subject": match.subject,
                "status": "ignored",
                "processed_at": datetime.now().isoformat(),
            })
            save_processed_log(log)
            print("  Marked as ignored.")
            continue
        elif choice != 'p':
            print("  Skipping...")
            continue
        
        # Process the email
        print("\nProcessing...")
        success, message, result = process_vendor_email(match, auto_submit=True)
        
        if success:
            print(f"  [OK] {message}")
            if result:
                print(f"\n  Validation Task: {result['validation_task']}")
                print(f"  Outcome: {result['validation_outcome']}")
                print(f"  Parameters:")
                for param, value in result['extracted_results'].items():
                    status = result['parameter_results'].get(param, 'N/A')
                    print(f"    - {param}: {value} [{status}]")
            
            log["processed"].append({
                "entry_id": match.entry_id,
                "vendor_id": match.vendor_id,
                "subject": match.subject,
                "status": "processed",
                "validation_outcome": result['validation_outcome'] if result else None,
                "processed_at": datetime.now().isoformat(),
            })
        else:
            print(f"  [FAIL] {message}")
            log["processed"].append({
                "entry_id": match.entry_id,
                "vendor_id": match.vendor_id,
                "subject": match.subject,
                "status": "error",
                "error": message,
                "processed_at": datetime.now().isoformat(),
            })
        
        save_processed_log(log)


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    import argparse
    import time
    
    parser = argparse.ArgumentParser(description="Monitor inbox for vendor responses")
    parser.add_argument("--watch", action="store_true", help="Watch mode - poll periodically")
    parser.add_argument("--interval", type=int, default=30, help="Polling interval in minutes (default: 30)")
    parser.add_argument("--hours", type=int, default=168, help="Hours back to search (default: 168 = 7 days)")
    parser.add_argument("--auto", action="store_true", help="Auto-process without prompts")
    args = parser.parse_args()
    
    print("Vendor Inbox Monitor")
    print("=" * 40)
    print(f"Packet Hash: {get_current_packet_hash()}")
    print(f"Searching last {args.hours} hours")
    print()
    
    if args.watch:
        print(f"Watch mode enabled - polling every {args.interval} minutes (Ctrl+C to stop)\n")
        while True:
            try:
                matches = scan_inbox_for_vendor_emails(hours_back=args.hours)
                log = load_processed_log()
                new_matches = [m for m in matches if not is_already_processed(m.entry_id, log)]
                
                if new_matches:
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Found {len(new_matches)} new email(s)")
                    for match in new_matches:
                        if args.auto:
                            success, message, result = process_vendor_email(match, auto_submit=True)
                            print(f"  {match.vendor_id}: {message}")
                        else:
                            print(f"  From: {match.sender_email}")
                            print(f"  Subject: {match.subject}")
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] No new vendor emails")
                
                time.sleep(args.interval * 60)  # Convert minutes to seconds
                
            except KeyboardInterrupt:
                print("\nStopping watch mode.")
                break
    else:
        # Single scan
        print("Scanning inbox...")
        matches = scan_inbox_for_vendor_emails(hours_back=args.hours)
        
        print(f"Found {len(matches)} potential vendor email(s)")
        
        if matches:
            if args.auto:
                log = load_processed_log()
                for match in matches:
                    if not is_already_processed(match.entry_id, log):
                        success, message, result = process_vendor_email(match, auto_submit=True)
                        print(f"  {match.vendor_id or 'UNKNOWN'}: {message}")
                        log["processed"].append({
                            "entry_id": match.entry_id,
                            "vendor_id": match.vendor_id,
                            "status": "processed" if success else "error",
                            "processed_at": datetime.now().isoformat(),
                        })
                save_processed_log(log)
            else:
                interactive_process(matches)


if __name__ == "__main__":
    main()
