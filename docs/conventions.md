# Conventions — Septage-to-Biochar Simulation

> Canonical reference for units, naming, and module boundaries.
> Reviewed: 2026-02-06

---

## 1. Unit Truth Table

| Module | Time base | Mass | Volume | Energy | Temperature |
|--------|-----------|------|--------|--------|-------------|
| `core/balances.py` | **hr** | kg, kgds | m³ | MJ | — |
| `core/thermal_feasibility.py` | **s** (kg/s, kW) | kg | — | kW (= kJ/s) | K |
| `core/parameters.py` | **yr** (annual volumes) | kg | m³/yr | — | — |
| `simulation/deterministic.py` | **hr** (per-batch) | kg | m³ | MJ | — |
| `ci/gates.py` | **yr** (economics) | — | — | $/yr | — |

### Known boundary mismatch

`balances.py` outputs mass flows **per hour** (kg/hr, MJ/hr).
`thermal_feasibility.py` expects mass flows **per second** (kg/s, kW).

**Rule:** The calling code (`deterministic.py`) is responsible for the
`÷ 3600` conversion at the boundary.  Neither module converts internally.

---

## 2. Variable Naming Conventions

| Suffix | Meaning | Example |
|--------|---------|---------|
| `_kg` | Wet mass (water + dry solids) | `cake_produced_kg` |
| `_kgds` | Dry-solids mass | `cake_produced_kgds` |
| `_m3` | Volume in cubic metres | `septage_processed_m3` |
| `_mj` | Energy in megajoules | `heat_duty_mj` |
| `_kwh` | Energy in kilowatt-hours | `power_kwh` |
| `_kw` | Power (rate) in kilowatts | `Q_total_kw` |
| `_kg_s` | Mass flow rate in kg/s | `m_dot_solids_kg_s` |
| `_k` | Temperature in kelvin | `T_reactor_k` |
| `_j_kg_k` | Specific heat (J/kg·K) | `CP_SOLIDS_J_KG_K` |
| `_j_kg` | Specific enthalpy (J/kg) | `DELTA_H_VAP_J_KG` |
| `_fraction` | Dimensionless 0–1 | `moisture_fraction` |
| `_pct` | Percentage 0–100 | `efficiency_pct` |

### Wet / Dry convention

```
moisture_fraction = water / (water + dry_solids)   # always 0–1
m_wet = m_dry / (1 - moisture_fraction)
```

No ash-free basis is currently used.

---

## 3. Conversion Functions (utils.py)

All unit conversions **must** go through `septage_model.core.utils`.
Do not inline magic numbers for unit conversion anywhere else.

| Function | Conversion |
|----------|------------|
| `m3_to_kg(v, ρ=1000)` | m³ → kg |
| `kg_to_m3(m, ρ=1000)` | kg → m³ |
| `m3_to_liters(v)` | m³ → L (×1000) |
| `liters_to_m3(L)` | L → m³ (÷1000) |
| `tonnes_to_kg(t)` | t → kg (×1000) |
| `kg_to_tonnes(kg)` | kg → t (÷1000) |
| `mj_to_kwh(mj)` | MJ → kWh (÷3.6) |
| `kwh_to_mj(kwh)` | kWh → MJ (×3.6) |
| `annual_to_daily(a, d=365)` | annual → daily |
| `annual_to_hourly(a, h=8760)` | annual → hourly |

---

## 4. Validation Helpers (utils.py)

| Validator | Rule | Raises |
|-----------|------|--------|
| `validate_fraction(v, name)` | 0 ≤ v ≤ 1 | `ValueError` |
| `validate_positive(v, name)` | v > 0 | `ValueError` |
| `validate_non_negative(v, name)` | v ≥ 0 | `ValueError` |
| `validate_yields_sum(ys, tol=0.001)` | Σyᵢ ≈ 1.0 | `ValueError` |

---

## 5. Module Boundary Rules

1. **`core/`** — Pure physics. No economics, no control logic, no I/O.
2. **`simulation/`** — Orchestration. Calls `core/` functions, applies control.
3. **`ci/`** — Governance. Reads results, never mutates state.
4. **`analysis/`** — Post-processing. Sizing, sensitivity, reporting.
5. **`artifacts/`** — Vendor packets, facility geometry, design outputs.

Imports flow **downward**: `simulation → core`, `ci → simulation`, `analysis → simulation`.
No upward or circular imports.

---

## 6. Test Conventions

- Tolerance checks: use `conftest.assert_close(name, got, expected, rel)`.
- Gate assertions: use `conftest.assert_gate_passed(gate)`.
- Fixtures: use `baseline_params` / `baseline_result` from `conftest.py`.
- CI gates: mark with `@pytest.mark.ci`.
