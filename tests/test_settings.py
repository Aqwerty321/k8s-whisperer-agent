import pytest

from backend.app.config import Settings


def test_settings_accept_empty_observed_namespaces_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSERVED_NAMESPACES", "")
    settings = Settings()

    assert settings.observed_namespaces == []


def test_settings_split_comma_separated_observed_namespaces(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSERVED_NAMESPACES", "default,payments , team-b")
    settings = Settings()

    assert settings.observed_namespaces == ["default", "payments", "team-b"]
