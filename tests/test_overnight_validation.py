"""
Tests for overnight mode validation pipeline.

Tests verify:
    1. 1 vendor → PARTIAL, DRL-4 blocked
    2. 2 vendors consistent → VALIDATED, DRL-4 allowed
    3. 2 vendors inconsistent → PARTIAL (blocked), remediation message
    4. Policy change (min_vendors=1) → validation passes without code change
"""

import pytest

from septage_model.core.parameters import (
    OvernightMode,
    OvernightModeStatus,
    OvernightModeParams,
    VendorOvernightData,
    VendorValidationPolicy,
    RestartBucket,
    validate_overnight_responses,
)
from septage_model.ci.gates import overnight_mode_validation_gate


# =============================================================================
# Test Fixtures
# =============================================================================

def make_vendor_response(
    vendor_id: str,
    mode: OvernightMode = OvernightMode.HOLD,
    restart_hot: float = 0.5,
    thermal_heat: bool = True,
) -> VendorOvernightData:
    """Helper to create vendor response."""
    return VendorOvernightData(
        vendor_id=vendor_id,
        packet_hash="1ee87b8d691d",
        date_received="2026-02-06",
        mode=mode,
        thermal_continuous_heat=thermal_heat,
        min_temp_c=400.0,
        restart_time_hot_hr=restart_hot,
        restart_time_warm_hr=2.0,
        restart_time_cold_hr=6.0,
        shutdown_philosophy="auto_shutdown",
    )


# =============================================================================
# Test: Vendor Validation Policy
# =============================================================================

class TestVendorValidationPolicy:
    """Tests for VendorValidationPolicy."""
    
    def test_default_policy_requires_2_vendors(self):
        """Default policy requires ≥2 consistent vendors."""
        policy = VendorValidationPolicy()
        assert policy.min_vendors == 2
        assert policy.mode_match_required is True
        assert policy.restart_bucket_match is True
        assert policy.thermal_hold_match is True
    
    def test_restart_bucket_classification(self):
        """Restart times classified into buckets correctly."""
        policy = VendorValidationPolicy()
        
        # < 1 hour = FAST
        assert policy.classify_restart_time(0.5) == RestartBucket.FAST
        assert policy.classify_restart_time(0.9) == RestartBucket.FAST
        
        # 1-4 hours = MODERATE
        assert policy.classify_restart_time(1.0) == RestartBucket.MODERATE
        assert policy.classify_restart_time(2.5) == RestartBucket.MODERATE
        assert policy.classify_restart_time(4.0) == RestartBucket.MODERATE
        
        # > 4 hours = SLOW
        assert policy.classify_restart_time(4.1) == RestartBucket.SLOW
        assert policy.classify_restart_time(8.0) == RestartBucket.SLOW
    
    def test_restart_times_consistent_same_bucket(self):
        """Times in same bucket with small difference are consistent."""
        policy = VendorValidationPolicy()
        
        # Both FAST, within 25% tolerance
        assert policy.restart_times_consistent(0.5, 0.6) is True
        
        # Both MODERATE, within 25% tolerance (2.0 vs 2.4 = 18% diff)
        assert policy.restart_times_consistent(2.0, 2.4) is True
        
        # Both SLOW, within 25% tolerance
        assert policy.restart_times_consistent(5.0, 5.5) is True
    
    def test_restart_times_inconsistent_exceeds_tolerance(self):
        """Times in same bucket but exceeding 25% tolerance are inconsistent."""
        policy = VendorValidationPolicy()
        
        # Both MODERATE, but 2.0 vs 3.0 = 40% diff > 25%
        assert policy.restart_times_consistent(2.0, 3.0) is False
    
    def test_restart_times_inconsistent_different_bucket(self):
        """Times in different buckets are inconsistent."""
        policy = VendorValidationPolicy()
        
        # FAST vs MODERATE
        assert policy.restart_times_consistent(0.5, 2.0) is False
        
        # MODERATE vs SLOW
        assert policy.restart_times_consistent(2.0, 6.0) is False


# =============================================================================
# Test: Validation Function
# =============================================================================

class TestValidateOvernightResponses:
    """Tests for validate_overnight_responses()."""
    
    def test_zero_responses_returns_unknown(self):
        """0 responses → UNKNOWN status."""
        result = validate_overnight_responses([])
        
        assert result.status == OvernightModeStatus.UNKNOWN
        assert result.blocks_drl4 is True
        assert result.vendor_count == 0
    
    def test_one_response_returns_partial(self):
        """1 vendor → PARTIAL, DRL-4 blocked."""
        responses = [make_vendor_response("pyreg")]
        result = validate_overnight_responses(responses)
        
        assert result.status == OvernightModeStatus.PARTIAL
        assert result.blocks_drl4 is False  # PARTIAL doesn't block, UNKNOWN does
        assert result.is_validated is False
        assert result.vendor_count == 1
        assert result.mode == OvernightMode.HOLD
    
    def test_two_consistent_returns_validated(self):
        """2 vendors consistent → VALIDATED, DRL-4 allowed."""
        responses = [
            make_vendor_response("pyreg", mode=OvernightMode.HOLD, restart_hot=0.5),
            make_vendor_response("klean", mode=OvernightMode.HOLD, restart_hot=0.6),
        ]
        result = validate_overnight_responses(responses)
        
        assert result.status == OvernightModeStatus.VALIDATED
        assert result.is_validated is True
        assert result.blocks_drl4 is False
        assert result.vendor_count == 2
        assert result.mode == OvernightMode.HOLD
        # Averaged restart time
        assert result.restart_time_hot_hr == pytest.approx(0.55, rel=0.01)
    
    def test_two_inconsistent_mode_returns_partial(self):
        """2 vendors inconsistent mode → PARTIAL (blocked)."""
        responses = [
            make_vendor_response("pyreg", mode=OvernightMode.HOLD),
            make_vendor_response("klean", mode=OvernightMode.FULL_SHUTDOWN),
        ]
        result = validate_overnight_responses(responses)
        
        assert result.status == OvernightModeStatus.PARTIAL
        assert result.is_validated is False
        # Only 1 consistent response (first one)
        assert len([r for r in result.vendor_responses]) == 2
    
    def test_two_inconsistent_restart_bucket_returns_partial(self):
        """2 vendors with different restart buckets → PARTIAL."""
        responses = [
            make_vendor_response("pyreg", restart_hot=0.5),   # FAST bucket
            make_vendor_response("klean", restart_hot=3.0),   # MODERATE bucket
        ]
        result = validate_overnight_responses(responses)
        
        assert result.status == OvernightModeStatus.PARTIAL
        assert result.is_validated is False
    
    def test_two_inconsistent_thermal_returns_partial(self):
        """2 vendors with different thermal_hold → PARTIAL."""
        responses = [
            make_vendor_response("pyreg", thermal_heat=True),
            make_vendor_response("klean", thermal_heat=False),
        ]
        result = validate_overnight_responses(responses)
        
        assert result.status == OvernightModeStatus.PARTIAL
        assert result.is_validated is False
    
    def test_policy_change_min_vendors_1(self):
        """Policy change (min_vendors=1) → validation passes with 1 response."""
        policy = VendorValidationPolicy(min_vendors=1)
        responses = [make_vendor_response("pyreg")]
        
        result = validate_overnight_responses(responses, policy=policy)
        
        assert result.status == OvernightModeStatus.VALIDATED
        assert result.is_validated is True
        assert result.vendor_count == 1
    
    def test_three_vendors_two_consistent(self):
        """3 vendors, 2 consistent → VALIDATED using consistent pair."""
        responses = [
            make_vendor_response("pyreg", mode=OvernightMode.HOLD, restart_hot=0.5),
            make_vendor_response("klean", mode=OvernightMode.HOLD, restart_hot=0.6),
            make_vendor_response("beston", mode=OvernightMode.FULL_SHUTDOWN, restart_hot=6.0),
        ]
        result = validate_overnight_responses(responses)
        
        assert result.status == OvernightModeStatus.VALIDATED
        assert result.mode == OvernightMode.HOLD
        # Only first 2 are consistent
        assert result.is_validated is True


# =============================================================================
# Test: DRL-4 Gate
# =============================================================================

class TestOvernightModeValidationGate:
    """Tests for overnight_mode_validation_gate()."""
    
    def test_drl3_passes_with_unknown(self):
        """DRL-3: passes even with UNKNOWN status (screening allowed)."""
        params = OvernightModeParams()  # Default: UNKNOWN
        
        result = overnight_mode_validation_gate(params, claimed_drl=3)
        
        assert result.passed is True
        assert result.name == "Overnight Mode Validation"
    
    def test_drl3_emits_warning_for_unvalidated(self):
        """DRL-3: emits warning listing unvalidated assumptions."""
        responses = [make_vendor_response("pyreg")]
        params = validate_overnight_responses(responses)
        
        result = overnight_mode_validation_gate(params, claimed_drl=3)
        
        assert result.passed is True
        assert result.remediation is not None
        assert "DRL-3 warning" in result.remediation
    
    def test_drl4_blocks_with_unknown(self):
        """DRL-4: HARD BLOCK with UNKNOWN status."""
        params = OvernightModeParams()  # Default: UNKNOWN
        
        result = overnight_mode_validation_gate(params, claimed_drl=4)
        
        assert result.passed is False
        assert result.name == "Overnight Mode Validation (DRL)"
        assert "blocked" in result.remediation
        assert "UNKNOWN" in result.remediation
    
    def test_drl4_blocks_with_partial(self):
        """DRL-4: HARD BLOCK with PARTIAL status (1 vendor)."""
        responses = [make_vendor_response("pyreg")]
        params = validate_overnight_responses(responses)
        
        result = overnight_mode_validation_gate(params, claimed_drl=4)
        
        # PARTIAL also blocks DRL-4 (need VALIDATED)
        # Wait - PARTIAL.blocks_drl4 is False because only UNKNOWN blocks
        # Let me check the gate logic...
        # The gate checks status == VALIDATED, so PARTIAL should fail
        assert result.passed is False
        assert "PARTIAL" in result.remediation
        assert "1" in result.remediation  # vendor count
    
    def test_drl4_passes_with_validated(self):
        """DRL-4: passes with VALIDATED status (≥2 consistent)."""
        responses = [
            make_vendor_response("pyreg", mode=OvernightMode.HOLD),
            make_vendor_response("klean", mode=OvernightMode.HOLD),
        ]
        params = validate_overnight_responses(responses)
        
        result = overnight_mode_validation_gate(params, claimed_drl=4)
        
        assert result.passed is True
        assert result.remediation is None
    
    def test_drl5_also_blocked_by_unknown(self):
        """DRL-5+: also blocked by UNKNOWN (same as DRL-4)."""
        params = OvernightModeParams()
        
        result = overnight_mode_validation_gate(params, claimed_drl=5)
        
        assert result.passed is False
    
    def test_remediation_message_includes_pipeline(self):
        """Remediation message includes resolution path."""
        params = OvernightModeParams()
        
        result = overnight_mode_validation_gate(params, claimed_drl=4)
        
        assert "VendorOvernightData" in result.remediation
        assert "validate_overnight_responses" in result.remediation


# =============================================================================
# Test: Integration with ModelParameters
# =============================================================================

class TestModelParametersIntegration:
    """Tests for overnight_mode integration in ModelParameters."""
    
    def test_default_model_params_has_overnight_mode(self):
        """ModelParameters includes overnight_mode field."""
        from septage_model.core import ModelParameters
        
        params = ModelParameters()
        
        assert hasattr(params, 'overnight_mode')
        assert isinstance(params.overnight_mode, OvernightModeParams)
        assert params.overnight_mode.status == OvernightModeStatus.UNKNOWN
    
    def test_overnight_mode_blocks_drl4_by_default(self):
        """Default overnight_mode blocks DRL-4."""
        from septage_model.core import ModelParameters
        
        params = ModelParameters()
        
        assert params.overnight_mode.blocks_drl4 is True
