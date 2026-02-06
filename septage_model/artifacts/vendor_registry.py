"""
Vendor Registry - Canonical source of vendor identity.

Provides:
    - Stable vendor identity (vendor_id is immutable)
    - Legal name for display (may change)
    - Slug for filesystem-safe paths
    - Vendor status tracking (active/deprecated/rejected)

Rules:
    - All submissions must reference an existing vendor_id
    - No implicit vendor creation from submissions
    - vendor_id is the only stable identity
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum
from pathlib import Path
import json
import re


class VendorStatus(Enum):
    """Status of vendor in system."""
    ACTIVE = "active"               # Currently being evaluated
    DEPRECATED = "deprecated"       # No longer primary, but data preserved
    REJECTED = "rejected"           # Did not meet criteria
    QUALIFIED = "qualified"         # Passed validation, approved for use


class VendorCategory(Enum):
    """Category of vendor equipment."""
    DEWATERING = "dewatering"
    PYROLYSIS = "pyrolysis"
    DRYING = "drying"
    CHAR_HANDLING = "char_handling"
    CONTROLS = "controls"
    INTEGRATION = "integration"


def slugify(name: str) -> str:
    """
    Convert legal name to filesystem-safe slug.
    
    Examples:
        "Vendor X Corporation" -> "vendor_x_corporation"
        "PyroTech Labs, Inc." -> "pyrotech_labs_inc"
    """
    # Lowercase
    slug = name.lower()
    # Replace common business suffixes punctuation
    slug = slug.replace(",", "").replace(".", "")
    # Replace spaces and special chars with underscore
    slug = re.sub(r'[^a-z0-9]+', '_', slug)
    # Remove leading/trailing underscores
    slug = slug.strip('_')
    # Collapse multiple underscores
    slug = re.sub(r'_+', '_', slug)
    return slug


@dataclass
class Vendor:
    """
    Vendor identity record.
    
    Attributes:
        vendor_id: Immutable primary key (e.g., "dew_001")
        legal_name: Display name (may change)
        slug: Filesystem-safe token (derived from legal_name)
        category: Equipment category
        status: Current status in system
        contact_email: Primary contact email
        notes: Additional notes
        registered_at: When vendor was added to registry
    """
    vendor_id: str
    legal_name: str
    slug: str
    category: VendorCategory
    status: VendorStatus = VendorStatus.ACTIVE
    contact_email: str = ""
    notes: str = ""
    registered_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "vendor_id": self.vendor_id,
            "legal_name": self.legal_name,
            "slug": self.slug,
            "category": self.category.value,
            "status": self.status.value,
            "contact_email": self.contact_email,
            "notes": self.notes,
            "registered_at": self.registered_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Vendor':
        return cls(
            vendor_id=data["vendor_id"],
            legal_name=data["legal_name"],
            slug=data["slug"],
            category=VendorCategory(data["category"]),
            status=VendorStatus(data.get("status", "active")),
            contact_email=data.get("contact_email", ""),
            notes=data.get("notes", ""),
            registered_at=datetime.fromisoformat(data["registered_at"]) 
                if "registered_at" in data else datetime.now(),
        )


class VendorRegistry:
    """
    Registry of all known vendors.
    
    This is the canonical source of vendor identity.
    All submissions must reference a vendor_id from this registry.
    """
    
    def __init__(self, path: Optional[Path] = None):
        self.path = path or get_default_vendor_registry_path()
        self.vendors: Dict[str, Vendor] = {}
        self._meta: Dict[str, Any] = {}
    
    def get(self, vendor_id: str) -> Optional[Vendor]:
        """Get vendor by ID. Returns None if not found."""
        return self.vendors.get(vendor_id)
    
    def require(self, vendor_id: str) -> Vendor:
        """Get vendor by ID. Raises KeyError if not found."""
        vendor = self.vendors.get(vendor_id)
        if vendor is None:
            raise KeyError(
                f"Unknown vendor_id: '{vendor_id}'. "
                f"Register vendor first with register_vendor(). "
                f"Known vendors: {list(self.vendors.keys())}"
            )
        return vendor
    
    def register(
        self,
        vendor_id: str,
        legal_name: str,
        category: VendorCategory,
        contact_email: str = "",
        notes: str = "",
    ) -> Vendor:
        """
        Register a new vendor.
        
        Args:
            vendor_id: Unique identifier (e.g., "dew_001")
            legal_name: Legal/display name
            category: Equipment category
            contact_email: Primary contact
            notes: Additional notes
        
        Returns:
            Created Vendor object
        
        Raises:
            ValueError: If vendor_id already exists
        """
        if vendor_id in self.vendors:
            raise ValueError(
                f"Vendor '{vendor_id}' already exists. "
                f"Use update() to modify existing vendors."
            )
        
        vendor = Vendor(
            vendor_id=vendor_id,
            legal_name=legal_name,
            slug=slugify(legal_name),
            category=category,
            status=VendorStatus.ACTIVE,
            contact_email=contact_email,
            notes=notes,
            registered_at=datetime.now(),
        )
        
        self.vendors[vendor_id] = vendor
        self.save()
        return vendor
    
    def update_status(
        self, 
        vendor_id: str, 
        status: VendorStatus,
        notes: str = ""
    ) -> Vendor:
        """Update vendor status."""
        vendor = self.require(vendor_id)
        vendor = Vendor(
            vendor_id=vendor.vendor_id,
            legal_name=vendor.legal_name,
            slug=vendor.slug,
            category=vendor.category,
            status=status,
            contact_email=vendor.contact_email,
            notes=notes if notes else vendor.notes,
            registered_at=vendor.registered_at,
        )
        self.vendors[vendor_id] = vendor
        self.save()
        return vendor
    
    def list_by_category(self, category: VendorCategory) -> List[Vendor]:
        """Get all vendors in a category."""
        return [v for v in self.vendors.values() if v.category == category]
    
    def list_by_status(self, status: VendorStatus) -> List[Vendor]:
        """Get all vendors with a status."""
        return [v for v in self.vendors.values() if v.status == status]
    
    def list_active(self) -> List[Vendor]:
        """Get all active vendors."""
        return self.list_by_status(VendorStatus.ACTIVE)
    
    def save(self) -> None:
        """Save registry to JSON file."""
        data = {
            "_meta": self._meta or {
                "description": "Canonical vendor registry - DO NOT define vendors ad-hoc",
                "rules": [
                    "vendor_id is immutable primary key",
                    "legal_name may change (display only)",
                    "slug derived from legal_name, used for filenames",
                    "All submissions must reference existing vendor_id"
                ]
            }
        }
        for vendor_id, vendor in self.vendors.items():
            data[vendor_id] = vendor.to_dict()
        
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, path: Optional[Path] = None) -> 'VendorRegistry':
        """Load registry from JSON file."""
        registry = cls(path)
        
        if not registry.path.exists():
            return registry
        
        with open(registry.path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        registry._meta = data.pop("_meta", {})
        
        for vendor_id, vendor_data in data.items():
            if isinstance(vendor_data, dict) and "vendor_id" in vendor_data:
                registry.vendors[vendor_id] = Vendor.from_dict(vendor_data)
        
        return registry
    
    def to_summary(self) -> str:
        """Generate summary of registered vendors."""
        lines = [
            "=" * 60,
            "VENDOR REGISTRY",
            "=" * 60,
            "",
        ]
        
        if not self.vendors:
            lines.append("  No vendors registered.")
            lines.append("")
            lines.append("  Use register_vendor() to add vendors.")
        else:
            for category in VendorCategory:
                vendors = self.list_by_category(category)
                if vendors:
                    lines.append(f"{category.value.upper()}:")
                    for v in vendors:
                        status_icon = {
                            VendorStatus.ACTIVE: "🔵",
                            VendorStatus.DEPRECATED: "⚪",
                            VendorStatus.REJECTED: "🔴",
                            VendorStatus.QUALIFIED: "🟢",
                        }.get(v.status, "?")
                        lines.append(f"  {status_icon} {v.vendor_id}: {v.legal_name}")
                    lines.append("")
        
        lines.append("=" * 60)
        return "\n".join(lines)


# =============================================================================
# Module-level functions
# =============================================================================

def get_default_vendor_registry_path() -> Path:
    """Get default path for vendor registry."""
    return Path(__file__).parent.parent.parent / "docs" / "vendor" / "vendors.json"


def get_vendor_registry() -> VendorRegistry:
    """Get or create vendor registry."""
    return VendorRegistry.load()


def register_vendor(
    vendor_id: str,
    legal_name: str,
    category: VendorCategory,
    contact_email: str = "",
    notes: str = "",
) -> Vendor:
    """
    Register a new vendor in the canonical registry.
    
    This is the only way to add vendors to the system.
    
    Args:
        vendor_id: Unique identifier (e.g., "dew_001", "pyr_001")
        legal_name: Legal/display name
        category: Equipment category (VendorCategory enum)
        contact_email: Primary contact email
        notes: Additional notes
    
    Returns:
        Created Vendor object
    
    Example:
        >>> register_vendor(
        ...     vendor_id="dew_001",
        ...     legal_name="Dewatering Systems Inc.",
        ...     category=VendorCategory.DEWATERING,
        ...     contact_email="sales@dewsys.com"
        ... )
    """
    registry = get_vendor_registry()
    return registry.register(
        vendor_id=vendor_id,
        legal_name=legal_name,
        category=category,
        contact_email=contact_email,
        notes=notes,
    )


def get_vendor(vendor_id: str) -> Vendor:
    """
    Get vendor by ID.
    
    Raises:
        KeyError: If vendor not found
    """
    registry = get_vendor_registry()
    return registry.require(vendor_id)


def print_vendor_registry() -> None:
    """Print current vendor registry to console."""
    registry = get_vendor_registry()
    print(registry.to_summary())
