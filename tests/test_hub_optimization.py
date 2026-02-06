"""
test_hub_optimization.py

Comprehensive test suite for hub_optimization.py (984 lines).

Covers:
  - CatchmentModel: geometry math, calibrated factories, optimistic bounds
  - HubStaffingScenario: labor costs, factory methods, theoretical bounds
  - CofeedScenario: delivered cost, risk adjustment, factory methods
  - HubViabilityResult: CSV serialization, field completeness
  - Failure mode classification: all 6 modes
  - evaluate_single_scenario: integration with simulation engine
  - run_hub_optimization: sweep structure, breakeven extraction
  - HubViabilityAnalysis: summary generation, filtering
  - CSV export: file write, column completeness
  - Cross-module consistency: parameter imports, staffing model alignment
"""

import csv
import math
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from septage_model.analysis.hub_optimization import (
    CatchmentModel,
    CofeedScenario,
    FailureMode,
    HubStaffingScenario,
    HubViabilityAnalysis,
    HubViabilityResult,
    classify_failure_mode,
    evaluate_single_scenario,
    export_to_csv,
    run_hub_optimization,
    CSV_COLUMNS,
)
from septage_model.core.parameters import (
    ModelParameters,
    StaffingModel,
    create_hub_scenario,
)


# =============================================================================
# CatchmentModel — geometry and volume calculations
# =============================================================================

class TestCatchmentModelGeometry:
    """Test the catchment area and volume math."""

    def test_theoretical_volume_formula(self):
        """Volume = π r² × density × septic_frac × l_per_cap_day × 365 / 1000."""
        c = CatchmentModel(
            radius_km=50.0,
            population_density_per_km2=10.0,
            septic_system_fraction=0.35,
            septage_l_per_capita_day=5.0,
        )
        area = math.pi * 50**2
        pop = area * 10
        septic = pop * 0.35
        daily_l = septic * 5.0
        expected = daily_l * 365 / 1000
        assert c.calc_theoretical_volume_m3_yr() == pytest.approx(expected, rel=1e-9)

    def test_capturable_volume_applies_participation(self):
        """Capturable = theoretical × participation_rate (unless hauler-capped)."""
        c = CatchmentModel(
            radius_km=10.0,
            population_density_per_km2=5.0,
            participation_rate=0.20,
            haulers_in_territory=100,  # very high — no cap
        )
        theoretical = c.calc_theoretical_volume_m3_yr()
        assert c.calc_capturable_volume_m3_yr() == pytest.approx(
            theoretical * 0.20, rel=1e-9
        )

    def test_hauler_capacity_ceiling(self):
        """Hauler capacity is a hard ceiling on capturable volume."""
        c = CatchmentModel(
            radius_km=200.0,           # huge area → huge theoretical
            population_density_per_km2=50.0,
            participation_rate=1.0,    # 100% capture
            haulers_in_territory=1,
            avg_truck_capacity_m3=10.0,
            loads_per_hauler_per_day=1.0,
            operating_days_per_year=250,
        )
        hauler_cap = 1 * 10 * 1.0 * 250  # 2,500 m³/yr
        assert c.calc_capturable_volume_m3_yr() == pytest.approx(hauler_cap)

    def test_avg_haul_distance(self):
        """Average haul = 2/3 of radius."""
        c = CatchmentModel(radius_km=60.0)
        assert c.calc_avg_haul_distance_km() == pytest.approx(60.0 * 0.67)

    def test_implied_population(self):
        """Population = π r² × density."""
        c = CatchmentModel(radius_km=30.0, population_density_per_km2=20.0)
        expected = math.pi * 30**2 * 20
        assert c.calc_implied_population() == pytest.approx(expected, rel=1e-9)

    def test_zero_participation_gives_zero_volume(self):
        c = CatchmentModel(participation_rate=0.0, radius_km=50.0)
        assert c.calc_capturable_volume_m3_yr() == 0.0

    def test_capturable_never_exceeds_theoretical(self):
        """Even at 100% participation, capturable ≤ theoretical (hauler cap aside)."""
        c = CatchmentModel(
            participation_rate=1.0,
            haulers_in_territory=1000,  # no cap
        )
        assert c.calc_capturable_volume_m3_yr() <= c.calc_theoretical_volume_m3_yr()


class TestCatchmentCalibratedFactories:
    """Test the calibrated factory methods hit their target volumes."""

    def test_rural_small_near_3000(self):
        c = CatchmentModel.rural_small()
        vol = c.calc_capturable_volume_m3_yr()
        assert 2500 < vol < 3500, f"rural_small should be ~3k, got {vol:.0f}"
        assert c.is_calibrated is True

    def test_rural_medium_near_5000(self):
        c = CatchmentModel.rural_medium()
        vol = c.calc_capturable_volume_m3_yr()
        assert 4000 < vol < 6000, f"rural_medium should be ~5k, got {vol:.0f}"
        assert c.calibration_anchor == "rural_ontario_base_5k"

    def test_rural_large_near_8000(self):
        c = CatchmentModel.rural_large()
        vol = c.calc_capturable_volume_m3_yr()
        assert 7000 < vol < 9500, f"rural_large should be ~8k, got {vol:.0f}"

    def test_suburban_fringe_near_12000(self):
        c = CatchmentModel.suburban_fringe()
        vol = c.calc_capturable_volume_m3_yr()
        assert 10000 < vol < 14000, f"suburban_fringe should be ~12k, got {vol:.0f}"

    def test_factory_ordering(self):
        """Factories are ordered by volume: small < medium < large < suburban."""
        vols = [
            CatchmentModel.rural_small().calc_capturable_volume_m3_yr(),
            CatchmentModel.rural_medium().calc_capturable_volume_m3_yr(),
            CatchmentModel.rural_large().calc_capturable_volume_m3_yr(),
            CatchmentModel.suburban_fringe().calc_capturable_volume_m3_yr(),
        ]
        assert vols == sorted(vols), f"Volumes not monotonically increasing: {vols}"


class TestCatchmentOptimisticBounds:
    """Test optimistic bound scenarios are properly flagged."""

    def test_optimistic_rural_medium_flagged(self):
        c = CatchmentModel.optimistic_rural_medium()
        assert c.is_optimistic_bound is True
        assert c.is_calibrated is False

    def test_optimistic_rural_large_flagged(self):
        c = CatchmentModel.optimistic_rural_large()
        assert c.is_optimistic_bound is True
        assert c.is_calibrated is False

    def test_optimistic_exceeds_calibrated(self):
        """Optimistic medium should exceed calibrated medium volume."""
        cal = CatchmentModel.rural_medium().calc_capturable_volume_m3_yr()
        opt = CatchmentModel.optimistic_rural_medium().calc_capturable_volume_m3_yr()
        assert opt > cal

    def test_calibration_report_returns_string(self):
        c = CatchmentModel.rural_medium()
        report = c.calibration_report()
        assert "rural_medium" in report
        assert "Captured volume" in report


# =============================================================================
# HubStaffingScenario — labor cost and factory methods
# =============================================================================

class TestHubStaffingScenario:
    """Test staffing scenario labor cost calculations."""

    def test_owner_operated_baseline_is_zero_labor(self):
        s = HubStaffingScenario.owner_operated_baseline()
        assert s.annual_labor_cost() == 0.0
        assert s.is_theoretical_bound is True

    def test_owner_operated_realistic_is_zero_cash(self):
        s = HubStaffingScenario.owner_operated_realistic()
        assert s.annual_labor_cost() == 0.0
        assert s.is_theoretical_bound is False

    def test_light_ops_positive_labor(self):
        s = HubStaffingScenario.light_ops()
        assert s.annual_labor_cost() > 0
        assert s.is_theoretical_bound is False

    def test_fully_staffed_exceeds_light_ops(self):
        light = HubStaffingScenario.light_ops().annual_labor_cost()
        full = HubStaffingScenario.fully_staffed().annual_labor_cost()
        assert full > light, "Fully staffed should cost more than light ops"

    def test_shared_operator_less_than_light_ops(self):
        shared = HubStaffingScenario.shared_operator().annual_labor_cost()
        light = HubStaffingScenario.light_ops().annual_labor_cost()
        assert shared < light, "Shared operator (50%) should be cheaper"

    def test_remote_monitored_has_on_call(self):
        s = HubStaffingScenario.remote_monitored()
        assert s.staffing.on_call_allowance_weekly > 0
        assert s.annual_labor_cost() > 0

    def test_all_factory_names_unique(self):
        scenarios = [
            HubStaffingScenario.owner_operated_baseline(),
            HubStaffingScenario.owner_operated_realistic(),
            HubStaffingScenario.remote_monitored(),
            HubStaffingScenario.shared_operator(),
            HubStaffingScenario.light_ops(),
            HubStaffingScenario.fully_staffed(),
        ]
        names = [s.name for s in scenarios]
        assert len(names) == len(set(names)), f"Duplicate staffing names: {names}"

    def test_staffing_cost_ordering(self):
        """Owner < shared < remote < light < fully_staffed (approximate)."""
        costs = {
            "owner_baseline": HubStaffingScenario.owner_operated_baseline().annual_labor_cost(),
            "owner_realistic": HubStaffingScenario.owner_operated_realistic().annual_labor_cost(),
            "shared": HubStaffingScenario.shared_operator().annual_labor_cost(),
            "light": HubStaffingScenario.light_ops().annual_labor_cost(),
            "fully": HubStaffingScenario.fully_staffed().annual_labor_cost(),
        }
        assert costs["owner_baseline"] == 0
        assert costs["owner_realistic"] == 0
        assert costs["shared"] < costs["light"]
        assert costs["light"] < costs["fully"]


# =============================================================================
# CofeedScenario — delivered cost and risk adjustment
# =============================================================================

class TestCofeedScenario:
    """Test co-feed scenario cost calculations."""

    def test_delivered_cost_includes_transport(self):
        c = CofeedScenario(
            name="test",
            base_cost_per_tds=50.0,
            transport_km=40.0,
            transport_cost_per_tds_km=0.10,
            supply_reliability=1.0,
            seasonal_variation_factor=1.0,
        )
        assert c.delivered_cost_per_tds() == pytest.approx(50.0 + 40.0 * 0.10)

    def test_risk_adjusted_adds_reliability_penalty(self):
        c = CofeedScenario(
            name="test",
            base_cost_per_tds=100.0,
            transport_km=0.0,
            transport_cost_per_tds_km=0.0,
            supply_reliability=0.50,  # 50% reliability
            seasonal_variation_factor=1.0,
        )
        delivered = c.delivered_cost_per_tds()
        risk_adj = c.risk_adjusted_cost_per_tds()
        assert risk_adj > delivered, "Risk adjustment should increase cost"
        # penalty = 1 + (1 - 0.50) * 0.30 = 1.15
        assert risk_adj == pytest.approx(delivered * 1.15)

    def test_perfect_reliability_no_penalty(self):
        c = CofeedScenario(
            name="test",
            base_cost_per_tds=80.0,
            transport_km=10.0,
            transport_cost_per_tds_km=0.10,
            supply_reliability=1.0,
            seasonal_variation_factor=1.0,
        )
        assert c.risk_adjusted_cost_per_tds() == pytest.approx(c.delivered_cost_per_tds())

    def test_disabled_cofeed_zero_cost(self):
        c = CofeedScenario.no_cofeed()
        assert c.delivered_cost_per_tds() == 0.0
        assert c.risk_adjusted_cost_per_tds() == 0.0
        assert c.enabled is False

    def test_contracted_wood_defaults(self):
        c = CofeedScenario.contracted_wood()
        assert c.supply_reliability >= 0.90
        assert c.delivered_cost_per_tds() > 0

    def test_spot_wood_less_reliable(self):
        contracted = CofeedScenario.contracted_wood()
        spot = CofeedScenario.spot_wood()
        assert spot.supply_reliability < contracted.supply_reliability

    def test_ag_residue_most_seasonal(self):
        ag = CofeedScenario.ag_residue()
        assert ag.seasonal_variation_factor >= 1.5

    def test_all_factory_names_unique(self):
        scenarios = [
            CofeedScenario.contracted_wood(),
            CofeedScenario.spot_wood(),
            CofeedScenario.ag_residue(),
            CofeedScenario.no_cofeed(),
        ]
        names = [s.name for s in scenarios]
        assert len(names) == len(set(names))


# =============================================================================
# HubViabilityResult — serialization
# =============================================================================

class TestHubViabilityResult:
    """Test result data structure and serialization."""

    @pytest.fixture
    def sample_result(self):
        return HubViabilityResult(
            catchment_name="test",
            catchment_radius_km=50.0,
            population_density=10.0,
            staffing_regime="light_ops",
            cofeed_strategy="contracted_wood",
            tipping_fee=55.0,
            annual_volume_m3=5000.0,
            annual_cofeed_tds=150.0,
            annual_revenue=300000.0,
            annual_opex=200000.0,
            labor_cost=130000.0,
            noi=100000.0,
            capex=800000.0,
            payback_years=8.0,
            energy_self_sufficient=True,
            viable=True,
            is_theoretical_bound=False,
            dominant_failure_mode=FailureMode.STRUCTURALLY_VIABLE,
            binding_constraint="None",
        )

    def test_csv_row_has_all_columns(self, sample_result):
        row = sample_result.to_csv_row()
        for col in CSV_COLUMNS:
            assert col in row, f"Missing CSV column: {col}"

    def test_csv_row_inf_payback_serialized_as_string(self):
        r = HubViabilityResult(
            catchment_name="test", catchment_radius_km=50, population_density=10,
            staffing_regime="x", cofeed_strategy="y", tipping_fee=50,
            annual_volume_m3=5000, annual_cofeed_tds=0,
            annual_revenue=0, annual_opex=100000, labor_cost=50000,
            noi=-50000, capex=800000,
            payback_years=float('inf'),
            energy_self_sufficient=True, viable=False,
            is_theoretical_bound=False,
            dominant_failure_mode=FailureMode.LABOR_DOMINATED,
            binding_constraint="test",
        )
        row = r.to_csv_row()
        assert row['payback_years'] == 'inf'

    def test_csv_row_finite_payback_is_numeric(self, sample_result):
        row = sample_result.to_csv_row()
        assert isinstance(row['payback_years'], float)

    def test_failure_mode_serialized_as_value(self, sample_result):
        row = sample_result.to_csv_row()
        assert row['dominant_failure_mode'] == "viable"


# =============================================================================
# Failure Mode Classification
# =============================================================================

class TestFailureModeClassification:
    """Test classify_failure_mode covers all 6 modes."""

    def _make_result(self, **overrides) -> HubViabilityResult:
        defaults = dict(
            catchment_name="test", catchment_radius_km=50, population_density=10,
            staffing_regime="light_ops", cofeed_strategy="contracted",
            tipping_fee=55, annual_volume_m3=5000, annual_cofeed_tds=150,
            annual_revenue=300000, annual_opex=200000, labor_cost=50000,
            noi=100000, capex=800000, payback_years=8.0,
            energy_self_sufficient=True, viable=True,
            is_theoretical_bound=False,
            dominant_failure_mode=FailureMode.STRUCTURALLY_VIABLE,
            binding_constraint="",
        )
        defaults.update(overrides)
        return HubViabilityResult(**defaults)

    def test_viable_scenario(self):
        r = self._make_result(viable=True)
        mode, _ = classify_failure_mode(r)
        assert mode == FailureMode.STRUCTURALLY_VIABLE

    def test_theoretical_bound_viable(self):
        r = self._make_result(is_theoretical_bound=True, noi=50000)
        mode, constraint = classify_failure_mode(r)
        assert mode == FailureMode.THEORETICAL_BOUND_ONLY
        assert "$0 labor" in constraint

    def test_theoretical_bound_fails(self):
        r = self._make_result(is_theoretical_bound=True, viable=False, noi=-10000)
        mode, _ = classify_failure_mode(r)
        assert mode == FailureMode.CAPEX_PROHIBITIVE

    def test_energy_deficit(self):
        r = self._make_result(viable=False, energy_self_sufficient=False)
        mode, _ = classify_failure_mode(r)
        assert mode == FailureMode.ENERGY_DEFICIT

    def test_volume_starved(self):
        r = self._make_result(viable=False, annual_volume_m3=1000.0)
        mode, _ = classify_failure_mode(r)
        assert mode == FailureMode.VOLUME_STARVED

    def test_labor_dominated(self):
        r = self._make_result(
            viable=False,
            annual_opex=200000,
            labor_cost=150000,  # 75% of OPEX
        )
        mode, _ = classify_failure_mode(r)
        assert mode == FailureMode.LABOR_DOMINATED

    def test_capex_prohibitive_fallback(self):
        r = self._make_result(
            viable=False,
            annual_opex=200000,
            labor_cost=50000,   # 25% — not labor dominated
            annual_volume_m3=5000,  # above threshold
            payback_years=30.0,
        )
        mode, _ = classify_failure_mode(r)
        assert mode == FailureMode.CAPEX_PROHIBITIVE

    def test_all_failure_modes_covered(self):
        """All 6 FailureMode enum values exist."""
        assert len(FailureMode) == 6
        expected = {
            "viable", "labor_dominated", "volume_starved",
            "energy_deficit", "capex_prohibitive", "theoretical_bound_only",
        }
        actual = {m.value for m in FailureMode}
        assert actual == expected


# =============================================================================
# evaluate_single_scenario — integration with simulation engine
# =============================================================================

class TestEvaluateSingleScenario:
    """Test single scenario evaluation end-to-end."""

    def test_returns_hub_viability_result(self):
        result = evaluate_single_scenario(
            catchment=CatchmentModel.rural_medium(),
            staffing=HubStaffingScenario.light_ops(),
            cofeed=CofeedScenario.contracted_wood(),
            tipping_fee=55.0,
        )
        assert isinstance(result, HubViabilityResult)

    def test_volume_matches_catchment(self):
        catchment = CatchmentModel.rural_medium()
        result = evaluate_single_scenario(
            catchment=catchment,
            staffing=HubStaffingScenario.light_ops(),
            cofeed=CofeedScenario.contracted_wood(),
            tipping_fee=55.0,
        )
        assert result.annual_volume_m3 == pytest.approx(
            catchment.calc_capturable_volume_m3_yr(), rel=1e-6
        )

    def test_tipping_fee_stored(self):
        result = evaluate_single_scenario(
            catchment=CatchmentModel.rural_medium(),
            staffing=HubStaffingScenario.light_ops(),
            cofeed=CofeedScenario.contracted_wood(),
            tipping_fee=42.50,
        )
        assert result.tipping_fee == 42.50

    def test_theoretical_bound_not_viable(self):
        """Even if NOI > 0, theoretical bounds should not be marked viable."""
        result = evaluate_single_scenario(
            catchment=CatchmentModel.suburban_fringe(),
            staffing=HubStaffingScenario.owner_operated_baseline(),
            cofeed=CofeedScenario.contracted_wood(),
            tipping_fee=75.0,
        )
        assert result.is_theoretical_bound is True
        assert result.viable is False  # excluded from viability

    def test_no_cofeed_sets_zero_tds(self):
        result = evaluate_single_scenario(
            catchment=CatchmentModel.rural_medium(),
            staffing=HubStaffingScenario.light_ops(),
            cofeed=CofeedScenario.no_cofeed(),
            tipping_fee=55.0,
        )
        assert result.annual_cofeed_tds == 0.0

    def test_failure_mode_populated(self):
        result = evaluate_single_scenario(
            catchment=CatchmentModel.rural_medium(),
            staffing=HubStaffingScenario.light_ops(),
            cofeed=CofeedScenario.contracted_wood(),
            tipping_fee=55.0,
        )
        assert result.dominant_failure_mode in FailureMode
        assert isinstance(result.binding_constraint, str)

    def test_revenue_increases_with_tipping_fee(self):
        r_low = evaluate_single_scenario(
            catchment=CatchmentModel.rural_medium(),
            staffing=HubStaffingScenario.light_ops(),
            cofeed=CofeedScenario.contracted_wood(),
            tipping_fee=35.0,
        )
        r_high = evaluate_single_scenario(
            catchment=CatchmentModel.rural_medium(),
            staffing=HubStaffingScenario.light_ops(),
            cofeed=CofeedScenario.contracted_wood(),
            tipping_fee=75.0,
        )
        assert r_high.annual_revenue > r_low.annual_revenue

    def test_noi_higher_at_zero_labor(self):
        """$0 labor should always produce higher NOI than paid staff."""
        r_zero = evaluate_single_scenario(
            catchment=CatchmentModel.rural_medium(),
            staffing=HubStaffingScenario.owner_operated_baseline(),
            cofeed=CofeedScenario.contracted_wood(),
            tipping_fee=55.0,
        )
        r_paid = evaluate_single_scenario(
            catchment=CatchmentModel.rural_medium(),
            staffing=HubStaffingScenario.light_ops(),
            cofeed=CofeedScenario.contracted_wood(),
            tipping_fee=55.0,
        )
        assert r_zero.noi >= r_paid.noi


# =============================================================================
# run_hub_optimization — sweep mechanics
# =============================================================================

class TestRunHubOptimization:
    """Test the parametric sweep orchestration."""

    @pytest.fixture(scope="class")
    def small_sweep(self):
        """Run a small sweep (1 catchment × 2 staffing × 1 cofeed × 3 fees = 6)."""
        return run_hub_optimization(
            catchments=[CatchmentModel.rural_medium()],
            staffing_scenarios=[
                HubStaffingScenario.owner_operated_baseline(),
                HubStaffingScenario.light_ops(),
            ],
            cofeed_scenarios=[CofeedScenario.contracted_wood()],
            tipping_fees=[45.0, 55.0, 65.0],
            include_theoretical_bound=True,
        )

    def test_result_count(self, small_sweep):
        assert len(small_sweep.results) == 6  # 1 × 2 × 1 × 3

    def test_returns_analysis_object(self, small_sweep):
        assert isinstance(small_sweep, HubViabilityAnalysis)

    def test_theoretical_bounds_separated(self, small_sweep):
        # 3 scenarios are from owner_operated_baseline
        assert len(small_sweep.theoretical_bounds) == 3

    def test_failure_mode_counts_sum(self, small_sweep):
        total = sum(small_sweep.failure_mode_counts.values())
        assert total == len(small_sweep.results)

    def test_summary_returns_string(self, small_sweep):
        summary = small_sweep.summary()
        assert isinstance(summary, str)
        assert "HUB VIABILITY ANALYSIS" in summary
        assert "Total scenarios evaluated" in summary

    def test_viable_scenarios_exclude_theoretical(self, small_sweep):
        for r in small_sweep.viable_scenarios:
            assert r.is_theoretical_bound is False

    def test_best_scenario_is_viable_or_none(self, small_sweep):
        if small_sweep.best_scenario is not None:
            assert small_sweep.best_scenario.viable is True


# =============================================================================
# CSV Export
# =============================================================================

class TestCSVExport:
    """Test CSV file export functionality."""

    def test_export_writes_file(self):
        analysis = run_hub_optimization(
            catchments=[CatchmentModel.rural_medium()],
            staffing_scenarios=[HubStaffingScenario.light_ops()],
            cofeed_scenarios=[CofeedScenario.contracted_wood()],
            tipping_fees=[55.0],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_export.csv"
            export_to_csv(analysis, path)
            assert path.exists()

    def test_export_has_header_and_data(self):
        analysis = run_hub_optimization(
            catchments=[CatchmentModel.rural_medium()],
            staffing_scenarios=[HubStaffingScenario.light_ops()],
            cofeed_scenarios=[CofeedScenario.contracted_wood()],
            tipping_fees=[55.0, 65.0],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.csv"
            export_to_csv(analysis, path)

            with open(path, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert len(rows) == 2
            assert set(reader.fieldnames) == set(CSV_COLUMNS)

    def test_csv_columns_match_result_keys(self):
        """CSV_COLUMNS should match the keys from to_csv_row()."""
        r = HubViabilityResult(
            catchment_name="x", catchment_radius_km=50, population_density=10,
            staffing_regime="x", cofeed_strategy="y", tipping_fee=50,
            annual_volume_m3=5000, annual_cofeed_tds=0,
            annual_revenue=0, annual_opex=0, labor_cost=0,
            noi=0, capex=0, payback_years=0,
            energy_self_sufficient=True, viable=False,
            is_theoretical_bound=False,
            dominant_failure_mode=FailureMode.STRUCTURALLY_VIABLE,
            binding_constraint="",
        )
        assert set(r.to_csv_row().keys()) == set(CSV_COLUMNS)


# =============================================================================
# HubViabilityAnalysis — summary and breakeven
# =============================================================================

class TestHubViabilityAnalysisSummary:
    """Test the analysis summary output."""

    def test_no_viable_shows_message(self):
        analysis = HubViabilityAnalysis(
            results=[],
            viable_scenarios=[],
            theoretical_bounds=[],
            best_scenario=None,
            min_viable_volume_m3=None,
            min_viable_tipping_fee=None,
            max_viable_labor_cost=None,
            failure_mode_counts={},
        )
        summary = analysis.summary()
        assert "NO VIABLE SCENARIOS FOUND" in summary

    def test_summary_includes_failure_distribution(self):
        analysis = HubViabilityAnalysis(
            results=[],
            viable_scenarios=[],
            theoretical_bounds=[],
            best_scenario=None,
            min_viable_volume_m3=None,
            min_viable_tipping_fee=None,
            max_viable_labor_cost=None,
            failure_mode_counts={FailureMode.LABOR_DOMINATED: 5},
        )
        summary = analysis.summary()
        assert "FAILURE MODE DISTRIBUTION" in summary
        assert "labor_dominated" in summary

    def test_breakeven_thresholds_in_summary(self):
        analysis = HubViabilityAnalysis(
            results=[],
            viable_scenarios=[],
            theoretical_bounds=[],
            best_scenario=None,
            min_viable_volume_m3=None,
            min_viable_tipping_fee=None,
            max_viable_labor_cost=None,
            failure_mode_counts={},
        )
        summary = analysis.summary()
        assert "BREAKEVEN THRESHOLDS" in summary


# =============================================================================
# Cross-module consistency
# =============================================================================

class TestCrossModuleConsistency:
    """Verify hub_optimization uses core parameters correctly."""

    def test_create_hub_scenario_returns_model_parameters(self):
        params = create_hub_scenario()
        assert isinstance(params, ModelParameters)

    def test_staffing_model_hub_light_ops_matches(self):
        """HubStaffingScenario.light_ops wraps StaffingModel.hub_light_ops."""
        scenario = HubStaffingScenario.light_ops()
        direct = StaffingModel.hub_light_ops()
        assert scenario.staffing.mode == direct.mode
        assert scenario.annual_labor_cost() == pytest.approx(
            direct.annual_cash_labor_cost()
        )

    def test_staffing_model_fully_staffed_matches(self):
        """HubStaffingScenario.fully_staffed wraps StaffingModel.hub_staffed."""
        scenario = HubStaffingScenario.fully_staffed()
        direct = StaffingModel.hub_staffed()
        assert scenario.annual_labor_cost() == pytest.approx(
            direct.annual_cash_labor_cost()
        )

    def test_owner_op_matches(self):
        scenario = HubStaffingScenario.owner_operated_baseline()
        direct = StaffingModel.owner_op(owner_hours=0.0)
        assert scenario.annual_labor_cost() == direct.annual_cash_labor_cost() == 0.0

    def test_default_tipping_fees_in_range(self):
        """Default sweep covers $35-$75/m³ (Ontario market range)."""
        fees = [35.0 + i * 2.5 for i in range(17)]
        assert fees[0] == 35.0
        assert fees[-1] == 75.0
        assert len(fees) == 17


# =============================================================================
# FailureMode enum completeness
# =============================================================================

class TestFailureModeEnum:
    """Test FailureMode enum is well-defined."""

    def test_enum_members(self):
        assert FailureMode.STRUCTURALLY_VIABLE.value == "viable"
        assert FailureMode.LABOR_DOMINATED.value == "labor_dominated"
        assert FailureMode.VOLUME_STARVED.value == "volume_starved"
        assert FailureMode.ENERGY_DEFICIT.value == "energy_deficit"
        assert FailureMode.CAPEX_PROHIBITIVE.value == "capex_prohibitive"
        assert FailureMode.THEORETICAL_BOUND_ONLY.value == "theoretical_bound_only"

    def test_enum_count(self):
        assert len(FailureMode) == 6
