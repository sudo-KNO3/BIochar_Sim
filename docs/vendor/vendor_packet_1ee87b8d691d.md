# Vendor Engagement Packet

**Generated**: 2026-02-05 09:20
**Version Hash**: `1ee87b8d691d`

---

## Executive Summary

This packet defines the requirements for vendor equipment to be integrated 
into the Septage-to-Biochar Processing System (Product Mode). Equipment that 
does not meet these requirements cannot be used.

**Current Design Readiness Level**: DRL-3 (Concept)
**CI Gate Status**: PASS (4/4 gates)
**Critical Failure Modes**: 0

---

## 1. MVP Engineering Specification

### Septage-to-Biochar Processing System - Product Mode

Continuous septage-to-biochar processing system designed for owner-operated deployment at rural waste handling facilities. System converts septage and wood co-feed into marketable biochar while achieving energy self-sufficiency.

### Scale Parameters

| Parameter | Value |
|-----------|-------|
| Annual Septage M3 | 2000 |
| Annual Cofeed Tds | 600 |
| Operating Days Per Year | 250 |
| Operating Hours Per Day | 8 |

### Performance Requirements

| Requirement | Value | Threshold |
|-------------|-------|-----------|
| Energy Self Sufficiency | 1.64 ratio | >= 1.0 |
| Char Production | 238.4 tonnes/year | - |
| Maintenance Cost | 23264.0 $/year | <= 35,000 |
| Callout Frequency | 0.12 callouts/week | <= 1.0 |

### Critical Design Constraints

**Owner Serviceability**: All routine maintenance tasks (< 4hr interval) must be performable by owner with standard tools. Contractor callouts limited to < 1/week average.

**Modular Replacement**: High-wear components (auger flights, seals, bearings) must be designed for modular replacement without specialized equipment.

**Condition Monitoring**: Vibration, temperature, and torque monitoring required on all rotating equipment. O2 monitoring required on pyrolyzer.

---

## 2. CI Gate Report

**Status**: PASS

### Frozen Constraints

| Constraint | Value |
|------------|-------|
| Max Maintenance Budget | $35,000/year |
| Max Payback Years | 15.0 years |
| Max Callouts Per Week | 1.0 |
| Energy Self Sufficiency | >= 100% |

### Gate Results

| Gate | Status | Value | Threshold |
|------|--------|-------|-----------|
| Maintenance Budget | ✅ | 23264.0 | 35000 |
| Payback Period | ✅ | 14.54 | 15.0 |
| Callout Frequency | ✅ | 0.12 | 1.0 |
| Energy Self-Sufficiency | ✅ | 1.64 | 1.0 |

> These gates are enforced automatically in CI. Any design change that violates these constraints will be rejected. Vendor equipment that cannot meet these requirements is not suitable for this application.

---

## 3. FMEA Summary

| Metric | Value |
|--------|-------|
| Total Failure Modes | 26 |
| Critical (RPN > 100) | 0 |
| Moderate (RPN 50-100) | 17 |
| Average RPN | 58.0 |
| Owner Serviceable | 77.0% |

### Top Risk Modes (Vendor Attention Required)

| Component | Failure Mode | RPN | Serviceable |
|-----------|--------------|-----|-------------|
| Screw Press | Screw wear/binding | 96 | ✅ |
| Pyrolyzer Auger | Auger seizure | 96 | ❌ |
| Char Discharge Valve | Valve sticking | 96 | ✅ |
| Pyrolyzer Seals | Seal degradation | 84 | ✅ |
| Heat Exchanger | Tube fouling | 80 | ✅ |

---

## 4. Validation Requirements

> Vendors are requested to provide data demonstrating that their equipment meets the acceptance criteria listed below. Data must include test methodology, sample characteristics, and measured values.

### DRL-4 Requirements

#### Dewatering Performance Validation

**Data Type**: bench_test
**Status**: not_started

Validate dewatering unit performance against model assumptions. Requires bench-scale testing with representative septage samples.

**Acceptance Criteria**:

| Parameter | Expected | Range | Tolerance | Unit |
|-----------|----------|-------|-----------|------|
| cake_ts_fraction | 0.2 | 0.18-0.25 | ±15% | fraction |
| solids_capture | 0.95 | 0.9-1.0 | ±5% | fraction |
| polymer_kg_per_tds | 5.0 | 3.0-8.0 | ±30% | kg/TDS |
| power_kwh_per_m3 | 2.0 | 1.0-4.0 | ±50% | kWh/m³ |

*Note: Requires 3+ batch tests with septage from target service area.*

#### Pyrolysis Yield Validation

**Data Type**: lab_test
**Status**: not_started

Validate pyrolysis product yields against model assumptions. Requires lab-scale pyrolysis testing with dewatered cake samples.

**Acceptance Criteria**:

| Parameter | Expected | Range | Tolerance | Unit |
|-----------|----------|-------|-----------|------|
| char_yield_septage | 0.467 | 0.35-0.55 | ±15% | kg char/kg TDS |
| char_yield_cofeed | 0.35 | 0.25-0.45 | ±15% | kg char/kg TDS |
| syngas_yield_septage | 3.2 | 2.5-4.5 | ±20% | MJ/kg TDS |
| syngas_yield_cofeed | 5.4 | 4.0-6.5 | ±15% | MJ/kg TDS |

*Note: Pyrolysis at 500-600°C, residence time 15-30 min. Test both septage-only and co-feed blends.*

### DRL-6 Requirements

#### CAPEX Vendor Validation

**Data Type**: vendor_spec
**Status**: not_started

Validate CAPEX estimates with actual vendor quotes. Requires budgetary quotes from equipment vendors.

**Acceptance Criteria**:

| Parameter | Expected | Range | Tolerance | Unit |
|-----------|----------|-------|-----------|------|
| total_capex | 1200000 | 800000-1600000 | ±25% | $ |
| capex_multiplier_product | 0.6 | 0.5-0.75 | ±15% | fraction |

*Note: Requires quotes for: dewatering, dryer, pyrolyzer, char handling, controls.*

#### Maintenance Model Validation

**Data Type**: vendor_spec
**Status**: not_started

Validate maintenance cost and callout frequency assumptions. Requires vendor maintenance schedules and spare parts pricing.

**Acceptance Criteria**:

| Parameter | Expected | Range | Tolerance | Unit |
|-----------|----------|-------|-----------|------|
| annual_maintenance_cost | 23000 | 15000-35000 | ±30% | $/year |
| callouts_per_year | 26 | 10-52 | ±50% | callouts/year |
| owner_serviceable_pct | 0.85 | 0.7-1.0 | ±10% | fraction |

*Note: Cross-reference with FMEA failure modes and MTTR estimates.*

---

## 5. DRL Status

**Current Level**: DRL-3
**Phase**: Concept
**Description**: Analytical/experimental proof of concept

The system is at DRL-3, meaning the design is analytically validated but awaiting empirical confirmation. Advancement to DRL-4 requires vendor/lab data for 2 validation tasks.

### Blocking for Next Level

- **dewatering_params_validated**: Dewatering performance validated with bench tests
- **pyrolysis_yields_validated**: Pyrolysis yields validated with lab tests

---

## Version Control

- **Packet Hash**: `1ee87b8d691d`
- **Generated**: 2026-02-05T09:20:19.656001

This packet is version-controlled. Any modifications will generate a new hash. 
Vendors should reference this hash when submitting data.

---

*Generated by Biochar_Sim Vendor Engagement System*