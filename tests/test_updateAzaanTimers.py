import json
import os
import pytest
import requests
from unittest.mock import patch, MagicMock

from updateAzaanTimers import fetch_prayer_times, save_prayer_times, main

SAMPLE_RESPONSE = {
    "results": {
        "datetime": [{
            "times": {
                "Fajr": "05:00", "Sunrise": "06:15", "Dhuhr": "13:00",
                "Asr": "16:30", "Maghrib": "18:45", "Isha": "20:00",
            }
        }]
    }
}
EXPECTED_TIMES = SAMPLE_RESPONSE["results"]["datetime"][0]["times"]


@pytest.fixture
def mock_api(monkeypatch):
    def _get(*args, **kwargs):
        r = MagicMock()
        r.json.return_value = SAMPLE_RESPONSE
        r.raise_for_status.return_value = None
        return r
    monkeypatch.setattr("requests.get", _get)


@pytest.fixture
def mock_api_error(monkeypatch):
    def _get(*args, **kwargs):
        raise requests.exceptions.RequestException("connection refused")
    monkeypatch.setattr("requests.get", _get)


@pytest.fixture
def mock_api_empty(monkeypatch):
    def _get(*args, **kwargs):
        r = MagicMock()
        r.json.return_value = {"results": {"datetime": []}}
        r.raise_for_status.return_value = None
        return r
    monkeypatch.setattr("requests.get", _get)


# ── fetch_prayer_times ────────────────────────────────────────────────────────

def test_fetch_returns_times_on_success(mock_api):
    assert fetch_prayer_times("London", "UK", "2") == EXPECTED_TIMES


def test_fetch_passes_correct_params_to_api(monkeypatch):
    captured = {}

    def _get(url, params=None, timeout=None):
        captured["params"] = params
        r = MagicMock()
        r.json.return_value = SAMPLE_RESPONSE
        r.raise_for_status.return_value = None
        return r

    monkeypatch.setattr("requests.get", _get)
    fetch_prayer_times("Cairo", "Egypt", "5")
    assert captured["params"] == {"city": "Cairo", "country": "Egypt", "method": "5"}


def test_fetch_returns_none_on_request_error(mock_api_error):
    assert fetch_prayer_times("London", "UK", "2") is None


def test_fetch_returns_none_when_datetime_list_is_empty(mock_api_empty):
    assert fetch_prayer_times("London", "UK", "2") is None


def test_fetch_returns_none_on_invalid_json(monkeypatch):
    def _get(*args, **kwargs):
        r = MagicMock()
        r.json.side_effect = json.JSONDecodeError("bad json", "doc", 0)
        r.raise_for_status.return_value = None
        return r

    monkeypatch.setattr("requests.get", _get)
    assert fetch_prayer_times("London", "UK", "2") is None


# ── save_prayer_times ─────────────────────────────────────────────────────────

def test_save_writes_correct_json(tmp_path):
    out = str(tmp_path / "times.json")
    assert save_prayer_times(out, EXPECTED_TIMES) is True
    with open(out) as f:
        assert json.load(f) == EXPECTED_TIMES


def test_save_returns_false_for_none_data():
    assert save_prayer_times("irrelevant.json", None) is False


def test_save_returns_false_for_empty_dict():
    assert save_prayer_times("irrelevant.json", {}) is False


def test_save_creates_intermediate_directories(tmp_path):
    out = str(tmp_path / "subdir" / "nested" / "times.json")
    assert save_prayer_times(out, EXPECTED_TIMES) is True
    assert os.path.exists(out)


def test_save_returns_false_on_io_error(tmp_path):
    out = str(tmp_path / "times.json")
    with patch("builtins.open", side_effect=IOError("disk full")):
        assert save_prayer_times(out, EXPECTED_TIMES) is False


# ── main (CLI) ────────────────────────────────────────────────────────────────

def test_main_saves_to_specified_output_file(mock_api, tmp_path):
    out = str(tmp_path / "result.json")
    with patch("sys.argv", ["prog", "--city", "London", "--country", "UK", "--output", out]):
        main()
    with open(out) as f:
        assert json.load(f) == EXPECTED_TIMES


def test_main_uses_default_method_2(mock_api, monkeypatch, tmp_path):
    captured = {}
    original = fetch_prayer_times

    def spy(city, country, method):
        captured["method"] = method
        return original(city, country, method)

    monkeypatch.setattr("updateAzaanTimers.fetch_prayer_times", spy)
    out = str(tmp_path / "result.json")
    with patch("sys.argv", ["prog", "--city", "London", "--country", "UK", "--output", out]):
        main()
    assert captured["method"] == "2"


def test_main_prints_failure_and_no_file_on_api_error(mock_api_error, tmp_path, capsys):
    out = str(tmp_path / "result.json")
    with patch("sys.argv", ["prog", "--city", "X", "--country", "Y", "--output", out]):
        main()
    assert "Failed to retrieve or save prayer times." in capsys.readouterr().out
    assert not os.path.exists(out)


def test_main_default_output_file(mock_api, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with patch("sys.argv", ["prog", "--city", "London", "--country", "UK"]):
        main()
    assert (tmp_path / "adhan_times.json").exists()
