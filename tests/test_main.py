```python
import pytest
from unittest.mock import patch, mock_open
import json
from datetime import datetime, timedelta
import os

# Assume main.py exists at the root of the project and is importable.
# If not, adjust sys.path or project structure for imports to work.
import main as adhan_app # Renamed to avoid name collision with test 'main' functions

# Mock prayer times data for file loading tests
MOCK_PRAYER_TIMES_DATA = {
    "Fajr": "05:00",
    "Sunrise": "06:30",
    "Dhuhr": "12:30",
    "Asr": "16:00",
    "Sunset": "17:45",
    "Maghrib": "18:00",
    "Isha": "20:00"
}

@pytest.fixture
def mock_prayer_times_file(tmp_path):
    """Fixture to create a temporary adhan_times.json file for tests."""
    file_path = tmp_path / "adhan_times.json"
    with open(file_path, 'w') as f:
        json.dump(MOCK_PRAYER_TIMES_DATA, f)
    # Patch the PRAYER_TIMES_FILE constant in the main module
    # so that AdhanClockApp picks up our temp file.
    with patch('main.PRAYER_TIMES_FILE', str(file_path)):
        yield file_path

@pytest.fixture
def app_with_mock_times(mock_prayer_times_file):
    """Fixture providing an AdhanClockApp instance with loaded prayer times."""
    return adhan_app.AdhanClockApp()


# --- Tests for _load_prayer_times method ---
def test_load_prayer_times_success(app_with_mock_times):
    """Test successful loading of prayer times from a valid JSON file."""
    assert app_with_mock_times.prayer_times == MOCK_PRAYER_TIMES_DATA

def test_load_prayer_times_file_not_found():
    """Test loading prayer times when the file does not exist."""
    # Ensure no file exists at the mocked path
    with patch('main.PRAYER_TIMES_FILE', 'non_existent.json'):
        app = adhan_app.AdhanClockApp()
        assert app.prayer_times is None

def test_load_prayer_times_invalid_json(tmp_path):
    """Test loading prayer times from a malformed JSON file."""
    file_path = tmp_path / "malformed_adhan_times.json"
    file_path.write_text("this is not json")
    with patch('main.PRAYER_TIMES_FILE', str(file_path)):
        app = adhan_app.AdhanClockApp()
        assert app.prayer_times is None

def test_load_prayer_times_incomplete_data(tmp_path):
    """Test loading prayer times with missing required prayer keys."""
    file_path = tmp_path / "incomplete_adhan_times.json"
    incomplete_data = {"Fajr": "05:00", "Dhuhr": "12:30"} # Missing Asr, Maghrib, Isha
    with open(file_path, 'w') as f:
        json.dump(incomplete_data, f)
    with patch('main.PRAYER_TIMES_FILE', str(file_path)):
        app = adhan_app.AdhanClockApp()
        assert app.prayer_times is None # Should return None if required keys are missing


# --- Tests for get_next_prayer_info method ---
def test_get_next_prayer_fajr(app_with_mock_times):
    """Test next prayer is Fajr when current time is before Fajr."""
    current_time = datetime(2023, 3, 15, 4, 0) # 4:00 AM
    name, time_str, dt_obj = app_with_mock_times.get_next_prayer_info(current_time)
    assert name == "Fajr"
    assert time_str == "05:00"
    assert dt_obj == datetime(2023, 3, 15, 5, 0)

def test_get_next_prayer_dhuhr(app_with_mock_times):
    """Test next prayer is Dhuhr when current time is after Sunrise but before Dhuhr."""
    current_time = datetime(2023, 3, 15, 7, 0) # 7:00 AM
    name, time_str, dt_obj = app_with_mock_times.get_next_prayer_info(current_time)
    assert name == "Dhuhr"
    assert time_str == "12:30"
    assert dt_obj == datetime(2023, 3, 15, 12, 30)

def test_get_next_prayer_isha(app_with_mock_times):
    """Test next prayer is Isha when current time is after Maghrib but before Isha."""
    current_time = datetime(2023, 3, 15, 18, 30) # 6:30 PM
    name, time_str, dt_obj = app_with_mock_times.get_next_prayer_info(current_time)
    assert name == "Isha"
    assert time_str == "20:00"
    assert dt_obj == datetime(2023, 3, 15, 20, 0)

def test_get_next_prayer_all_done_for_today(app_with_mock_times):
    """Test next prayer is Fajr (Tomorrow) when all prayers for today are passed."""
    current_time = datetime(2023, 3, 15, 21, 0) # 9:00 PM
    name, time_str, dt_obj = app_with_mock_times.get_next_prayer_info(current_time)
    assert name == "Fajr (Tomorrow)"
    assert time_str == "05:00" # Still shows today's Fajr time for tomorrow's prayer
    assert dt_obj == datetime(2023, 3, 16, 5, 0)

def test_get_next_prayer_at_prayer_time(app_with_mock_times):
    """Test behavior when current time is exactly a prayer time (should show next one)."""
    current_time = datetime(2023, 3, 15, 5, 0) # Exactly Fajr time
    name, time_str, dt_obj = app_with_mock_times.get_next_prayer_info(current_time)
    assert name == "Sunrise" # Should show Sunrise, as Fajr has just started/passed
    assert time_str == "06:30"

def test_get_next_prayer_no_prayer_times_loaded():
    """Test when no prayer times are loaded (e.g., file not found)."""
    # Create an app instance without loading any times
    with patch('main.PRAYER_TIMES_FILE', 'non_existent.json'):
        app = adhan_app.AdhanClockApp() # prayer_times will be None
        name, time_str, dt_obj = app.get_next_prayer_info(datetime.now())
        assert name == "No prayer times loaded"
        assert time_str is None
        assert dt_obj is None

def test_get_next_prayer_invalid_time_format_in_data(tmp_path):
    """Test robustness against invalid time formats in the loaded data."""
    file_path = tmp_path / "bad_time_format.json"
    bad_data = MOCK_PRAYER_TIMES_DATA.copy()
    bad_data["Dhuhr"] = "not_a_time" # Malformed Dhuhr time
    with open(file_path, 'w') as f:
        json.dump(bad_data, f)

    with patch('main.PRAYER_TIMES_FILE', str(file_path)):
        app = adhan_app.AdhanClockApp()
        # Ensure that Dhuhr is skipped and Asr is correctly identified as next
        current_time = datetime(2023, 3, 15, 10, 0) # Before Dhuhr
        name, time_str, dt_obj = app.get_next_prayer_info(current_time)
        assert name == "Asr" # Should skip Dhuhr (due to parsing error) and find Asr
        assert time_str == "16:00"


# --- Tests for format_time_display method ---
def test_format_time_display_valid():
    """Test formatting a valid prayer time."""
    app = adhan_app.AdhanClockApp() # Doesn't strictly need times loaded for this method
    assert app.format_time_display("Fajr", "05:00") == "Fajr: 05:00"

def test_format_time_display_none_time():
    """Test formatting with a None time string."""
    app = adhan_app.AdhanClockApp()
    assert app.format_time_display("Fajr", None) == "Fajr: N/A"

# --- Test run_gui (smoke test for its print output) ---
def test_run_gui_output(app_with_mock_times, capsys):
    """
    A basic smoke test for the run_gui method to ensure it prints expected messages.
    Note: Full GUI testing would require a different framework.
    """
    current_time = datetime(2023, 3, 15, 10, 0) # Example time
    with patch('main.datetime') as mock_dt:
        mock_dt.now.return_value = current_time
        mock_dt.strptime = datetime.strptime # Preserve original strptime
        mock_dt.timedelta = timedelta # Preserve original timedelta

        app_with_mock_times.run_gui()
        captured = capsys.readouterr()

        assert "Starting Adhan Clock GUI..." in captured.out
        assert f"Current time: {current_time.strftime('%H:%M:%S')}" in captured.out
        # Based on MOCK_PRAYER_TIMES_DATA and current_time 10:00, next prayer is Dhuhr at 12:30
        assert "Next Prayer: Dhuhr at 12:30" in captured.out
        assert "GUI application logic would continue here..." in captured.out
```
