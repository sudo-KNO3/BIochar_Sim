# Hub Mode Strategic Assessment: Go / No-Go Decision

**Document Status:** Decision Artifact  
**Generated:** 2026-02-06  
**Model Version:** DRL-3 (Design Closure)  
**Data Source:** `sensitivity/hub_viability_sweep.csv` (1,020 scenarios)

---

## Executive Summary

**Recommendation: CONDITIONAL NO-GO for general rural deployment.**

Hub mode is technically viable under specific conditions, but those conditions are narrow, fragile, and require owner-operation or suburban density. Product mode dominates on robustness, deployability, and risk profile.

Hub should be reserved for:
- Suburban fringe locations with guaranteed volume
- Owner-operated facilities with no labor cost
- Strategic pilots with explicit risk acceptance

---

## Viability Analysis Results

### Scenario Coverage

| Metric | Value |
|--------|-------|
| Total scenarios evaluated | 1,020 |
| Realistic scenarios (excluding $0 labor bound) | 816 |
| Viable scenarios | 358 (43.9% of realistic) |
| Failed scenarios | 458 (56.1% of realistic) |

### Failure Mode Distribution

| Failure Mode | Count | % of Total |
|--------------|-------|------------|
| Energy deficit (insufficient syngas) | 458 | 44.9% |
| Viable | 358 | 35.1% |
| Theoretical bound only ($0 labor) | 193 | 18.9% |
| CAPEX prohibitive | 11 | 1.1% |

**Key insight:** Nearly half of all scenarios fail due to energy deficit — the no-cofeed configurations cannot achieve thermal self-sufficiency at rural volumes.

---

## Minimum Viable Conditions

### Volume Threshold

| Catchment | Annual Volume | Viable? |
|-----------|---------------|---------|
| rural_small (35 km, 8/km²) | 3,009 m³/yr | ❌ NO — below threshold |
| rural_medium (50 km, 10/km²) | 5,017 m³/yr | ⚠️ MARGINAL — at threshold |
| rural_large (60 km, 12/km²) | 7,975 m³/yr | ✅ YES — with constraints |
| suburban_fringe (40 km, 35/km²) | 12,040 m³/yr | ✅ YES — best case |

**Minimum viable volume: 5,017 m³/yr**

This corresponds to ~50 km catchment radius at 10 people/km² with 10% participation rate.

### Staffing Requirements

| Staffing Regime | Annual Labor Cost | Viable Scenarios |
|-----------------|-------------------|------------------|
| Owner-operated (realistic) | $0 | 124 (35%) |
| Remote monitored | ~$40k | 93 (26%) |
| Shared operator | ~$67k | 82 (23%) |
| Light ops (40 hr/wk) | ~$133k | 59 (16%) |

**Maximum viable labor cost: $133,110/yr**

Viability drops sharply above owner-operated. Light-ops is marginal.

### Tipping Fee Sensitivity

**Minimum viable tipping fee: $35/m³**

Hub becomes viable at current market rates ($45/m³) only with:
- Suburban density (12k+ m³/yr), OR
- Owner-operation, OR
- High co-feed reliability

At $75/m³ tipping, most configurations become viable — but this is politically/competitively unrealistic.

---

## Viability by Deployment Context

### Rural-Only Assessment

| Metric | Value |
|--------|-------|
| Rural scenarios (small + medium + large) | 612 |
| Rural viable | 180 |
| Rural viability rate | 29.4% |

**Conclusion:** Rural hub viability is structurally constrained. Nearly 3 in 4 rural scenarios fail.

### Best-Case Scenario

| Parameter | Value |
|-----------|-------|
| Catchment | suburban_fringe (40 km radius) |
| Staffing | owner_operated_realistic |
| Co-feed | contracted_wood |
| Tipping fee | $75/m³ |
| Volume | 12,040 m³/yr |
| NOI | $689,362 |
| Payback | 4.4 years |

This is achievable only with suburban density, zero labor cost, and premium tipping fees.

### Worst Viable Scenario

| Parameter | Value |
|-----------|-------|
| Catchment | rural_medium (50 km radius) |
| Staffing | light_ops |
| Co-feed | contracted_wood |
| Tipping fee | $75/m³ |
| Volume | 5,017 m³/yr |
| NOI | ~$50k |
| Payback | ~19 years |

This is at the edge of viability — any parameter degradation pushes to failure.

---

## Comparison: Hub vs Product Mode

| Dimension | Product Mode | Hub Mode |
|-----------|--------------|----------|
| Minimum volume | 750 m³/yr | 5,017 m³/yr |
| Labor model | Owner-operated (0 cash) | Owner-op to light-ops |
| CAPEX | ~$220k (0.1× multiplier) | ~$2.2M (1.0× multiplier) |
| Payback (best) | 3.6 years | 4.4 years |
| Payback (typical) | 5-8 years | 15-20 years |
| Energy requirement | Cofeed required | Cofeed mandatory |
| Deployment risk | Low (modular) | High (fixed infrastructure) |
| Viability rate | >90% of scenarios | 44% of scenarios |

**Product mode dominates on:**
- Lower volume threshold (7× lower)
- Lower CAPEX (10× lower)
- Higher viability rate (2× higher)
- Lower deployment risk (modular vs fixed)

---

## Strategic Recommendations

### 1. General Rural Deployment: NO-GO

Hub mode should **not** be the default strategy for rural Ontario septage processing.

**Rationale:**
- 70% of rural scenarios fail
- Minimum volume (5k m³/yr) requires aggressive aggregation
- Labor cost sensitivity makes operations fragile
- Energy deficit at low volumes is structural

### 2. Suburban Fringe: CONDITIONAL GO

Hub may be appropriate for suburban fringe locations meeting ALL criteria:
- ✅ Guaranteed volume ≥ 10,000 m³/yr
- ✅ Owner-operator or shared staffing arrangement
- ✅ Contracted wood supply (≥95% reliability)
- ✅ Tipping fee ≥ $45/m³ with escalation

### 3. Strategic Pilot: CONDITIONAL GO

A single hub pilot may be justified to:
- Validate thermal performance at scale
- Establish regulatory precedent
- Demonstrate aggregation model

**Pilot requirements:**
- 5-year volume commitment from participating haulers
- Fallback to product mode if volume targets missed
- Explicit subsidy or grant support for first 3 years

### 4. Product Mode: GO (Default)

Product mode remains the recommended deployment path for:
- All rural locations
- Sites with volume < 8,000 m³/yr
- Operators unwilling to commit to staffing
- First-mover deployments

---

## Conclusion

**Hub mode is conditionally viable but fragile. Product mode dominates on robustness and deployability.**

The hub optimization analysis reveals that:

1. **Volume is the binding constraint** — rural catchments rarely generate enough septage
2. **Labor cost is the sensitivity lever** — only owner-operation is reliably viable
3. **Energy deficit kills no-cofeed scenarios** — cofeed is mandatory, not optional
4. **Suburban density is required** — rural-only hubs have 29% viability

The strategic recommendation is to **proceed with product mode as the primary deployment path**, reserving hub mode for opportunistic suburban deployments where all preconditions are met.

---

## Appendix: Data Sources

- **Hub optimization sweep:** `septage_model.analysis.hub_optimization`
- **Catchment calibration:** Rural Ontario baseline (3k / 5k / 8k / 12k m³/yr)
- **Staffing models:** `StaffingModel.owner_op()`, `.hub_light_ops()`
- **Tipping fee range:** $35–$75/m³ (17 values)
- **Co-feed scenarios:** contracted_wood, spot_wood, no_cofeed
- **Output artifact:** `sensitivity/hub_viability_sweep.csv`

---

*This document is a decision artifact. It reflects model state as of 2026-02-06 and should be updated if model parameters or market conditions change materially.*
