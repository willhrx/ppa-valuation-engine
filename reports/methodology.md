# PPA Valuation Engine — Methodology

## Overview

This document records the assumptions behind every named parameter in the
model, what each represents, and what reasonable alternative values look like.
The model is a *scenario-conditional pricing tool*, not a forecast.  Every
number below is a stated assumption, not a prediction.

---

## Phase 1: Synthetic Data Generation

### 1a. Solar Production (`solar_production.py`)

| Parameter | Default | Reasonable range | What it represents |
|---|---|---|---|
| `capacity_mw` | 50 MW | 10–500 MW | Nameplate DC/AC capacity of the solar park |
| `tilt_deg` | 35° | 25–45° | Panel tilt from horizontal; optimised for NL latitude |
| `azimuth_deg` | 180° | 170–190° | Panel orientation; 180° = due south |
| `performance_ratio` | 0.80 | 0.75–0.85 | Ratio of actual to theoretical output (inverter, soiling, wiring losses) |
| `degradation_rate` | 0.5 %/yr | 0.4–0.7 %/yr | Annual linear decline in panel efficiency |
| `cloud_factor_phi` | 0.90 | 0.80–0.95 | AR(1) autocorrelation of cloud factor (higher = more persistent weather) |
| `monthly_cloud_means` | [0.38…0.68] | 0.3–0.7 | Mean fraction of clear-sky irradiance per month (Dutch climatology) |

**Cloud factor model:** The cloud factor is simulated as an AR(1) process in
logit-space, so values remain in (0, 1).  The autocorrelation (φ ≈ 0.90)
reflects the fact that weather systems over the Netherlands typically persist
for 1–3 days.  A single low-cloud-factor week can reduce monthly yield by
20–30 %.  This creates the "bad weeks" and "good weeks" visible in real
production data.

**Sanity checks:** Annual yield 900–1000 kWh/kWp; capacity factor 10–12 %;
zero output between sunset and sunrise.

---

### 1b. Consumer Load (`consumer_load.py`)

| Parameter | Default | Reasonable range | What it represents |
|---|---|---|---|
| `annual_consumption_gwh` | 100 GWh | 50–200 GWh | Total annual energy consumption of the industrial offtaker |
| `seasonal_amplitude` | 0.15 | 0.05–0.25 | Fractional winter uplift (space heating component) |
| `noise_sigma` | 0.05 | 0.03–0.10 | Log-normal noise on hourly load (equipment cycling, temperature variation) |

**Shape assumption:** Industrial offtaker with two daily demand peaks (morning
operational ramp ~10:00, afternoon peak ~18:00), lower weekend demand, and a
mild winter uplift for heating.  The shape is normalised and rescaled to hit
the target annual consumption exactly.

---

### 1c. Market Prices (`market_prices.py`)

Prices are the sum of five additive layers (all EUR/MWh):

#### Layer 1 — Long-term level and drift

| Parameter | Default | Reasonable range | What it represents |
|---|---|---|---|
| `base_price` | 80 EUR/MWh | 60–100 | Long-run equilibrium wholesale price level in 2027 |
| `drift` | −1.5 EUR/MWh/yr | −3.0 to 0 | Expected annual price change; negative = continued renewable build-out suppression |

**This is the assumption with least confidence.**  Energy system modellers
disagree by ±30 EUR/MWh on where 2035 prices will sit.  Always present
scenarios around this parameter.

#### Layer 2 — Seasonal shape

| Parameter | Default | Reasonable range | What it represents |
|---|---|---|---|
| `seasonal_amplitude` | 15 EUR/MWh | 10–25 | Half-amplitude of winter/summer swing |
| `seasonal_peak_day` | Day 15 | Days 1–30 | Day-of-year with highest prices (cold snap period) |

**Mechanism:** European gas demand (heating), reduced wind in anti-cyclonic
winter conditions, and shorter days all push winter prices up.  Summer
oversupply from solar pushes them down.

#### Layer 3 — Intra-day shape

24-hour additive profiles (weekday and weekend) calibrated so that:
- Peak hours (17:00–20:00, winter weekdays): 120–150 EUR/MWh total
- Off-peak night hours: 40–60 EUR/MWh total

The weekend profile is flatter and lower (reduced industrial demand).

#### Layer 4 — Solar cannibalisation

| Parameter | Default | Reasonable range | What it represents |
|---|---|---|---|
| `cannibalisation_alpha_2027` | 12 EUR/MWh | 5–20 | Price suppression at noon in mid-summer 2027 |
| `cannibalisation_alpha_2036` | 37 EUR/MWh | 20–60 | Same parameter by end of PPA (reflects continued solar build-out) |

**Critical for solar PPA valuation.**  As NL solar penetration grows, all
panels generate simultaneously at noon in summer → massive supply surplus →
prices crash or go negative.  This is the primary driver of capture-rate
erosion over the PPA horizon.  The alpha parameter grows linearly with
installed capacity assumptions.

#### Layer 5 — AR(1) autocorrelated noise

| Parameter | Default | Reasonable range | What it represents |
|---|---|---|---|
| `ar1_phi` | 0.70 | 0.50–0.90 | Hour-to-hour autocorrelation of price residuals |
| `ar1_sigma` | 8 EUR/MWh | 5–15 | Stationary standard deviation of residuals |

**Why autocorrelation matters for risk quantification:**
Without autocorrelation, a Monte Carlo model sees each hour as independent.
In reality, gas outages, cold snaps, and wind droughts last days to weeks.
This clustering means "bad periods" for the producer (low prices coinciding
with high production) are more severe and sustained than independent draws
would suggest.  AR(1) with φ = 0.70 corresponds to a half-life of ~3.3 hours,
creating realistic price persistence without over-smoothing.

---

## Capture Rate

The capture rate is the key metric linking solar production to market value:

```
capture_rate = (Σ price(t) × production(t)) / (avg_price × Σ production(t))
```

A capture rate of 0.80 means the solar asset earns 80 % of the average market
price per MWh generated.  The remaining 20 % is the cost of profile risk.

For NL solar, historical capture rates are in the 0.75–0.90 range (early
2020s) and are expected to decline to 0.65–0.75 by the mid-2030s as
penetration grows.  This is the central risk in any solar PPA priced against
market.

---

## Discount Rate

| Parameter | Default | Reasonable range | What it represents |
|---|---|---|---|
| `discount_rate` | 6 % | 4–10 % | Annual WACC for NPV discounting |

Solar IPP developers typically use 5–8 % WACC depending on leverage and
market risk premium.  Regulated offtakers may use 4–6 %.
