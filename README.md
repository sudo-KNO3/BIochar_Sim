# BIochar_Sim

Techno-economic simulation of a **septage-to-biochar processing hub** — a
physics model of the dewatering/pyrolysis pathway coupled to a financial model,
with sensitivity analysis over the drivers that decide whether the hub pencils
out.

## What it does

- **Physics** — dewatering and thermal-conversion process model
  (`septage_model/analysis/physics_appendix.py`, `docs/physics_appendix_*.md`)
- **Economics** — pathway scenarios and hub optimization
  (`analysis/pathway_scenarios.py`, `analysis/hub_optimization.py`)
- **Sensitivity** — 2-D net-operating-income surfaces over the key levers
  (tipping fee, co-feed volume, char price, labor); outputs in `sensitivity/`
- **Vendor intake** — structured vendor-parameter submission + validation
  workflow under `docs/vendor/`

```bash
python run.py        # run the model
```

Example sensitivity output (net operating income vs. two drivers):

- `tipping_fee_vs_cofeed_volume_tds_noi.png`
- `tipping_fee_vs_char_tier2_price_noi.png`
- `cofeed_volume_tds_vs_labor_factor_noi.png`

## Stack

`Python` · `pyproject.toml` packaging · CI via GitHub Actions · matplotlib

## Status

Working model with documented conventions, an FMEA, and a go/no-go report under
`docs/`. Parameters are configuration-driven.
