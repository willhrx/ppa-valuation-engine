# PPA Valuation Engine — Project Brief

## Context

This project is a portfolio piece for a Junior Energy Analyst role at Balanz Energy B.V. (Utrecht, NL). The role involves developing and maintaining PPA valuation models, calculating pricing scenarios and risk parameters, and supporting the structuring of PPA offers to offtakers and producers. The required stack is Python with **pandas**, **NumPy**, and **scikit-learn**.

The goal is to build an industry-grade PPA valuation engine from first principles — not a forecasting tool, but a **pricing tool**: a structured way to express a view about the future, translate that view into a price, and quantify how sensitive that price is to each assumption.

---

## Key Conceptual Framing

### What this model IS

- A scenario-conditional pricing engine: "Under these stated assumptions, the PPA is worth €X, and here is how that changes if you disagree with any assumption."
- A risk decomposition tool: which assumptions drive the most uncertainty in the deal value?
- A negotiation framework: what is the producer's break-even price vs the consumer's alternative, and what is the acceptable pricing range?

### What this model IS NOT

- A price forecaster. Every forward-looking number is wrong. The model's value lies in transparency, auditability, and the ability to re-price when assumptions are challenged.
- Every layer of the data generation represents an explicit, named, documentable assumption — not a prediction.

### The four PPA risks being modelled (from Sia Partners framework)

1. **Volume risk** — uncertainty in how much the asset produces annually
2. **Profile risk** — uncertainty in *when* production occurs relative to price patterns (the capture-price problem)
3. **Price risk** — uncertainty in wholesale market prices
4. **Counterparty risk** — creditworthiness (modelled qualitatively, not in scope for v1)

---

## Deal Specification (Primary Case)

| Parameter | Value |
| --- | --- |
| Asset type | Solar PV (utility-scale) |
| Capacity | 50 MW |
| Location | Utrecht, Netherlands (lat 52.1°N, lon 5.1°E) |
| Operational start | 1 January 2027 |
| PPA tenor | 10 years (2027-01-01 to 2036-12-31) |
| Granularity | Hourly |
| Currency | EUR/MWh |
| Consumer | Mid-sized industrial offtaker, ~100 GWh/year |
| Market | Dutch day-ahead (EPEX NL) |

---

## Project Phases

### Phase 0 — Repo Scaffolding

Set up the project structure, dependencies, and configuration.

### Phase 1 — Synthetic Data Generation

Generate forward-looking "central case" hourly data for the full 10-year horizon. This is not forecasting — it is constructing a reference scenario with the right statistical properties so that downstream valuations are meaningful.

### Phase 2 — Core Valuation Engine (CURRENT PHASE)

NPV calculator, three supply structures (pay-as-produced, pay-as-nominated, baseload), four pricing structures (fixed flat, fixed escalated, indexed with floor/cap, floating), and capture-price decomposition.

### Phase 3 — Risk Quantification (Monte Carlo)

Stochastic price and production simulators, 1,000-path Monte Carlo, risk metrics (VaR, Expected Shortfall, P10/P50/P90 NPV), risk decomposition by source.

### Phase 4 — Pricing Solver & Scenario Analysis

Break-even price solver (scipy.optimize.brentq), sensitivity/tornado analysis, floor/cap option pricing.

### Phase 5 — Reporting & Documentation

Deal walkthrough notebook, methodology doc, portfolio-ready README.

---

## Phase 1 Specification (Detailed)

### 1a. Solar Production — `src/ppa_engine/data/solar_production.py`

Use **pvlib** for the deterministic solar geometry and clear-sky model:

1. Define location: `pvlib.location.Location(lat=52.1, lon=5.1, tz='Europe/Amsterdam', altitude=10)`
2. Generate hourly timestamps for the full 2027-2036 horizon
3. Compute clear-sky irradiance using Ineichen model (`pvlib.clearsky.ineichen()`)
4. Compute solar position and project onto a 35° south-facing tilted panel
5. Apply a **stochastic cloud factor** — a beta-distributed multiplier with monthly means matching Dutch climatology (winter ~0.35, summer ~0.65), **autocorrelated** hour-to-hour (φ ≈ 0.85-0.95 — weather systems persist)
6. Apply performance ratio (~0.80) and annual degradation (0.5%/year linear)
7. Multiply by capacity (50 MW) to get hourly AC output in MWh

**Sanity checks:**

- Annual yield: 900-1,000 kWh/kWp
- Capacity factor: 10-12%
- Zero generation between sunset and sunrise
- Realistic "bad weeks" and "good weeks" due to autocorrelated cloud factor

### 1b. Consumer Load — `src/ppa_engine/data/consumer_load.py`

- Annual consumption ~100 GWh
- Hourly load shape: weekday/weekend distinction, daily peaks ~10:00 and ~18:00, seasonal variation (higher in winter for heating)
- Stochastic noise layer

### 1c. Market Prices — `src/ppa_engine/data/market_prices.py`

Build prices as a **sum of five layers**, each representing an explicit assumption:

**Layer 1 — Long-term level and drift:**

```text
level(t) = base_price + drift × years_from_2027(t)
```

Default: base_price=75 €/MWh, drift=-1.5 €/MWh/year. This is the assumption with least confidence and should be clearly flagged.

**Layer 2 — Seasonal shape:**

```text
seasonal(t) = amplitude × cos(2π × (day_of_year - peak_day) / 365)
```

Default: amplitude=15 €/MWh, peak_day=15 (mid-January). Winter high, summer low.

**Layer 3 — Intra-day shape:**

- 24-hour vector of hour-of-day multipliers
- Morning peak (~07:00-09:00), evening peak (~17:00-20:00), midday dip in summer
- Separate weekday/weekend profiles (weekend is flatter, lower)

**Layer 4 — Cannibalisation term (critical for solar PPA valuation):**

```text
cannibalisation(t) = -α(year) × system_solar_proxy(t)
```

Where system_solar_proxy(t) is a sinusoid peaking at noon in summer (all NL solar generates simultaneously), and α(year) grows linearly reflecting continued solar buildout. Calibrate so mid-summer noon prices are ~€40-50 in 2027 and occasionally negative by 2034.

**Layer 5 — Autocorrelated noise (AR(1)):**

```text
noise(t) = φ × noise(t-1) + ε(t), where ε ~ Normal(0, σ)
```

Default: φ=0.7, σ=8 €/MWh. Autocorrelation is essential because:

- Physical price drivers (gas, weather, outages) persist over multiple hours/days
- It creates realistic sustained "good periods" and "bad periods"
- It correctly models the clustering of low prices with high solar output, which is what makes capture-price erosion a *clustering phenomenon* rather than just an average effect
- Without it, Monte Carlo would systematically underestimate revenue volatility

**Edge cases:**

- Allow negative prices (real EPEX NL goes negative on sunny windy Sundays) — do NOT floor at zero
- Skip price spikes in v1 (rare, cancel out over 10 years)

**Sanity checks:**

- Annual average: ~€80 in 2027, declining to ~€60 by 2036
- Peak hours (17:00-20:00 winter weekdays): €120-150
- Solar-peak hours (12:00-14:00 summer): €20-40 early years, occasionally negative later
- Weekend nights: €30-50
- **Capture rate for the solar asset: 0.65-0.85, declining over the horizon**

### 1d. Configuration — `src/ppa_engine/config.py`

All assumptions should be configurable, not hardcoded. Use dataclasses or a config dict. The model is a scenario tool — swapping assumptions and re-running is the core workflow.

---

## Repo Structure

```text
ppa-valuation-engine/
├── README.md
├── pyproject.toml
├── .gitignore
├── src/
│   └── ppa_engine/
│       ├── __init__.py
│       ├── data/
│       │   ├── __init__.py
│       │   ├── solar_production.py      # Phase 1a
│       │   ├── consumer_load.py         # Phase 1b
│       │   └── market_prices.py         # Phase 1c
│       ├── structures/
│       │   ├── __init__.py
│       │   ├── base.py                  # SupplyStructure ABC
│       │   ├── pay_as_produced.py
│       │   ├── pay_as_nominated.py
│       │   └── baseload.py
│       ├── pricing/
│       │   ├── __init__.py
│       │   ├── base.py                  # PricingStructure ABC
│       │   ├── fixed.py                 # flat + escalated
│       │   ├── indexed.py               # with floor/cap
│       │   └── floating.py
│       ├── valuation/
│       │   ├── __init__.py
│       │   ├── npv.py                   # core DCF
│       │   ├── capture.py               # capture price calc
│       │   └── solver.py                # break-even price (scipy.optimize.brentq)
│       ├── risk/
│       │   ├── __init__.py
│       │   ├── monte_carlo.py
│       │   ├── price_process.py         # AR(1) / Ornstein-Uhlenbeck
│       │   ├── production_scenarios.py  # P50/P90
│       │   └── metrics.py               # VaR, ES, decomposition
│       └── config.py                    # all assumptions as dataclasses
├── notebooks/
│   ├── 00_data_sanity_checks.ipynb
│   ├── 01_single_deal_walkthrough.ipynb
│   └── 02_risk_decomposition.ipynb
├── tests/
│   ├── test_solar_production.py
│   ├── test_npv.py
│   ├── test_structures.py
│   └── test_capture_price.py
├── data/
│   └── .gitkeep
└── reports/
    └── methodology.md
```

---

## Dependencies

```text
pandas>=2.0
numpy>=1.24
scipy>=1.10
scikit-learn>=1.3
pvlib>=0.10
matplotlib>=3.7
seaborn>=0.12
jupyter>=1.0
pytest>=7.0
```

---

## Design Principles

1. **Separation of supply structures and pricing structures.** These are independent dimensions — any supply structure can be combined with any pricing structure (3×4 = 12 combinations).
2. **Tests from day one.** Even three tests beat zero. Use pytest.
3. **Notebooks call into `src/`, never contain business logic.** Logic lives in importable modules.
4. **Every assumption is a named parameter in config.** Nothing hardcoded in functions.
5. **Reproducible by default.** Seed all random generators. Same seed = same output. Flip seed to explore sensitivity.
6. **Document assumptions in `methodology.md`.** For each parameter, one sentence on what it represents and what reasonable ranges look like.

---

## Claude Code Kickoff Instruction

Start by scaffolding Phase 0 (repo structure, pyproject.toml, .gitignore, empty modules with docstrings, config dataclasses). Then implement Phase 1 in order: 1a (solar production with pvlib), 1c (market prices with all 5 layers), 1b (consumer load). Finish with a sanity-check notebook (00_data_sanity_checks.ipynb) that plots a sample week in January and July showing all three series, and computes the capture rate.
