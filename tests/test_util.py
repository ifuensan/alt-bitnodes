from queries.util import iso2_to_iso3


def test_valid_codes():
    assert iso2_to_iso3("US") == "USA"
    assert iso2_to_iso3("DE") == "DEU"


def test_unknown_code_returns_none():
    assert iso2_to_iso3("XX") is None


def test_empty_and_none_return_none():
    assert iso2_to_iso3("") is None
    assert iso2_to_iso3(None) is None
