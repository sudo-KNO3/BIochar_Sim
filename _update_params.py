"""Script to add DeploymentMode and DeploymentParams to parameters.py"""

with open('septage_model/core/parameters.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add DeploymentMode enum after CharQualityTier
deployment_enum = '''


class DeploymentMode(Enum):
    """Deployment configuration for Option B system."""
    PRODUCT = "product"           # Owner-operated, labor externalized, 0.6x CAPEX
    REGIONAL_HUB = "regional_hub" # Staffed facility, full CAPEX, labor factor 0.7


@dataclass(frozen=True)
class DeploymentParams:
    """
    Deployment-specific parameters for Option B.
    
    Product Mode: Owner-operated asset for rural waste handlers
        - Labor externalized (owner's time not costed)
        - Smaller scale, modular equipment
        - Buyer economics framing (savings vs dumping fees)
    
    Regional Hub Mode: Centralized staffed facility
        - Professional operations, labor factor 0.7
        - Full-scale equipment
        - Facility NOI framing
    """
    mode: DeploymentMode = DeploymentMode.PRODUCT
    
    # Scale parameters
    annual_septage_m3: float = 2000.0      # Product: 2000, Hub: 5000
    annual_cofeed_tds: float = 600.0       # Product: 600, Hub: 1200
    
    # Economic parameters
    labor_factor: float = 0.0              # Product: 0.0 (externalized), Hub: 0.7
    capex_multiplier: float = 0.6          # Product: 0.6, Hub: 1.0
    capex_validated: bool = False          # Flag: CAPEX estimate requires vendor validation
    
    # Buyer economics (Product mode)
    reference_dumping_fee: float = 55.0    # $/m3 - what buyer currently pays
    owner_hours_per_week: float = 5.0      # Estimated operator time commitment
    
    @classmethod
    def product_default(cls) -> 'DeploymentParams':
        return cls(
            mode=DeploymentMode.PRODUCT,
            annual_septage_m3=2000.0,
            annual_cofeed_tds=600.0,
            labor_factor=0.0,
            capex_multiplier=0.6,
        )
    
    @classmethod
    def hub_default(cls) -> 'DeploymentParams':
        return cls(
            mode=DeploymentMode.REGIONAL_HUB,
            annual_septage_m3=5000.0,
            annual_cofeed_tds=1200.0,
            labor_factor=0.7,
            capex_multiplier=1.0,
        )

'''

# Insert after CharQualityTier
old_marker = '''class CharQualityTier(Enum):
    """Biochar quality/market tiers."""
    TIER_1_PREMIUM = 1    # IBI-certified, low metals, $500/t
    TIER_2_BULK = 2       # Bulk soil amendment, $225/t
    TIER_3_LOW_VALUE = 3  # Landfill cover/restricted, $75/t'''

content = content.replace(old_marker, old_marker + deployment_enum)

# 2. Add deployment field to ModelParameters
old_regulatory = '    regulatory: RegulatoryParams = field(default_factory=RegulatoryParams)'
new_regulatory = '''    regulatory: RegulatoryParams = field(default_factory=RegulatoryParams)
    deployment: DeploymentParams = field(default_factory=DeploymentParams)'''

content = content.replace(old_regulatory, new_regulatory)

with open('septage_model/core/parameters.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Added DeploymentMode enum and DeploymentParams to parameters.py')
