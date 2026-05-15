# PPA Valuation Engine

A Python-based valuation and risk analysis tool for Power Purchase Agreements on renewable energy assets, built from first principles for the Dutch wholesale electricity market.

## Quick Start

```bash
git clone https://github.com/willhrx/ppa-valuation-engine.git
cd ppa-valuation-engine
pip install -e ".[dev]"
streamlit run app/main.py
```

The app opens at `http://localhost:8501`.

- **Deal Setup** — configure your solar asset, market assumptions, and offtaker load
- **Run Simulation** — launch a Monte Carlo simulation (500 paths ≈ 20 s)
- **Risk Summary** — interactive dashboard with NPV distributions, break-even analysis, and risk attribution charts
- **Reports** — download a PDF deal summary or Excel workbook

Screenshot: _add screenshot of Risk Summary page here_

## Motivation

Power Purchase Agreements are long-term contracts between renewable energy producers and consumers (offtakers) that fix the terms for selling electricity over periods of 3 to 25+ years. Valuing these contracts requires modelling the interaction between intermittent renewable production, hourly wholesale market prices, and the contractual structure that determines how volume, profile, and price risk are allocated between counterparties.

This project builds an end-to-end PPA valuation engine that takes a forward-looking view of the market as input, prices a deal under multiple supply and pricing structures, and quantifies how sensitive the valuation is to each underlying assumption. It is designed to reflect the analytical workflow of a commercial energy trading desk — not as a forecasting tool, but as a **pricing and risk decomposition tool** that makes disagreements about the future legible and quantifiable.

## Primary Case

The model is built around a concrete deal scenario to keep everything grounded:

| Parameter | Value |
| Asset | 50 MW solar PV, utility-scale |
| Location | Utrecht, Netherlands (52.1°N, 5.1°E) |
| Operational start | 1 January 2027 |
| PPA tenor | 10 years (2027–2036) |
| Granularity | Hourly |
| Offtaker | Industrial consumer, ~100 GWh/year |
| Market | Dutch day-ahead (EPEX NL), EUR/MWh |

## What the Model Does

Given a set of explicitly stated assumptions about the future (market price trajectory, solar resource, demand patterns etc.), the engine:

1. **Generates synthetic hourly data** for production, consumption, and day-ahead prices across the full contract horizon — not as a forecast, but as a coherent reference scenario with realistic statistical properties.

2. **Values the PPA** under combinations of three supply structures and four pricing structures, computing NPV for both the producer and the consumer, and decomposing value into its components.

3. **Quantifies risk** through Monte Carlo simulation — generating thousands of alternative futures and reporting distributional metrics (P10/P50/P90, Value-at-Risk, Expected Shortfall) rather than point estimates.

4. **Solves for break-even pricing** — finding the PPA price that meets a producer's target IRR and comparing it against the consumer's market alternative, identifying the negotiation range.

5. **Decomposes risk by source** — attributing total NPV variance to volume risk, profile risk, and price risk independently, so that structural choices (e.g. pay-as-produced vs baseload) can be evaluated in terms of which risks they transfer and at what cost.

## Core Concepts

### The Capture Price Problem

A solar asset's revenue per MWh is not the average wholesale price — it is the **production-weighted average price**, known as the capture price. Because all solar assets in a market generate simultaneously (they see the same sun), high-solar hours are also high-supply hours, which suppresses prices. The ratio of capture price to baseload average (the **capture rate**) is typically 0.65–0.85 for Dutch solar and declining as installed capacity grows.

This cannibalisation effect is the single most important driver of solar PPA economics. The model implements it explicitly so that the price gap between supply structures emerges from the mathematics rather than being assumed.

### Supply Structures

| Structure | Volume delivered | Risk allocation |
| **Pay-as-produced** | Actual asset output | Consumer carries price and profile risk; cheapest structure |
| **Pay-as-nominated** | Day-ahead forecast; imbalances settled at imbalance price | Producer takes forecast accuracy risk; +3–5% premium |
| **Baseload** | Fixed MW every hour; producer covers shortfalls on spot market | Producer carries nearly all risk; most expensive structure |

### Pricing Structures

| Structure | Mechanism |
| **Fixed flat** | Single price for the full term |
| **Fixed escalated** | Fixed with annual escalator (e.g. inflation-linked) |
| **Indexed** | Base price linked to an index, with optional floor and cap |
| **Floating** | Spot price minus a discount, with optional floor |

Any supply structure can be combined with any pricing structure (12 combinations), and the model evaluates each independently.

### Assumptions as Parameters

Every forward-looking input is an explicit, named, configurable assumption — not a hardcoded number. The synthetic price model is built as five additive layers:

1. **Long-term level and drift** — baseline wholesale price and its annual trajectory
2. **Seasonal shape** — winter premium, summer discount
3. **Intra-day shape** — morning and evening peaks, midday solar dip, weekday/weekend distinction
4. **Cannibalisation** — price suppression correlated with system-wide solar output, increasing over time
5. **Autocorrelated noise** — AR(1) process capturing the persistence of price drivers (weather, fuel costs, outages)

The model is a scenario tool: swap the assumptions, re-run, and observe how the pricing range moves. The output is never a single NPV — it is always a distribution conditional on stated assumptions, with sensitivity analysis showing which assumptions matter most.

## Project Structure

```text
ppa-valuation-engine/
├── src/
│   └── ppa_engine/
│       ├── data/                  # Synthetic data generators
│       │   ├── solar_production.py
│       │   ├── consumer_load.py
│       │   └── market_prices.py
│       ├── structures/            # Supply structure implementations
│       │   ├── base.py
│       │   ├── pay_as_produced.py
│       │   ├── pay_as_nominated.py
│       │   └── baseload.py
│       ├── pricing/               # Pricing structure implementations
│       │   ├── base.py
│       │   ├── fixed.py
│       │   ├── indexed.py
│       │   └── floating.py
│       ├── valuation/             # NPV, capture price, solver
│       │   ├── npv.py
│       │   ├── capture.py
│       │   └── solver.py
│       ├── risk/                  # Monte Carlo and risk metrics
│       │   ├── monte_carlo.py
│       │   ├── price_process.py
│       │   ├── production_scenarios.py
│       │   └── metrics.py
│       └── config.py              # All assumptions as dataclasses
├── notebooks/
│   ├── 00_data_sanity_checks.ipynb
│   ├── 01_single_deal_walkthrough.ipynb
│   └── 02_risk_decomposition.ipynb
├── tests/
├── data/
└── reports/
    └── methodology.md
```

## Build Plan

### Phase 1 — Synthetic Data Generation

Generate a 10-year hourly reference scenario (87,600+ hours) for solar production, consumer load, and day-ahead prices. Solar production uses pvlib for deterministic solar geometry with a stochastic cloud-factor overlay calibrated to Dutch climatology. Prices are built layer by layer so each structural driver is independently tuneable.

**Success criteria:** Capture rate for the solar asset sits between 0.65–0.85 against the synthetic price series, with visible cannibalisation (prices dipping when solar peaks) on sample-week plots.

### Phase 2 — Core Valuation Engine

Implement the NPV calculator, all supply and pricing structure combinations, and the capture-price decomposition. The valuation should be callable as a single function that returns producer NPV, consumer NPV, and a breakdown of value components.

**Success criteria:** Baseload PPAs price higher than pay-as-produced by a margin that emerges from the model, not from a hard-coded premium. The sum of producer and consumer NPVs is consistent across structures (risk is redistributed, not created).

### Phase 3 — Monte Carlo Risk Quantification

Build stochastic generators for prices (AR(1) / Ornstein-Uhlenbeck) and production (P50/P90 framework). Run 1,000-path simulations and report distributional risk metrics. Decompose total risk into volume, profile, and price components by running single-source perturbation scenarios.

**Success criteria:** Pay-as-produced shows higher variance in producer NPV than baseload, confirming that the structure transfers risk to the consumer. Risk decomposition attributes measurable shares to each risk source.

### Phase 4 — Pricing Solver & Scenario Analysis

Solve for break-even PPA prices given target IRRs. Build tornado charts ranking assumption sensitivity. Quantify the cost of price floors and caps via Monte Carlo.

**Success criteria:** The model outputs a negotiation range (producer floor to consumer ceiling) and can price structural features (floors, caps, escalators) as incremental costs.

### Phase 5 — Reporting & Documentation

End-to-end deal walkthrough notebook, methodology documentation with all assumptions and their justifications, and this README refined into a portfolio-ready summary.

## Tech Stack

- **pandas** — hourly time-series manipulation, resampling, joining production and price frames
- **NumPy** — Monte Carlo array operations, stochastic process generation
- **scipy** — break-even price solver (Brent's method), statistical distributions
- **scikit-learn** — fitting price process parameters from historical residuals, regression
- **pvlib** — solar position, clear-sky irradiance, plane-of-array projection
- **matplotlib / seaborn** — all visualisation
- **pytest** — test suite

## References

- Sia Partners & Alterna Energie, *A Practical Guide to PPAs* (2023)
- Swindle, G., *Valuation and Risk Management in Energy Markets*, Cambridge University Press
- ENTSO-E Transparency Platform — Dutch day-ahead price data
- KNMI — Dutch solar irradiance climatology
- Pexapark PPA Price Index — European PPA market benchmarks

## License

This project is an educational portfolio piece and is not intended for production trading use.
