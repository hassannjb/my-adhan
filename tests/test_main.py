```python
import pytest
from datetime import datetime, timedelta
import os
import json

# Assuming AdhanClockApp is in the main.py file in the root directory
from main import AdhanClockApp

# --- Fixture for creating dummy prayer times file ---
# Moved to conftest.py

# --- Tests for AdhanClockApp ---

def test_init_default_filepath(mock_prayer_times_file):
    """Test initialization with default filepath."""
    # Temporarily change the working directory to ensure default path is used correctly
    original_cwd = os.getcwd()
    os.chdir(os.path.dirname(mock_prayer_times_file))
    try:
        app = AdhanClockApp()
        # Check if it loaded the default file correctly (assuming the mock fixture created it)
        assert app.prayer_times is not None
        assert app.prayer_times_filepath == "adhan_times.json"
    finally:
        os.chdir(original_cwd) # Restore original working directory


def test_init_custom_filepath(mock_prayer_times_file):
    """Test initialization with a custom filepath."""
    app = AdhanClockApp(prayer_times_filepath=mock_prayer_times_file)
    assert app.prayer_times is not None
    assert app.prayer_times_filepath == str(mock_prayer_times_file)

def test_load_prayer_times_success(mock_prayer_times_file):
    """Test successful loading of prayer times."""
    app = AdhanClockApp(prayer_times_filepath=mock_prayer_times_file)
    assert app.prayer_times is not None
    assert "Fajr" in app.prayer_times
    assert app.prayer_times["Fajr"] == "05:00"

def test_load_prayer_times_file_not_found():
    """Test loading when the prayer times file does not exist."""
    non_existent_file = "non_existent_adhan_times.json"
    app = AdhanClockApp(prayer_times_filepath=non_existent_file)
    assert app.prayer_times is None

def test_load_prayer_times_malformed_data(malformed_prayer_times_file):
    """Test loading with a JSON file missing expected prayer keys."""
    app = AdhanClockApp(prayer_times_filepath=malformed_prayer_times_file)
    assert app.prayer_times is None

def test_load_prayer_times_invalid_json(invalid_json_file):
    """Test loading with a file containing invalid JSON."""
    app = AdhanClockApp(prayer_times_filepath=invalid_json_file)
    assert app.prayer_times is None

def test_load_prayer_times_invalid_time_format(invalid_time_format_file):
    """Test loading with a file containing invalid time format for a prayer."""
    # The app should still load, but warn and potentially exclude the invalid entry
    app = AdhanClockApp(prayer_times_filepath=invalid_time_format_file)
    assert app.prayer_times is not None
    assert app.prayer_times["Fajr"] == "05:00"
    # The invalid "Asr" time should be handled, but the rest should load.
    # The get_next_prayer_info should gracefully handle missing/invalid times.

def test_get_next_prayer_info_before_fajr(mock_prayer_times_file):
    """Test when current time is before Fajr."""
    app = AdhanClockApp(prayer_times_filepath=mock_prayer_times_file)
    current_dt = datetime(2023, 10, 27, 3, 0) # 3 AM
    next_prayer_name, next_prayer_time_str, next_prayer_dt_obj = app.get_next_prayer_info(current_dt)
    assert next_prayer_name == "Fajr"
    assert next_prayer_time_str == "05:00"
    assert next_prayer_dt_obj == datetime(2023, 10, 27, 5, 0)

def test_get_next_prayer_info_after_fajr_before_dhuhr(mock_prayer_times_file):
    """Test when current time is after Fajr but before Dhuhr."""
    app = AdhanClockApp(prayer_times_filepath=mock_prayer_times_file)
    current_dt = datetime(2023, 10, 27, 7, 0) # 7 AM
    next_prayer_name, next_prayer_time_str, next_prayer_dt_obj = app.get_next_prayer_info(current_dt)
    assert next_prayer_name == "Dhuhr"
    assert next_prayer_time_str == "13:00"
    assert next_prayer_dt_obj == datetime(2023, 10, 27, 13, 0)

def test_get_next_prayer_info_exact_prayer_time(mock_prayer_times_file):
    """Test when current time is exactly a prayer time."""
    app = AdhanClockApp(prayer_times_filepath=mock_prayer_times_file)
    current_dt = datetime(2023, 10, 27, 13, 0) # Exactly Dhuhr time
    next_prayer_name, next_prayer_time_str, next_prayer_dt_obj = app.get_next_prayer_info(current_dt)
    # The logic should look for the *next* prayer after the current time.
    # If the current time is exactly a prayer time, the next prayer should be the one following it.
    assert next_prayer_name == "Asr"
    assert next_prayer_time_str == "16:00"
    assert next_prayer_dt_obj == datetime(2023, 10, 27, 16, 0)

def test_get_next_prayer_info_after_all_prayers_today_next_day_fajr(mock_prayer_times_file):
    """Test when current time is after all prayers of the day, should be Fajr of next day."""
    app = AdhanClockApp(prayer_times_filepath=mock_prayer_times_file)
    current_dt = datetime(2023, 10, 27, 23, 0) # 11 PM
    next_prayer_name, next_prayer_time_str, next_prayer_dt_obj = app.get_next_prayer_info(current_dt)
    assert next_prayer_name == "Fajr (Tomorrow)"
    assert next_prayer_time_str == "05:00"
    assert next_prayer_dt_obj == datetime(2023, 10, 28, 5, 0)

def test_get_next_prayer_info_no_prayer_times_loaded():
    """Test behavior when prayer_times is None."""
    app = AdhanClockApp() # This will not load times by default if file doesn't exist
    app.prayer_times = None # Explicitly set to None for this test
    current_dt = datetime.now()
    next_prayer_name, next_prayer_time_str, next_prayer_dt_obj = app.get_next_prayer_info(current_dt)
    assert next_prayer_name == "No prayer times loaded"
    assert next_prayer_time_str is None
    assert next_prayer_dt_obj is None

def test_get_next_prayer_info_malformed_fajr_for_tomorrow(invalid_time_format_file):
    """Test scenario where tomorrow's Fajr time is malformed."""
    # We need to create a specific file for this, or mock app.prayer_times
    # For simplicity, let's create a temporary file
    temp_dir = pytest.temp_test_dir
    malformed_fajr_file_path = temp_dir / "malformed_fajr.json"
    malformed_fajr_data = {
        "Fajr": "invalid-fajr-time", # Invalid format for Fajr
        "Dhuhr": "13:00",
        "Asr": "16:00",
        "Maghrib": "18:30",
        "Isha": "20:00"
    }
    with open(malformed_fajr_file_path, 'w') as f:
        json.dump(malformed_fajr_data, f, indent=4)

    app = AdhanClockApp(prayer_times_filepath=malformed_fajr_file_path)
    current_dt = datetime(2023, 10, 27, 23, 0) # After all prayers
    
    # Expecting a warning about invalid Fajr time, and then it should fall back
    # to the "All prayers done for today" message if tomorrow's Fajr can't be parsed.
    next_prayer_name, next_prayer_time_str, next_prayer_dt_obj = app.get_next_prayer_info(current_dt)
    
    # If Fajr is invalid, it falls through to the end of the loop.
    # If there are no other valid prayers or if the next day Fajr parsing fails,
    # it should return the fallback.
    assert next_prayer_name == "All prayers done for today"
    assert next_prayer_time_str is None
    assert next_prayer_dt_obj is None

def test_get_next_prayer_info_with_sunrise_sunset_ignored(mock_prayer_times_file):
    """Test that Sunrise and Sunset are correctly handled (or ignored if not in prayer_order)."""
    app = AdhanClockApp(prayer_times_filepath=mock_prayer_times_file)
    current_dt = datetime(2023, 10, 27, 6, 0) # After sunrise, before Dhuhr
    next_prayer_name, next_prayer_time_str, next_prayer_dt_obj = app.get_next_prayer_info(current_dt)
    
    # Sunrise and Sunset are in prayer_order but not considered 'prayers' to find next.
    # The logic should find Dhuhr.
    assert next_prayer_name == "Dhuhr"
    assert next_prayer_time_str == "13:00"
    assert next_prayer_dt_obj == datetime(2023, 10, 27, 13, 0)

def test_format_time_display_with_time():
    """Test formatting a prayer name and time."""
    app = AdhanClockApp()
    formatted = app.format_time_display("Fajr", "05:00")
    assert formatted == "Fajr: 05:00"

def test_format_time_display_without_time():
    """Test formatting a prayer name with no time string."""
    app = AdhanClockApp()
    formatted = app.format_time_display("Fajr", None)
    assert formatted == "Fajr: N/A"

def test_run_gui_output(capsys, mock_prayer_times_file):
    """Test the basic output of the run_gui method."""
    app = AdhanClockApp(prayer_times_filepath=mock_prayer_times_file)
    app.run_gui()
    captured = capsys.readouterr()

    assert "Starting Adhan Clock GUI..." in captured.out
    assert "Current time:" in captured.out
    assert "Next Prayer: Fajr at 05:00" in captured.out # Based on current_dt assumed by the test
    assert "GUI application logic would continue here..." in captured.out

def test_run_gui_output_no_times(capsys):
    """Test the basic output of run_gui when no prayer times are loaded."""
    app = AdhanClockApp() # Assumes no adhan_times.json exists or is invalid
    app.prayer_times = None # Ensure it's None for this test
    app.run_gui()
    captured = capsys.readouterr()

    assert "Starting Adhan Clock GUI..." in captured.out
    assert "Current time:" in captured.out
    assert "Next Prayer: No prayer times loaded at N/A" in captured.out
    assert "GUI application logic would continue here..." in captured.out
```
