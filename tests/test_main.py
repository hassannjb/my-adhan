"""
Tests for the adhan domain package — config, models, and calculator.
These are pure unit tests: no network, no GUI, no audio.
"""
import json
from datetime import date
from pathlib import Path

import pytz
import pytest
from unittest.mock import patch

from adhan.models import Config, Coordinates, PrayerSchedule
from adhan.config import load_config, save_config
from adhan.calculator import build_params, calculate


# ── adhan.models ──────────────────────────────────────────────────────────────

def test_config_defaults():
    c = Config()
    assert c.fajr_angle == 15.0
    assert c.isha_angle == 15.0
    assert c.method == "NORTH_AMERICA"
    assert c.city == "Unknown"


def test_config_to_dict_round_trips():
    c = Config(city="London", method="ISNA", fajr_angle=18.0, isha_angle=17.0)
    d = c.to_dict()
    assert d["city"] == "London"
    assert d["method"] == "ISNA"
    assert d["fajr_angle"] == 18.0


def test_coordinates_are_frozen():
    coords = Coordinates(51.5, -0.1)
    with pytest.raises(Exception):
        coords.latitude = 0.0  # frozen dataclass


def test_prayer_schedule_as_dict_returns_six_keys():
    tz = pytz.UTC
    d = date(2024, 1, 1)
    from datetime import datetime, timezone
    now = datetime(2024, 1, 1, 6, 0, tzinfo=tz)
    schedule = PrayerSchedule(
        date=d, fajr=now, sunrise=now, dhuhr=now,
        asr=now, maghrib=now, isha=now, timezone_name="UTC",
    )
    times = schedule.as_dict()
    assert set(times.keys()) == {"Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"}


def test_prayer_schedule_next_after_returns_next():
    tz = pytz.UTC
    from datetime import datetime, timedelta
    base = datetime(2024, 1, 1, 8, 0, tzinfo=tz)
    schedule = PrayerSchedule(
        date=base.date(),
        fajr=base - timedelta(hours=3),
        sunrise=base - timedelta(hours=2),
        dhuhr=base + timedelta(hours=4),
        asr=base + timedelta(hours=7),
        maghrib=base + timedelta(hours=9),
        isha=base + timedelta(hours=11),
        timezone_name="UTC",
    )
    name, dt = schedule.next_after(base)
    assert name == "Dhuhr"
    assert dt == base + timedelta(hours=4)


def test_prayer_schedule_next_after_returns_none_when_all_done():
    tz = pytz.UTC
    from datetime import datetime, timedelta
    base = datetime(2024, 1, 1, 23, 0, tzinfo=tz)
    schedule = PrayerSchedule(
        date=base.date(),
        fajr=base - timedelta(hours=17),
        sunrise=base - timedelta(hours=16),
        dhuhr=base - timedelta(hours=10),
        asr=base - timedelta(hours=7),
        maghrib=base - timedelta(hours=5),
        isha=base - timedelta(hours=2),
        timezone_name="UTC",
    )
    assert schedule.next_after(base) is None


# ── adhan.config ──────────────────────────────────────────────────────────────

def test_load_config_missing_file_returns_defaults(tmp_path):
    c = load_config(tmp_path / "nonexistent.json")
    assert c.method == "NORTH_AMERICA"
    assert c.fajr_angle == 15.0


def test_load_config_reads_values(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "method": "EGYPTIAN",
        "fajr_angle": 19.5,
        "isha_angle": 17.5,
        "city": "Cairo",
    }))
    c = load_config(p)
    assert c.method == "EGYPTIAN"
    assert c.fajr_angle == 19.5
    assert c.city == "Cairo"


def test_load_config_malformed_json_returns_defaults(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{bad json")
    c = load_config(p)
    assert c.method == "NORTH_AMERICA"


def test_save_and_reload_config(tmp_path):
    p = tmp_path / "config.json"
    original = Config(method="MWL", fajr_angle=18.0, isha_angle=17.0, city="London")
    save_config(original, p)
    reloaded = load_config(p)
    assert reloaded.method == "MWL"
    assert reloaded.fajr_angle == 18.0
    assert reloaded.city == "London"


# ── adhan.calculator ──────────────────────────────────────────────────────────

@pytest.fixture
def london_params():
    return build_params(Config(method="NORTH_AMERICA", fajr_angle=15.0, isha_angle=15.0))


@pytest.fixture
def london_coords():
    return Coordinates(latitude=51.5074, longitude=-0.1278)


def test_calculate_returns_prayer_schedule(london_coords, london_params):
    tz = pytz.timezone("Europe/London")
    schedule = calculate(date(2024, 6, 1), london_coords, london_params, tz)
    assert isinstance(schedule, PrayerSchedule)
    assert schedule.date == date(2024, 6, 1)
    assert schedule.timezone_name == "Europe/London"


def test_calculate_times_are_in_correct_order(london_coords, london_params):
    tz = pytz.timezone("Europe/London")
    s = calculate(date(2024, 6, 1), london_coords, london_params, tz)
    assert s.fajr < s.sunrise < s.dhuhr < s.asr < s.maghrib < s.isha


def test_calculate_times_are_timezone_aware(london_coords, london_params):
    tz = pytz.timezone("Europe/London")
    s = calculate(date(2024, 6, 1), london_coords, london_params, tz)
    assert s.fajr.tzinfo is not None
    assert s.isha.tzinfo is not None


def test_build_params_uses_correct_method():
    from adhanpy.calculation.CalculationMethod import CalculationMethod
    params = build_params(Config(method="NORTH_AMERICA"))
    assert params.method == CalculationMethod.NORTH_AMERICA


def test_build_params_unknown_method_falls_back_to_north_america():
    from adhanpy.calculation.CalculationMethod import CalculationMethod
    params = build_params(Config(method="NONEXISTENT_METHOD"))
    assert params.method == CalculationMethod.NORTH_AMERICA
