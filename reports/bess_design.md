# BESS for solar PPAs — exploration & design basis

*Status: exploration only. No engine changes. Produced by
`scripts/bess_prototype.py` (read-only against `ppa_engine`), 2026-06-10.*

## Question

Should the valuation engine model a co-located battery (BESS), and does it
de-risk baseload PPAs in particular?

## Framing inside this engine

The producer's total economics under a baseload PPA decompose as

```
NPV_total = disc( delivered(t) × spot(t) )        physical sales
          + disc( flat × (strike − spot(t)) )     the CfD swap leg
```

The swap leg never sees the battery. A co-located BESS only re-shapes
`delivered(t)` — moving PV energy from cheap midday surplus hours into
expensive evening shortfall hours. That cleanly separates the BESS question
from the PPA-structure question and means a future `BatteryConfig` can sit
**between the solar generator and the supply structure** without touching
pricing or settlement code.

## Prototype

`scripts/bess_prototype.py`: greedy day-ahead dispatch with perfect
foresight (upper bound on value), PV-surplus-only charging (no grid import),
√η split round-trip losses, daily cycle cap, SOC carried across days.
Default 2027–2036 central scenario, 50 MW asset, flat obligation = mean
production (~5.8 MW).

### Results (central scenario)

Base: spot NPV €17.69M, capture rate 0.760.

| Battery (power/energy) | ΔNPV | Capture rate | Shortfall covered | Cycles/day | Breakeven capex |
|---|---|---|---|---|---|
| 5 MW / 5 MWh | +€0.58M | 0.790 | 4.5% | 0.89 | 117 €/kWh |
| 5 MW / 20 MWh | +€1.72M | 0.854 | 15.6% | 0.82 | 86 €/kWh |
| 10 MW / 40 MWh | +€3.15M | 0.934 | 14.9% | 0.74 | 79 €/kWh |
| 20 MW / 40 MWh | +€3.54M | 0.952 | 8.0% | 0.74 | 89 €/kWh |
| 20 MW / 80 MWh | +€5.03M | 1.046 | 12.3% | 0.61 | 63 €/kWh |

(Breakeven capex = the installed cost per kWh that the 10-year discounted
uplift would exactly pay back — no O&M, no degradation, perfect foresight.)

### Risk check (15 joint weather+price paths, 20 MW / 80 MWh, strike €65)

|  | mean NPV_total | σ | P10 |
|---|---|---|---|
| no BESS | €16.09M | €0.08M | €15.99M |
| with BESS | €21.52M | €0.10M | €21.42M |

## Findings

1. **The value story is capture rate, not arbitrage profit.** Even a small
   battery materially lifts the delivered capture rate (0.76 → 0.79–1.05).
   Duration matters more than power: 4-hour systems dominate 1-hour at
   equal energy cost-effectiveness, because the job is moving the midday
   hump into the evening peak, not fast cycling.
2. **Pure energy-shifting does not pay for the battery at today's capex.**
   Best case breaks even at ~63–117 €/kWh vs ~150–250 €/kWh installed for
   grid-scale storage in 2026 — and the prototype's perfect foresight makes
   these numbers an upper bound. A standalone "add BESS, collect arbitrage"
   case does not close on this central scenario. It improves over the
   horizon as cannibalisation deepens the midday/evening spread, which the
   model captures via the α ramp.
3. **10-year NPV variance is barely affected.** Hour-scale weather and
   price noise average out across 87,600 hours, so σ(NPV) is small with or
   without the battery. The popular intuition "a battery de-risks the
   baseload PPA" shows up *not* as variance reduction at the NPV level but
   as a **structurally better short position**: 8–16% of all shortfall
   energy is served from storage instead of bought at (typically high)
   evening spot. That should compress the baseload-vs-PaP fair-strike
   premium — measurable today with the existing `/api/solver/fair-strike`
   once delivered profiles can include a battery.
4. **Where the engine framework would need to grow** for missing value
   streams that often *do* close the BESS business case: imbalance/intraday
   revenues (the engine has no intraday market), capacity/ancillary
   revenues, and grid-charging arbitrage. Those are new market layers, not
   PPA-structure changes.

## Proposed v1 integration (when/if approved)

- `BatteryConfig` dataclass on `PPAConfig` (power, energy, η, cycle cap,
  enabled flag — default disabled, zero behaviour change).
- A `dispatch()` transform applied to the solar series **before** supply
  structures see it, in the orchestration layer (`value_all_combinations`
  and the MC path builder) — supply/pricing structures stay untouched.
- Foresight realism: replace perfect day-ahead foresight with
  deterministic-price-only foresight (dispatch on the price *shape*, settle
  on realised prices) to remove the upper-bound bias inside the MC.
- UI: a "Co-located BESS" section in the config panel (enable + power +
  duration), and the fair-strike tool re-run with/without to price the
  premium compression.

## Recommendation

**Go, but as a capture-rate / fair-strike feature, not a revenue feature.**
Model it to quantify how much a battery compresses the baseload premium and
lifts capture rate under user scenarios — that is decision-relevant for PPA
structuring. Do not present the ΔNPV as a battery investment case until
imbalance/intraday revenue layers exist; the prototype shows shifting alone
under-pays current capex by roughly 2×.
