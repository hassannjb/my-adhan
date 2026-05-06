import json
import pytest
from datetime import datetime

from main import AdhanClockApp, PRAYER_TIMES_FILE

VALID_TIMES = {
    "Fajr": "05:00", "Sunrise": "06:15", "Dhuhr": "13:00",
    "Asr": "16:30", "Sunset": "18:30", "Maghrib": "18:30", "Isha": "20:00",
}


@pytest.fixture
def times_file(tmp_path):
    p = tmp_path / "adhan_times.json"
    p.write_text(json.dumps(VALID_TIMES))
    return str(p)


@pytest.fixture
def app(times_file):
    return AdhanClockApp(prayer_times_filepath=times_file)


# ── _load_prayer_times ────────────────────────────────────────────────────────

def test_load_file_not_found(tmp_path):
    a = AdhanClockApp(prayer_times_filepath=str(tmp_path / "missing.json"))
    assert a.prayer_times is None


def test_load_malformed_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json")
    a = AdhanClockApp(prayer_times_filepath=str(p))
    assert a.prayer_times is None


def test_load_missing_required_keys(tmp_path):
    # Fajr only — Dhuhr, Asr, Maghrib, Isha are missing
    p = tmp_path / "partial.json"
    p.write_text(json.dumps({"Fajr": "05:00", "Sunrise": "06:00"}))
    a = AdhanClockApp(prayer_times_filepath=str(p))
    assert a.prayer_times is None


def test_load_valid_file(app):
    assert app.prayer_times == VALID_TIMES


def test_reload_picks_up_updated_file(times_file):
    a = AdhanClockApp(prayer_times_filepath=times_file)
    updated = {**VALID_TIMES, "Fajr": "04:45"}
    with open(times_file, "w") as f:
        json.dump(updated, f)
    assert a._load_prayer_times()["Fajr"] == "04:45"


def test_default_filepath_constant():
    assert PRAYER_TIMES_FILE == "adhan_times.json"


# ── get_next_prayer_info ──────────────────────────────────────────────────────

def test_next_prayer_no_times_loaded(tmp_path):
    a = AdhanClockApp(prayer_times_filepath=str(tmp_path / "missing.json"))
    name, t, dt = a.get_next_prayer_info(datetime(2023, 10, 27, 12, 0))
    assert name == "No prayer times loaded"
    assert t is None
    assert dt is None


def test_next_prayer_before_fajr(app):
    name, t, dt = app.get_next_prayer_info(datetime(2023, 10, 27, 4, 0))
    assert name == "Fajr"
    assert t == "05:00"
    assert dt == datetime(2023, 10, 27, 5, 0)


def test_next_prayer_between_prayers(app):
    name, t, dt = app.get_next_prayer_info(datetime(2023, 10, 27, 14, 0))
    assert name == "Asr"
    assert t == "16:30"
    assert dt == datetime(2023, 10, 27, 16, 30)


def test_next_prayer_exactly_at_prayer_time_advances_to_next(app):
    # Strict > comparison means being exactly at Dhuhr skips it
    name, t, _ = app.get_next_prayer_info(datetime(2023, 10, 27, 13, 0))
    assert name == "Asr"
    assert t == "16:30"


def test_next_prayer_after_isha_wraps_to_tomorrow_fajr(app):
    name, t, dt = app.get_next_prayer_info(datetime(2023, 10, 27, 21, 0))
    assert name == "Fajr (Tomorrow)"
    assert t == "05:00"
    assert dt == datetime(2023, 10, 28, 5, 0)


def test_next_prayer_skips_entry_with_invalid_time_format(tmp_path):
    data = {**VALID_TIMES, "Sunrise": "not-a-time"}
    p = tmp_path / "times.json"
    p.write_text(json.dumps(data))
    a = AdhanClockApp(prayer_times_filepath=str(p))
    # At 12:00, Sunrise (invalid) is skipped; Dhuhr at 13:00 is next
    name, t, _ = a.get_next_prayer_info(datetime(2023, 10, 27, 12, 0))
    assert name == "Dhuhr"
    assert t == "13:00"


def test_next_prayer_invalid_fajr_returns_all_done(tmp_path):
    data = {**VALID_TIMES, "Fajr": "bad-time"}
    p = tmp_path / "times.json"
    p.write_text(json.dumps(data))
    a = AdhanClockApp(prayer_times_filepath=str(p))
    # After all prayers for today, tries tomorrow's Fajr but it can't be parsed
    name, t, dt = a.get_next_prayer_info(datetime(2023, 10, 27, 21, 0))
    assert name == "All prayers done for today"
    assert t is None
    assert dt is None


# ── format_time_display ───────────────────────────────────────────────────────

def test_format_with_valid_time(app):
    assert app.format_time_display("Fajr", "05:00") == "Fajr: 05:00"


def test_format_with_none_time_shows_na(app):
    assert app.format_time_display("Maghrib", None) == "Maghrib: N/A"


# ── run_gui ───────────────────────────────────────────────────────────────────

def test_run_gui_prints_expected_output(app, capsys):
    app.run_gui()
    out = capsys.readouterr().out
    assert "Starting Adhan Clock GUI..." in out
    assert "Current time:" in out
    assert "Next Prayer:" in out
    assert "GUI application logic would continue here..." in out
