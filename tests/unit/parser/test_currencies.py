"""Sprint E6 unit tests — ISO 4217 offline dataset (currencies.py)."""
from app.services.parser.currencies import (
    CURRENCIES,
    exponent_for,
    is_known_code,
)


def test_dataset_integrity():
    """Every entry: 3-letter uppercase code, name string, exponent in the
    ISO 4217 minor-unit set {0, 2, 3, 4}."""
    for code, (name, exponent) in CURRENCIES.items():
        assert len(code) == 3 and code.isalpha() and code.isupper(), code
        assert isinstance(name, str) and name, code
        assert exponent in (0, 2, 3, 4), (code, exponent)


def test_spot_checks():
    assert CURRENCIES["JPY"] == ("Yen", 0)
    assert CURRENCIES["INR"] == ("Indian Rupee", 2)
    assert CURRENCIES["USD"] == ("US Dollar", 2)
    assert CURRENCIES["EUR"] == ("Euro", 2)
    assert CURRENCIES["GBP"] == ("Pound Sterling", 2)
    assert CURRENCIES["KWD"] == ("Kuwaiti Dinar", 3)
    assert CURRENCIES["CLF"][1] == 4
    assert CURRENCIES["KRW"][1] == 0


def test_known_and_unknown_codes():
    assert is_known_code("JPY") and is_known_code("jpy")
    assert is_known_code("USD")
    assert not is_known_code("XYZ")   # not an ISO 4217 code
    assert not is_known_code("GST")   # looks plausible, is not
    assert not is_known_code(None)
    assert not is_known_code("")


def test_exponent_helper():
    assert exponent_for("JPY") == 0
    assert exponent_for("KWD") == 3
    assert exponent_for("USD") == 2
    assert exponent_for("INR") == 2
    assert exponent_for("XYZ") is None
