"""
Artifact Versioning Module.

Provides version tracking for design artifacts:
    - FMEA documents
    - DRL assessments
    - Gate reports
    - Parameter snapshots

Version format: {artifact_type}_v{major}.{minor}.{patch}_{hash}

Features:
    - Deterministic hashing for reproducibility
    - Semantic versioning with auto-increment
    - Audit trail for regulatory review
    - Diff capability between versions
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from datetime import datetime
from enum import Enum
import json
import hashlib


class ArtifactType(Enum):
    """Types of versioned artifacts."""
    FMEA = "fmea"
    DRL_ASSESSMENT = "drl"
    GATE_REPORT = "gate"
    PARAMETER_SET = "params"
    SIMULATION_RESULT = "sim"
    DOCUMENTATION = "docs"


@dataclass
class SemanticVersion:
    """
    Semantic versioning with comparison support.
    
    Format: major.minor.patch
    - major: Breaking changes
    - minor: New features, backward compatible
    - patch: Bug fixes
    """
    major: int = 0
    minor: int = 0
    patch: int = 0
    
    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"
    
    def __lt__(self, other: 'SemanticVersion') -> bool:
        return self.as_tuple() < other.as_tuple()
    
    def __le__(self, other: 'SemanticVersion') -> bool:
        return self.as_tuple() <= other.as_tuple()
    
    def __gt__(self, other: 'SemanticVersion') -> bool:
        return self.as_tuple() > other.as_tuple()
    
    def __ge__(self, other: 'SemanticVersion') -> bool:
        return self.as_tuple() >= other.as_tuple()
    
    def as_tuple(self) -> Tuple[int, int, int]:
        return (self.major, self.minor, self.patch)
    
    def increment_major(self) -> 'SemanticVersion':
        """Increment major version, reset minor and patch."""
        return SemanticVersion(self.major + 1, 0, 0)
    
    def increment_minor(self) -> 'SemanticVersion':
        """Increment minor version, reset patch."""
        return SemanticVersion(self.major, self.minor + 1, 0)
    
    def increment_patch(self) -> 'SemanticVersion':
        """Increment patch version."""
        return SemanticVersion(self.major, self.minor, self.patch + 1)
    
    @classmethod
    def parse(cls, version_str: str) -> 'SemanticVersion':
        """Parse version from string like '1.2.3'."""
        parts = version_str.split('.')
        if len(parts) != 3:
            raise ValueError(f"Invalid version format: {version_str}")
        return cls(int(parts[0]), int(parts[1]), int(parts[2]))


@dataclass
class ArtifactVersion:
    """
    A versioned artifact with metadata.
    
    Attributes:
        artifact_type: Type of artifact
        version: Semantic version
        content_hash: SHA-256 hash of content (first 12 chars)
        created_at: When this version was created
        created_by: Who/what created this version
        description: Human-readable description of changes
        content: The actual artifact content (serializable)
        parent_hash: Hash of previous version (for chain verification)
    """
    artifact_type: ArtifactType
    version: SemanticVersion
    content_hash: str
    created_at: datetime
    created_by: str = "automated"
    description: str = ""
    content: Optional[Dict[str, Any]] = None
    parent_hash: Optional[str] = None
    
    @property
    def version_id(self) -> str:
        """Full version identifier."""
        return f"{self.artifact_type.value}_v{self.version}_{self.content_hash}"
    
    @property
    def short_id(self) -> str:
        """Short version identifier."""
        return f"{self.artifact_type.value}_v{self.version}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "artifact_type": self.artifact_type.value,
            "version": str(self.version),
            "content_hash": self.content_hash,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "description": self.description,
            "content": self.content,
            "parent_hash": self.parent_hash,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ArtifactVersion':
        """Deserialize from dictionary."""
        return cls(
            artifact_type=ArtifactType(data["artifact_type"]),
            version=SemanticVersion.parse(data["version"]),
            content_hash=data["content_hash"],
            created_at=datetime.fromisoformat(data["created_at"]),
            created_by=data.get("created_by", "unknown"),
            description=data.get("description", ""),
            content=data.get("content"),
            parent_hash=data.get("parent_hash"),
        )


# =============================================================================
# Hashing Functions
# =============================================================================

def compute_content_hash(content: Any, truncate: int = 12) -> str:
    """
    Compute deterministic hash of content.
    
    Args:
        content: Any JSON-serializable content
        truncate: Number of characters to return (default 12)
    
    Returns:
        Truncated SHA-256 hash string
    """
    # Serialize with sorted keys for deterministic ordering
    serialized = json.dumps(content, sort_keys=True, default=str)
    full_hash = hashlib.sha256(serialized.encode()).hexdigest()
    return full_hash[:truncate]


def verify_content_hash(content: Any, expected_hash: str) -> bool:
    """
    Verify content matches expected hash.
    
    Args:
        content: Content to verify
        expected_hash: Expected hash value
    
    Returns:
        True if hash matches
    """
    actual_hash = compute_content_hash(content, len(expected_hash))
    return actual_hash == expected_hash


# =============================================================================
# Version Registry
# =============================================================================

@dataclass
class VersionRegistry:
    """
    Registry of all artifact versions.
    
    Maintains version history and provides:
    - Version lookup
    - History traversal
    - Diff between versions
    """
    versions: Dict[str, ArtifactVersion] = field(default_factory=dict)
    latest: Dict[str, str] = field(default_factory=dict)  # artifact_type -> version_id
    
    def register(self, artifact: ArtifactVersion) -> None:
        """
        Register a new artifact version.
        
        Args:
            artifact: ArtifactVersion to register
        """
        self.versions[artifact.version_id] = artifact
        
        # Update latest if this is newer
        type_key = artifact.artifact_type.value
        if type_key not in self.latest:
            self.latest[type_key] = artifact.version_id
        else:
            current = self.versions[self.latest[type_key]]
            if artifact.version > current.version:
                self.latest[type_key] = artifact.version_id
    
    def get(self, version_id: str) -> Optional[ArtifactVersion]:
        """Get artifact by version ID."""
        return self.versions.get(version_id)
    
    def get_latest(self, artifact_type: ArtifactType) -> Optional[ArtifactVersion]:
        """Get latest version of an artifact type."""
        version_id = self.latest.get(artifact_type.value)
        if version_id:
            return self.versions.get(version_id)
        return None
    
    def get_history(self, artifact_type: ArtifactType) -> List[ArtifactVersion]:
        """Get all versions of an artifact type, oldest first."""
        versions = [
            v for v in self.versions.values() 
            if v.artifact_type == artifact_type
        ]
        return sorted(versions, key=lambda v: v.version.as_tuple())
    
    def save(self, path: Path) -> None:
        """Save registry to JSON file."""
        data = {
            "versions": {k: v.to_dict() for k, v in self.versions.items()},
            "latest": self.latest,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, path: Path) -> 'VersionRegistry':
        """Load registry from JSON file."""
        if not path.exists():
            return cls()
        
        with open(path, 'r') as f:
            data = json.load(f)
        
        registry = cls()
        for version_id, version_data in data.get("versions", {}).items():
            registry.versions[version_id] = ArtifactVersion.from_dict(version_data)
        registry.latest = data.get("latest", {})
        
        return registry


# =============================================================================
# Versioning Operations
# =============================================================================

def create_artifact_version(
    artifact_type: ArtifactType,
    content: Dict[str, Any],
    registry: Optional[VersionRegistry] = None,
    version_bump: str = "patch",
    description: str = "",
    created_by: str = "automated"
) -> ArtifactVersion:
    """
    Create a new versioned artifact.
    
    Args:
        artifact_type: Type of artifact
        content: Serializable content
        registry: Optional registry for version tracking
        version_bump: 'major', 'minor', or 'patch'
        description: Human-readable description
        created_by: Creator identifier
    
    Returns:
        New ArtifactVersion
    """
    content_hash = compute_content_hash(content)
    
    # Determine version number
    if registry:
        latest = registry.get_latest(artifact_type)
        if latest:
            if version_bump == "major":
                version = latest.version.increment_major()
            elif version_bump == "minor":
                version = latest.version.increment_minor()
            else:
                version = latest.version.increment_patch()
            parent_hash = latest.content_hash
        else:
            version = SemanticVersion(1, 0, 0)
            parent_hash = None
    else:
        version = SemanticVersion(1, 0, 0)
        parent_hash = None
    
    artifact = ArtifactVersion(
        artifact_type=artifact_type,
        version=version,
        content_hash=content_hash,
        created_at=datetime.now(),
        created_by=created_by,
        description=description,
        content=content,
        parent_hash=parent_hash,
    )
    
    if registry:
        registry.register(artifact)
    
    return artifact


def diff_artifacts(
    old: ArtifactVersion,
    new: ArtifactVersion
) -> Dict[str, Any]:
    """
    Compute difference between two artifact versions.
    
    Args:
        old: Previous version
        new: Current version
    
    Returns:
        Dictionary of differences
    """
    if old.artifact_type != new.artifact_type:
        return {"error": "Cannot diff different artifact types"}
    
    if old.content is None or new.content is None:
        return {"error": "Content not available for diff"}
    
    added = {}
    removed = {}
    changed = {}
    
    old_keys = set(old.content.keys())
    new_keys = set(new.content.keys())
    
    for key in new_keys - old_keys:
        added[key] = new.content[key]
    
    for key in old_keys - new_keys:
        removed[key] = old.content[key]
    
    for key in old_keys & new_keys:
        if old.content[key] != new.content[key]:
            changed[key] = {
                "old": old.content[key],
                "new": new.content[key],
            }
    
    return {
        "from_version": str(old.version),
        "to_version": str(new.version),
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged_count": len(old_keys & new_keys) - len(changed),
    }


# =============================================================================
# Convenience Functions for Specific Artifact Types
# =============================================================================

def version_gate_report(
    gate_report,
    registry: Optional[VersionRegistry] = None,
    description: str = ""
) -> ArtifactVersion:
    """
    Create versioned artifact from gate report.
    
    Args:
        gate_report: GateReport from run_design_gates()
        registry: Optional version registry
        description: Description of this version
    
    Returns:
        ArtifactVersion for the gate report
    """
    content = {
        "all_passed": gate_report.all_passed,
        "gates": [
            {
                "name": g.name,
                "passed": g.passed,
                "value": g.value,
                "threshold": g.threshold,
            }
            for g in gate_report.gates
        ],
    }
    
    return create_artifact_version(
        artifact_type=ArtifactType.GATE_REPORT,
        content=content,
        registry=registry,
        description=description,
    )


def version_fmea(
    fmea_analysis,
    registry: Optional[VersionRegistry] = None,
    description: str = ""
) -> ArtifactVersion:
    """
    Create versioned artifact from FMEA analysis.
    
    Args:
        fmea_analysis: FMEAAnalysis from analyze_fmea()
        registry: Optional version registry
        description: Description of this version
    
    Returns:
        ArtifactVersion for the FMEA
    """
    content = {
        "critical_count": fmea_analysis.critical_count,
        "moderate_count": fmea_analysis.moderate_count,
        "acceptable_count": fmea_analysis.acceptable_count,
        "total_rpn": fmea_analysis.total_rpn,
        "avg_rpn": fmea_analysis.avg_rpn,
        "owner_serviceable_pct": fmea_analysis.owner_serviceable_pct,
        "failure_modes": [m.to_dict() for m in fmea_analysis.failure_modes],
    }
    
    return create_artifact_version(
        artifact_type=ArtifactType.FMEA,
        content=content,
        registry=registry,
        description=description,
    )


def version_drl_assessment(
    assessment,
    registry: Optional[VersionRegistry] = None,
    description: str = ""
) -> ArtifactVersion:
    """
    Create versioned artifact from DRL assessment.
    
    Args:
        assessment: DRLAssessment from evaluate_drl()
        registry: Optional version registry
        description: Description of this version
    
    Returns:
        ArtifactVersion for the DRL assessment
    """
    content = assessment.to_dict()
    
    return create_artifact_version(
        artifact_type=ArtifactType.DRL_ASSESSMENT,
        content=content,
        registry=registry,
        description=description,
    )


def version_parameters(
    params,
    registry: Optional[VersionRegistry] = None,
    description: str = ""
) -> ArtifactVersion:
    """
    Create versioned artifact from model parameters.
    
    Args:
        params: ModelParameters from create_baseline_parameters()
        registry: Optional version registry
        description: Description of this version
    
    Returns:
        ArtifactVersion for the parameters
    """
    # Convert dataclass to dict if possible
    if hasattr(params, '__dict__'):
        content = {k: v for k, v in params.__dict__.items() if not k.startswith('_')}
    elif hasattr(params, 'to_dict'):
        content = params.to_dict()
    else:
        content = {"params": str(params)}
    
    return create_artifact_version(
        artifact_type=ArtifactType.PARAMETER_SET,
        content=content,
        registry=registry,
        description=description,
    )


# =============================================================================
# Default Registry Path
# =============================================================================

def get_default_registry_path() -> Path:
    """Get default path for version registry."""
    return Path(__file__).parent.parent.parent / ".versions" / "registry.json"


def get_or_create_registry() -> VersionRegistry:
    """Get existing registry or create new one."""
    path = get_default_registry_path()
    return VersionRegistry.load(path)


def save_registry(registry: VersionRegistry) -> None:
    """Save registry to default path."""
    path = get_default_registry_path()
    registry.save(path)
