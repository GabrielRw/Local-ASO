"""Normalization and local input validation tests."""

import pytest

from local_aso_tracker.config import (
    config_path,
    load_settings,
    update_settings,
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


def test_agent_provider_setting_is_validated_and_persisted(
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASO_DATA_DIR", str(tmp_path))
    path = write_default_config()
    path.write_text(path.read_text(encoding="utf-8") + "# keep this comment\n", encoding="utf-8")
    updates = update_settings(agent_provider="claude")
    assert updates.agent_provider == "claude"
    assert load_settings().agent_provider == "claude"
    assert "# keep this comment" in config_path().read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="unknown setting"):
        update_settings(not_a_setting=True)
