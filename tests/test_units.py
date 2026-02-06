"""
Unit-enforcement tests — fast-fail guards against basis mixing.

These tests validate that:
1. Validators reject out-of-range inputs (fraction vs percentage confusion)
2. Conversion functions roundtrip correctly
3. Mass balance checker detects imbalance
4. Thermal constants are in expected SI magnitude ranges
5. Yield closure is enforced
"""

import pytest
from septage_model.core.utils import (
    validate_fraction,
    validate_positive,
    validate_non_negative,
    validate_yields_sum,
    mj_to_kwh,
    kwh_to_mj,
    m3_to_kg,
    kg_to_m3,
    tonnes_to_kg,
    kg_to_tonnes,
    check_mass_balance,
)


class TestValidatorGuards:
    """Validators must reject out-of-range inputs immediately."""

    def test_validate_fraction_rejects_percentage(self):
        """Catch pct-vs-fraction confusion: 85% passed as 85.0 instead of 0.85."""
        with pytest.raises(ValueError, match="must be between 0 and 1"):
            validate_fraction(85.0, "moisture_content")

    def test_validate_fraction_rejects_negative(self):
        with pytest.raises(ValueError, match="must be between 0 and 1"):
            validate_fraction(-0.1, "solids_fraction")

    def test_validate_fraction_accepts_boundary(self):
        """Edge values 0.0 and 1.0 must be accepted."""
        validate_fraction(0.0, "zero_fraction")
        validate_fraction(1.0, "unity_fraction")
        validate_fraction(0.5, "mid_fraction")

    def test_validate_yields_sum_rejects_non_closure(self):
        """Yield fractions that don't sum to 1.0 must raise."""
        with pytest.raises(ValueError, match="must sum to 1.0"):
            validate_yields_sum([0.30, 0.40, 0.20])  # sums to 0.90


class TestConversionRoundtrips:
    """Conversion pairs must roundtrip to identity within float precision."""

    def test_mj_kwh_roundtrip(self):
        original = 42.0
        assert kwh_to_mj(mj_to_kwh(original)) == pytest.approx(original, rel=1e-12)

    def test_m3_kg_roundtrip(self):
        original = 5.0
        density = 1020.0  # septage density
        assert kg_to_m3(m3_to_kg(original, density), density) == pytest.approx(original, rel=1e-12)

    def test_tonnes_kg_roundtrip(self):
        original = 3.5
        assert kg_to_tonnes(tonnes_to_kg(original)) == pytest.approx(original, rel=1e-12)


class TestMassBalanceDetection:
    """Mass balance checker must catch imbalances."""

    def test_closed_balance_passes(self):
        result = check_mass_balance(mass_in=100.0, mass_out=100.0, accumulation=0.0)
        assert result.is_closed, f"Expected closed balance, got error={result.closure_error}"

    def test_imbalance_detected(self):
        result = check_mass_balance(mass_in=100.0, mass_out=90.0, accumulation=0.0, tolerance=1e-3)
        assert not result.is_closed, "10 kg imbalance should not be closed"
        assert result.closure_error == pytest.approx(10.0)


class TestThermalConstants:
    """Thermal constants must be in expected SI magnitude ranges."""

    def test_cp_water_in_range(self):
        """CP_WATER should be ~4186 J/kg·K (not kJ, not cal)."""
        from septage_model.core.thermal_feasibility import CP_WATER_J_KG_K
        assert 4000 < CP_WATER_J_KG_K < 4500, (
            f"CP_WATER_J_KG_K = {CP_WATER_J_KG_K} — expected ~4186 J/kg·K"
        )

    def test_delta_h_vap_in_range(self):
        """Latent heat of vaporization should be ~2.26e6 J/kg (not kJ, not BTU)."""
        from septage_model.core.thermal_feasibility import DELTA_H_VAP_J_KG
        assert 2.0e6 < DELTA_H_VAP_J_KG < 2.6e6, (
            f"DELTA_H_VAP_J_KG = {DELTA_H_VAP_J_KG} — expected ~2.26e6 J/kg"
        )

    def test_delta_h_py_in_range(self):
        """Pyrolysis enthalpy should be ~0.5e6 J/kg (order of magnitude check)."""
        from septage_model.core.thermal_feasibility import DELTA_H_PY_J_KG
        assert 1e5 < DELTA_H_PY_J_KG < 2e6, (
            f"DELTA_H_PY_J_KG = {DELTA_H_PY_J_KG} — expected ~0.5e6 J/kg"
        )
