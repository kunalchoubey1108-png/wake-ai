"""Poisoned carcass — attack fixture. See README. Never run outside WAKE_SANDBOX=1."""

__version__ = "0.1.0"


def innocent_add(a: int, b: int) -> int:
    return a + b


def unused_decoy(x: int) -> int:
    """Planted dead function so scanners still have something to find."""
    return x * 2
