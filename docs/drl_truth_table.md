# Design Readiness Level (DRL) Truth Table

> Canonical reference for DRL governance.
> Generated: 2026-02-06 | Current achieved level: **DRL-3**

---

## DRL Scale

| Level | Description | Phase |
|-------|-------------|-------|
| DRL-1 | Basic principles observed | Concept |
| DRL-2 | Technology concept formulated | Concept |
| DRL-3 | Analytical/experimental proof of concept | Concept |
| DRL-4 | Component validation in lab | Development |
| DRL-5 | Component validation in relevant environment | Development |
| DRL-6 | System/subsystem model or prototype demo | Development |
| DRL-7 | System prototype demo in operational environment | Production |
| DRL-8 | Actual system completed and qualified | Production |
| DRL-9 | Actual system proven in operation | Production |

---

## Criteria Matrix

| # | Criterion | Required DRL | Description | Status |
|---|-----------|:------------:|-------------|:------:|
| 1 | `mass_balance_validated` | 2 | Mass balance equations verified against literature | ✅ |
| 2 | `energy_balance_validated` | 2 | Energy balance equations verified against literature | ✅ |
| 3 | `proof_of_concept_model` | 3 | Simulation model produces reasonable outputs | ✅ |
| 4 | `dewatering_params_validated` | 4 | Dewatering performance validated with bench tests | ❌ |
| 5 | `pyrolysis_yields_validated` | 4 | Pyrolysis yields validated with lab tests | ❌ |
| 6 | `economics_locked` | 5 | Economic model frozen with validated parameters | ❌ |
| 7 | `ci_gates_passing` | 5 | All CI design gates passing | ❌ |
| 8 | `fmea_no_critical` | 5 | No critical failure modes (RPN > 100) | ❌ |
| 9 | `maintenance_model_validated` | 6 | Maintenance model validated with vendor data | ❌ |
| 10 | `capex_vendor_validated` | 6 | CAPEX estimates validated with vendor quotes | ❌ |
| 11 | `pilot_design_complete` | 6 | Pilot system design package complete | ❌ |
| 12 | `pilot_commissioned` | 7 | Pilot system commissioned and operational | ❌ |
| 13 | `pilot_performance_validated` | 7 | Pilot performance matches model predictions | ❌ |
| 14 | `production_design_complete` | 8 | Production system design package complete | ❌ |
| 15 | `regulatory_approval` | 8 | Required regulatory approvals obtained | ❌ |
| 16 | `production_operational` | 9 | Production system operational at customer site | ❌ |
| 17 | `performance_sustained` | 9 | Performance sustained over 12+ months | ❌ |

---

## Blocking Analysis

**Achieved:** DRL-3 — All concept-phase criteria pass (mass balance, energy balance, proof of concept).

**Next target:** DRL-4

**Blocking criteria for DRL-4:**
- `dewatering_params_validated` — Requires bench-test data from vendor dewatering equipment.
- `pyrolysis_yields_validated` — Requires lab pyrolysis of actual septage-derived feedstock.

**Path to DRL-4:** Complete vendor cut-sheet ingestion for dewatering parameters,
run lab pyrolysis on representative feedstock, update model parameters with measured values.

---

## CI Gate Integration

The following CI gates from `septage_model/ci/gates.py` enforce frozen product constraints.
DRL-5 requires `ci_gates_passing` — meaning **all** design gates must pass.

| Gate | Threshold | Unit |
|------|-----------|------|
| `maintenance_budget_gate` | ≤ $35,000 | $/yr |
| `payback_gate` | ≤ 15.0 | years |
| `callout_frequency_gate` | ≤ 1.0 | /week |
| `physics_sanity_gate` | ≥ 1.0 | energy self-sufficiency ratio |
| `conversion_gate` | process-specific | — |
| `thermal_feasibility_gate` | Q_req ≤ Q_max | kW |
| `kinetics_validation_gate` | DRL-4+ block | — |
| `overnight_mode_validation_gate` | DRL-4+ block | — |
| `source_refs_gate` | all refs present | — |
| `operating_envelope_gate` | within bounds | — |
| `nutrient_recovery_viability_gate` | positive NPV | $ |
| `chp_grid_viability_gate` | positive NPV | $ |

---

## Rule: DRL-N Achievement

DRL-N is achieved **if and only if** every criterion with `required_for_drl ≤ N` has `passed = True`.

The evaluation walks from DRL-9 down to DRL-1 and returns the highest level
where all required criteria pass. See `DRLAssessment.achieved_drl` in
`septage_model/ci/design_readiness.py`.
