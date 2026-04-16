"""
structures — Supply structure definitions (Phase 2).

A supply structure determines *how much energy* flows under the PPA in each
settlement period — it is independent of *how that energy is priced*.

Modules
-------
base              SupplyStructure abstract base class
pay_as_produced   Buyer takes 100 % of actual generation (default solar PPA)
pay_as_nominated  Fixed schedule agreed in advance; imbalance stays with producer
baseload          Flat 24/7 offtake profile regardless of actual production
"""
