```python
import pytest
from datetime import datetime, timedelta
import os
import json

from main import AdhanClockApp, PRAYER_TIMES_FILE

# Helper to create a dummy prayer times file
def create_dummy_prayer_times_file(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)

# Helper to remove a dummy prayer times file
def remove_dummy_prayer_times_file(filepath):
    if os.path.exists(filepath):
        os.remove(filepath)
    # Clean up directory if it becomes empty
    try:
        os.rmdir(os.path.dirname(filepath))
    except OSError:
        pass # Directory not empty or doesn't exist

@pytest.fixture
def setup_app_with_file(tmp_path):
    """Fixture to set up AdhanClockApp with a temporary prayer times file."""
    test_filepath = tmp_path / "test_adhan_times.json"
    return AdhanClockApp(prayer_times_filepath=str(test_filepath)), str(test_filepath)

# Tests for AdhanClockApp
def test_init_with_default_filepath(tmp_path):
    """Test initialization with default filepath."""
    original_cwd = os.getcwd()
    os.chdir(tmp_path) # Change directory to temp path for default file creation
    app = AdhanClockApp()
    assert app.prayer_times_filepath == os.path.join(tmp_path, PRAYER_TIMES_FILE)
    os.chdir(original_cwd) # Change back

def test_init_with_custom_filepath(tmp_path):
    """Test initialization with a custom filepath."""
    custom_path = tmp_path / "custom" / "my_times.json"
    app = AdhanClockApp(prayer_times_filepath=str(custom_path))
    assert app.prayer_times_filepath == str(custom_path)

def test_load_prayer_times_file_not_found(tmp_path):
    """Test loading when the prayer times file does not exist."""
    app = AdhanClockApp(prayer_times_filepath=str(tmp_path / "non_existent.json"))
    # Temporarily redirect stdout to capture print statements if needed,
    # but for now we check the return value of _load_prayer_times
    assert app._load_prayer_times() is None

def test_load_prayer_times_malformed_json(setup_app_with_file, tmp_path):
    """Test loading when the prayer times file has malformed JSON."""
    app, test_filepath = setup_app_with_file
    with open(test_filepath, 'w') as f:
        f.write("{'Fajr': '05:00'") # Missing closing brace and invalid quotes
    
    assert app._load_prayer_times() is None

def test_load_prayer_times_missing_keys(setup_app_with_file, tmp_path):
    """Test loading when the prayer times file is missing expected prayer keys."""
    app, test_filepath = setup_app_with_file
    malformed_data = {"Fajr": "05:00", "Sunrise": "06:00"} # Missing Dhuhr, Asr, Maghrib, Isha
    create_dummy_prayer_times_file(test_filepath, malformed_data)
    
    assert app._load_prayer_times() is None

def test_load_prayer_times_invalid_time_format(setup_app_with_file, tmp_path):
    """Test loading when a prayer time has an invalid format."""
    app, test_filepath = setup_app_with_file
    invalid_data = {
        "Fajr": "05:00",
        "Dhuhr": "13:00",
        "Asr": "invalid-time", # Invalid format
        "Maghrib": "18:00",
        "Isha": "19:00"
    }
    create_dummy_prayer_times_file(test_filepath, invalid_data)
    
    loaded_times = app._load_prayer_times()
    assert loaded_times is not None
    # The function should still return the valid data even if one entry is invalid
    # and print a warning. The get_next_prayer_info will handle invalid times gracefully.

def test_load_prayer_times_success(setup_app_with_file, tmp_path):
    """Test successful loading of valid prayer times."""
    app, test_filepath = setup_app_with_file
    valid_data = {
        "Fajr": "05:00",
        "Sunrise": "06:15",
        "Dhuhr": "13:00",
        "Asr": "16:30",
        "Sunset": "18:30",
        "Maghrib": "18:30",
        "Isha": "20:00"
    }
    create_dummy_prayer_times_file(test_filepath, valid_data)
    
    loaded_times = app._load_prayer_times()
    assert loaded_times == valid_data

def test_get_next_prayer_info_no_times_loaded(setup_app_with_file, tmp_path):
    """Test get_next_prayer_info when no prayer times are loaded."""
    app, test_filepath = setup_app_with_file
    app.prayer_times = None # Explicitly set to None
    current_dt = datetime(2023, 10, 27, 12, 0, 0)
    name, time, dt_obj = app.get_next_prayer_info(current_dt)
    assert name == "No prayer times loaded"
    assert time is None
    assert dt_obj is None

def test_get_next_prayer_info_before_first_prayer(setup_app_with_file, tmp_path):
    """Test finding the next prayer when current time is before Fajr."""
    app, test_filepath = setup_app_with_file
    prayer_data = {
        "Fajr": "05:00", "Sunrise": "06:15", "Dhuhr": "13:00",
        "Asr": "16:30", "Sunset": "18:30", "Maghrib": "18:30", "Isha": "20:00"
    }
    create_dummy_prayer_times_file(test_filepath, prayer_data)
    app.prayer_times = app._load_prayer_times() # Reload after creating file

    current_dt = datetime(2023, 10, 27, 4, 0, 0) # Before Fajr
    name, time, dt_obj = app.get_next_prayer_info(current_dt)
    
    assert name == "Fajr"
    assert time == "05:00"
    assert dt_obj == datetime(2023, 10, 27, 5, 0, 0)

def test_get_next_prayer_info_after_last_prayer_same_day(setup_app_with_file, tmp_path):
    """Test finding the next prayer when current time is after all prayers for the day."""
    app, test_filepath = setup_app_with_file
    prayer_data = {
        "Fajr": "05:00", "Sunrise": "06:15", "Dhuhr": "13:00",
        "Asr": "16:30", "Sunset": "18:30", "Maghrib": "18:30", "Isha": "20:00"
    }
    create_dummy_prayer_times_file(test_filepath, prayer_data)
    app.prayer_times = app._load_prayer_times()

    current_dt = datetime(2023, 10, 27, 21, 0, 0) # After Isha
    name, time, dt_obj = app.get_next_prayer_info(current_dt)

    # Expecting Fajr of the next day
    assert name == "Fajr (Tomorrow)"
    assert time == "05:00"
    assert dt_obj == datetime(2023, 10, 28, 5, 0, 0)

def test_get_next_prayer_info_exactly_at_prayer_time(setup_app_with_file, tmp_path):
    """Test finding the next prayer when current time is exactly at a prayer time."""
    app, test_filepath = setup_app_with_file
    prayer_data = {
        "Fajr": "05:00", "Sunrise": "06:15", "Dhuhr": "13:00",
        "Asr": "16:30", "Sunset": "18:30", "Maghrib": "18:30", "Isha": "20:00"
    }
    create_dummy_prayer_times_file(test_filepath, prayer_data)
    app.prayer_times = app._load_prayer_times()

    current_dt = datetime(2023, 10, 27, 13, 0, 0) # Exactly Dhuhr time
    name, time, dt_obj = app.get_next_prayer_info(current_dt)

    # The next prayer should be Asr
    assert name == "Asr"
    assert time == "16:30"
    assert dt_obj == datetime(2023, 10, 27, 16, 30, 0)

def test_get_next_prayer_info_between_prayers(setup_app_with_file, tmp_path):
    """Test finding the next prayer when current time is between two prayers."""
    app, test_filepath = setup_app_with_file
    prayer_data = {
        "Fajr": "05:00", "Sunrise": "06:15", "Dhuhr": "13:00",
        "Asr": "16:30", "Sunset": "18:30", "Maghrib": "18:30", "Isha": "20:00"
    }
    create_dummy_prayer_times_file(test_filepath, prayer_data)
    app.prayer_times = app._load_prayer_times()

    current_dt = datetime(2023, 10, 27, 14, 0, 0) # After Dhuhr, before Asr
    name, time, dt_obj = app.get_next_prayer_info(current_dt)

    assert name == "Asr"
    assert time == "16:30"
    assert dt_obj == datetime(2023, 10, 27, 16, 30, 0)

def test_get_next_prayer_info_with_invalid_times_in_data(setup_app_with_file, tmp_path):
    """Test finding the next prayer when the loaded data has invalid time formats."""
    app, test_filepath = setup_app_with_file
    prayer_data = {
        "Fajr": "05:00",
        "Sunrise": "invalid", # Invalid
        "Dhuhr": "13:00",
        "Asr": "16:30",
        "Sunset": "18:30",
        "Maghrib": "18:30",
        "Isha": "20:00"
    }
    create_dummy_prayer_times_file(test_filepath, prayer_data)
    app.prayer_times = app._load_prayer_times()

    current_dt = datetime(2023, 10, 27, 12, 0, 0) # Before Dhuhr
    name, time, dt_obj = app.get_next_prayer_info(current_dt)
    
    # Sunrise should be skipped, Dhuhr is next
    assert name == "Dhuhr"
    assert time == "13:00"
    assert dt_obj == datetime(2023, 10, 27, 13, 0, 0)

def test_get_next_prayer_info_next_day_fajr_invalid_format(setup_app_with_file, tmp_path):
    """Test when next day's Fajr has an invalid format."""
    app, test_filepath = setup_app_with_file
    prayer_data = {
        "Fajr": "invalid-tomorrow", # Invalid format for tomorrow's Fajr
        "Sunrise": "06:15", "Dhuhr": "13:00",
        "Asr": "16:30", "Sunset": "18:30", "Maghrib": "18:30", "Isha": "20:00"
    }
    create_dummy_prayer_times_file(test_filepath, prayer_data)
    app.prayer_times = app._load_prayer_times()

    current_dt = datetime(2023, 10, 27, 21, 0, 0) # After Isha
    name, time, dt_obj = app.get_next_prayer_info(current_dt)

    # Should fall back to the "All prayers done for today" message because tomorrow's Fajr is malformed.
    assert name == "All prayers done for today"
    assert time is None
    assert dt_obj is None

def test_get_next_prayer_info_all_prayers_done_message(setup_app_with_file, tmp_path):
    """Test the fallback message when no valid next prayer can be determined."""
    app, test_filepath = setup_app_with_file
    prayer_data = {
        "Fajr": "invalid-format",
        "Sunrise": "invalid",
        "Dhuhr": "invalid",
        "Asr": "invalid",
        "Sunset": "invalid",
        "Maghrib": "invalid",
        "Isha": "invalid",
    }
    create_dummy_prayer_times_file(test_filepath, prayer_data)
    app.prayer_times = app._load_prayer_times()

    current_dt = datetime(2023, 10, 27, 12, 0, 0) # Any time
    name, time, dt_obj = app.get_next_prayer_info(current_dt)
    
    assert name == "All prayers done for today"
    assert time is None
    assert dt_obj is None


def test_format_time_display_with_time():
    """Test format_time_display with a valid time string."""
    app = AdhanClockApp()
    formatted = app.format_time_display("Fajr", "05:00")
    assert formatted == "Fajr: 05:00"

def test_format_time_display_without_time():
    """Test format_time_display with a None time string."""
    app = AdhanClockApp()
    formatted = app.format_time_display("Fajr", None)
    assert formatted == "Fajr: N/A"

def test_format_time_display_empty_string_time():
    """Test format_time_display with an empty string time."""
    app = AdhanClockApp()
    formatted = app.format_time_display("Fajr", "")
    assert formatted == "Fajr: " # Original behavior: prints empty string

def test_run_gui_prints_output(capsys):
    """Test that run_gui prints basic output and doesn't crash."""
    # This test doesn't check the actual GUI, just that the method runs and prints.
    # We need to mock the datetime.now to ensure consistent output for testing.
    # However, the current implementation of run_gui only prints current status once.
    # To make it more testable, it should ideally run for a duration or be mockable.
    
    # For now, we just ensure it doesn't error and captures some output.
    # To make this test more robust, one would mock datetime.now and the get_next_prayer_info.
    
    # Create a dummy prayer times file for run_gui to load
    dummy_filepath = "test_run_gui_adhan_times.json"
    prayer_data = {
        "Fajr": "05:00", "Sunrise": "06:15", "Dhuhr": "13:00",
        "Asr": "16:30", "Sunset": "18:30", "Maghrib": "18:30", "Isha": "20:00"
    }
    create_dummy_prayer_times_file(dummy_filepath, prayer_data)
    
    app = AdhanClockApp(prayer_times_filepath=dummy_filepath)
    app.run_gui()
    
    captured = capsys.readouterr()
    assert "Starting Adhan Clock GUI..." in captured.out
    assert "Current time:" in captured.out
    assert "Next Prayer:" in captured.out
    assert "GUI application logic would continue here..." in captured.out

    remove_dummy_prayer_times_file(dummy_filepath) # Clean up

```
