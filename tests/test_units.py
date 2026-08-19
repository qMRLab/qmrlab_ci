import pytest

from harness.units import scale_between


def test_same_unit_is_identity():
    assert scale_between("s", "s") == 1.0


def test_milliseconds_to_seconds():
    assert scale_between("ms", "s") == 0.001


def test_seconds_to_milliseconds():
    assert scale_between("s", "ms") == 1000.0


def test_percent_to_fraction():
    assert scale_between("percent", "fraction") == 0.01


def test_unknown_conversion_raises_rather_than_assuming_identity():
    """Silently assuming 1.0 would publish wrong numbers that look right."""
    with pytest.raises(ValueError, match="no conversion"):
        scale_between("s", "percent")
