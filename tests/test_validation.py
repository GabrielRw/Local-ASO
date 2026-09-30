"""Normalization and local input validation tests."""

import pytest

from local_aso_tracker.config import (
    load_settings,
    validate_country_code,
    validate_device,
    write_default_config,
)
from local_aso_tracker.repositories.data import normalize_keyword


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" Learn   Astrology ", "learn astrology"),
        ("ZODIAC SIGNS", "zodiac signs"),
        ("Étoiles", "étoiles"),
    ],
)
def test_keyword_normalization(raw: str, expected: str) -> None:
    assert normalize_keyword(raw) == expected


@pytest.mark.parametrize("raw", ["", "u", "usa", "1s", "éu"])
def test_country_validation_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(ValueError, match="two ASCII letters"):
        validate_country_code(raw)


def test_country_validation_normalizes_case_and_space() -> None:
    assert validate_country_code(" US ") == "us"


def test_device_validation_is_explicit() -> None:
    assert validate_device(" iPad ") == "ipad"
    with pytest.raises(ValueError, match=r"iphone.*ipad"):
        validate_device("android")


def test_default_config_is_valid_toml(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    path = write_default_config()
    assert path.exists()
    assert load_settings().result_limit == 200
