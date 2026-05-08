"""Tests for adhan.location — no Qt or adhan stubs needed."""
from unittest.mock import MagicMock, patch

import pytz

from adhan.location import get_current_location


def _mock_response(data):
    r = MagicMock()
    r.json.return_value = data
    return r


def test_get_current_location_success(monkeypatch):
    monkeypatch.setattr(
        "requests.get",
        lambda *a, **kw: _mock_response(
            {"status": "success", "lat": 51.5, "lon": -0.1,
             "timezone": "Europe/London", "city": "London"}
        ),
    )
    coords, tz, city = get_current_location()
    assert coords.latitude == 51.5
    assert coords.longitude == -0.1
    assert tz == pytz.timezone("Europe/London")
    assert city == "London"


def test_get_current_location_api_failure(monkeypatch):
    monkeypatch.setattr(
        "requests.get",
        lambda *a, **kw: _mock_response({"status": "fail"}),
    )
    coords, tz, city = get_current_location()
    assert coords.latitude == 0.0
    assert tz == pytz.UTC
    assert city == "Offline"


def test_get_current_location_network_error(monkeypatch):
    def _raise(*a, **kw):
        raise ConnectionError("refused")

    monkeypatch.setattr("requests.get", _raise)
    coords, tz, city = get_current_location()
    assert city == "Offline"
    assert tz == pytz.UTC
