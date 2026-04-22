"""MLflow client filter-string + name-safety regression tests.

Guards the two one-line-fix spots that have bitten the platform before:

* find_run_by_platform_id MUST backtick-quote the ``platform.run_id``
  tag key. The dotted tag name is otherwise parsed as three tokens by
  MLflow's filter-string parser and every lookup silently returns [] —
  that was the Batch 35e staging outage.
* search_model_versions MUST reject names that contain quote chars or
  backslashes before interpolating them into the ``name='<name>'``
  filter — Batch 35b+36 follow-up closed an injection surface where an
  admin-triggered rename could broaden cross-tenant version visibility.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_find_run_by_platform_id_uses_backticked_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aipacken.services import mlflow_client as svc

    mock_client = MagicMock()
    # Make both search_experiments and search_runs return "found something"
    # so the helper reaches the filter construction path.
    exp = MagicMock(experiment_id="exp-1")
    mock_client.search_experiments.return_value = [exp]
    fake_run = MagicMock()
    fake_run.info.run_id = "mlflow-run-abc"
    mock_client.search_runs.return_value = [fake_run]

    # Bypass feature-flag + lru_cache client bootstrap.
    svc.get_client.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setattr(svc, "get_client", lambda: mock_client)

    result = svc.find_run_by_platform_id("019db6a3-86e6-703f-9e40-079e89985c6b")
    assert result is fake_run

    # Assert backticks present — the literal string that broke Batch 35e
    # would be ``filter_string="tags.platform.run_id = '...'"`` (no ticks),
    # which MLflow's parser tokenizes as three identifiers.
    assert mock_client.search_runs.call_count == 1
    kwargs = mock_client.search_runs.call_args.kwargs
    fs = kwargs.get("filter_string", "")
    assert "tags.`platform.run_id`" in fs, f"regression: missing backticks in {fs!r}"


@pytest.mark.parametrize(
    "bad_name",
    [
        "foo' OR name LIKE '%",
        "foo\\bar",
        "foo\nbar",
        "foo;drop",
        "foo`bar",
        'foo"bar',
        "",
    ],
)
def test_search_model_versions_rejects_unsafe_names(
    bad_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aipacken.services import mlflow_client as svc

    mock_client = MagicMock()
    svc.get_client.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setattr(svc, "get_client", lambda: mock_client)

    # The helper must return [] and never call the underlying search.
    result = svc.search_model_versions(bad_name)
    assert result == []
    mock_client.search_model_versions.assert_not_called()


def test_search_model_versions_accepts_safe_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aipacken.services import mlflow_client as svc

    mock_client = MagicMock()
    mv = MagicMock(version="1")
    mock_client.search_model_versions.return_value = [mv]
    svc.get_client.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setattr(svc, "get_client", lambda: mock_client)

    result = svc.search_model_versions("sklearn_logistic-run-abcd1234")
    assert result == [mv]
    mock_client.search_model_versions.assert_called_once_with(
        "name='sklearn_logistic-run-abcd1234'"
    )


def test_assert_safe_model_name_happy_path() -> None:
    from aipacken.services.mlflow_client import _assert_safe_model_name

    _assert_safe_model_name("xgboost-run-019db6a3")
    _assert_safe_model_name("my.model_v2")  # dots/underscores are fine


@pytest.mark.parametrize("bad_name", ["foo'x", 'foo"x', "foo\\x", "foo\nx", "foo\x00", ""])
def test_assert_safe_model_name_raises(bad_name: str) -> None:
    from aipacken.services.mlflow_client import _assert_safe_model_name

    with pytest.raises(ValueError):
        _assert_safe_model_name(bad_name)
