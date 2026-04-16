"""
pricing — Pricing structure definitions (Phase 2).

A pricing structure determines *at what price* each MWh of contracted energy
is settled.  It is entirely independent of the supply structure.

Modules
-------
base       PricingStructure abstract base class
fixed      Fixed flat and fixed escalated pricing
indexed    Market-indexed with optional floor and cap
floating   Pure floating (spot price pass-through)
"""
