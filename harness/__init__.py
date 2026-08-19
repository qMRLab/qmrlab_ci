"""Derived-number computation for the qmrlab_ci benchmark.

Adapters emit maps, timing, and units. Everything computed from those — hashes,
statistics, comparisons — is computed here, once, so that a difference between two
targets is a difference between the softwares and not between two implementations
of the same statistic.
"""

__version__ = "0.1.0"
