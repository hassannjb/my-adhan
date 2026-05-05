```python
import pytest
import os
from datetime import datetime, timedelta
import json

# Assume main.py is in the root of the project
from main import AdhanClockApp, PRAYER_TIMES_FILE

# Define a default file path for tests, to avoid interfering with actual files
TEST_PRAYER_TIMES_FILE = "test_adhan_times.json"

@pytest.fixture
def cleanup_test_file():
    """Fixture to clean up the test prayer times file after each test."""
    if os.path.exists(TEST_PRAYER_TIMES_FILE):
        os.remove(TEST_PRAYER_TIMES_FILE)
    if os.path.exists(PRAYER_TIMES_FILE): # Clean up default if it was created
        os.remove(PRAYER_TIMES_FILE)
    yield
    if os.path.exists(TEST_PRAYER_TIMES_FILE):
        os.remove(TEST_PRAYER_TIMES_FILE)
    if os.path.exists(PRAYER_TIMES_FILE):
        os.remove(PRAYER_TIMES_FILE)

def create_test_prayer_times_file(filepath, data):
    """Helper function to create a prayer times JSON file for testing."""
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)

@pytest.fixture
def app_with_valid_times(cleanup_test_file):
    """Fixture to provide an AdhanClockApp instance with valid prayer times."""
    valid_times_data = {
        "Fajr": "05:00",
        "Sunrise": "06:15",
        "Dhuhr": "13:00",
        "Asr": "16:30",
        "Maghrib": "18:45",
        "Isha": "20:00"
    }
    create_test_prayer_times_file(TEST_PRAYER_TIMES_FILE, valid_times_data)
    app = AdhanClockApp(prayer_times_filepath=TEST_PRAYER_TIMES_FILE)
    yield app
    # cleanup is handled by cleanup_test_file fixture

@pytest.fixture
def app_with_malformed_times(cleanup_test_file):
    """Fixture to provide an AdhanClockApp instance with malformed prayer times."""
    malformed_times_data = {
        "Fajr": "05:00",
        "Dhuhr": "13:00",
        # Missing Asr, Maghrib, Isha
    }
    create_test_prayer_times_file(TEST_PRAYER_TIMES_FILE, malformed_times_data)
    app = AdhanClockApp(prayer_times_filepath=TEST_PRAYER_TIMES_FILE)
    yield app

@pytest.fixture
def app_with_invalid_time_format(cleanup_test_file):
    """Fixture to provide an AdhanClockApp instance with invalid time formats."""
    invalid_format_data = {
        "Fajr": "05:00",
        "Sunrise": "06:15",
        "Dhuhr": "13:00",
        "Asr": "invalid_time", # Invalid format
        "Maghrib": "18:45",
        "Isha": "20:00"
    }
    create_test_prayer_times_file(TEST_PRAYER_TIMES_FILE, invalid_format_data)
    app = AdhanClockApp(prayer_times_filepath=TEST_PRAYER_TIMES_FILE)
    yield app

def test_init_with_default_filepath(cleanup_test_file):
    """Tests initialization using the default prayer times file path."""
    # Create a dummy default file
    default_data = {"Fajr": "05:00", "Dhuhr": "13:00", "Asr": "16:00", "Maghrib": "18:00", "Isha": "19:00"}
    create_test_prayer_times_file(PRAYER_TIMES_FILE, default_data)
    
    app = AdhanClockApp()
    assert app.prayer_times_filepath == PRAYER_TIMES_FILE
    assert app.prayer_times == default_data

def test_init_with_custom_filepath(cleanup_test_file):
    """Tests initialization using a custom prayer times file path."""
    custom_data = {"Fajr": "04:00", "Dhuhr": "12:00"}
    create_test_prayer_times_file(TEST_PRAYER_TIMES_FILE, custom_data)
    
    app = AdhanClockApp(prayer_times_filepath=TEST_PRAYER_TIMES_FILE)
    assert app.prayer_times_filepath == TEST_PRAYER_TIMES_FILE
    assert app.prayer_times == custom_data

def test_load_prayer_times_file_not_found(cleanup_test_file):
    """Tests loading when the prayer times file does not exist."""
    app = AdhanClockApp(prayer_times_filepath="non_existent_file.json")
    assert app.prayer_times is None
    # Check if the warning was printed (difficult to assert directly without mocking print)
    # We'll rely on the fact that app.prayer_times is None as the indicator.

def test_load_prayer_times_malformed_json(cleanup_test_file):
    """Tests loading when the prayer times file contains invalid JSON."""
    with open(TEST_PRAYER_TIMES_FILE, 'w') as f:
        f.write("{invalid json")
    
    app = AdhanClockApp(prayer_times_filepath=TEST_PRAYER_TIMES_FILE)
    assert app.prayer_times is None

def test_load_prayer_times_missing_keys(app_with_malformed_times):
    """Tests loading when the JSON file is missing required prayer keys."""
    # The fixture app_with_malformed_times already sets up this condition
    assert app_with_malformed_times.prayer_times is None # Should be None due to missing keys

def test_get_next_prayer_info_valid_times(app_with_valid_times):
    """Tests finding the next prayer with valid prayer times."""
    # Example: Current time is just before Dhuhr
    current_dt = datetime(2023, 10, 27, 12, 0, 0)
    next_prayer_name, next_prayer_time_str, next_prayer_dt_obj = app_with_valid_times.get_next_prayer_info(current_dt)
    
    assert next_prayer_name == "Dhuhr"
    assert next_prayer_time_str == "13:00"
    assert next_prayer_dt_obj == datetime(2023, 10, 27, 13, 0, 0)

    # Example: Current time is after all prayers for today
    current_dt_late = datetime(2023, 10, 27, 21, 0, 0)
    next_prayer_name_late, next_prayer_time_str_late, next_prayer_dt_obj_late = app_with_valid_times.get_next_prayer_info(current_dt_late)
    
    # It should suggest Fajr for the next day
    assert next_prayer_name_late == "Fajr (Tomorrow)"
    assert next_prayer_time_str_late == "05:00"
    assert next_prayer_dt_obj_late == datetime(2023, 10, 28, 5, 0, 0)

def test_get_next_prayer_info_no_times_loaded():
    """Tests when no prayer times have been loaded."""
    app = AdhanClockApp(prayer_times_filepath="non_existent_file.json")
    current_dt = datetime.now()
    next_prayer_name, _, _ = app.get_next_prayer_info(current_dt)
    assert next_prayer_name == "No prayer times loaded"

def test_get_next_prayer_info_invalid_time_format(app_with_invalid_time_format):
    """Tests behavior when prayer times have invalid time formats."""
    # Current time before the "invalid_time" Asr
    current_dt = datetime(2023, 10, 27, 15, 0, 0)
    next_prayer_name, next_prayer_time_str, next_prayer_dt_obj = app_with_invalid_time_format.get_next_prayer_info(current_dt)
    
    # It should skip the invalid "Asr" and find the next valid prayer (Maghrib)
    assert next_prayer_name == "Maghrib"
    assert next_prayer_time_str == "18:45"
    assert next_prayer_dt_obj == datetime(2023, 10, 27, 18, 45, 0)

    # Test case where invalid time is the only remaining prayer before tomorrow's Fajr
    # Let's simulate times where only "invalid_time" Asr remains for today
    invalid_format_data_only_invalid = {
        "Fajr": "05:00",
        "Sunrise": "06:15",
        "Dhuhr": "13:00",
        "Asr": "invalid_time", # Invalid format
        "Maghrib": "invalid_time_2", # Another invalid format
        "Isha": "invalid_time_3" # Another invalid format
    }
    malformed_app_filepath = "malformed_app_test.json"
    create_test_prayer_times_file(malformed_app_filepath, invalid_format_data_only_invalid)
    malformed_app = AdhanClockApp(prayer_times_filepath=malformed_app_filepath)
    
    current_dt_late = datetime(2023, 10, 27, 17, 0, 0) # After Dhuhr, before any remaining (invalid) prayers
    next_prayer_name_late, next_prayer_time_str_late, next_prayer_dt_obj_late = malformed_app.get_next_prayer_info(current_dt_late)
    
    # It should still fall back to Fajr of tomorrow if all today's times are invalid
    assert next_prayer_name_late == "Fajr (Tomorrow)"
    assert next_prayer_time_str_late == "05:00"
    assert next_prayer_dt_obj_late == datetime(2023, 10, 28, 5, 0, 0)
    os.remove(malformed_app_filepath) # Clean up the temporary file


def test_get_next_prayer_info_tomorrow_fajr_invalid(app_with_valid_times):
    """Tests scenario where tomorrow's Fajr time is invalid."""
    # Temporarily modify the loaded times to make Fajr invalid for tomorrow's check
    original_prayer_times = app_with_valid_times.prayer_times.copy()
    app_with_valid_times.prayer_times["Fajr"] = "invalid-fajr-time"

    current_dt_late = datetime(2023, 10, 27, 21, 0, 0) # After all prayers for today
    next_prayer_name, next_prayer_time_str, next_prayer_dt_obj = app_with_valid_times.get_next_prayer_info(current_dt_late)

    # Expecting "All prayers done for today" because Fajr for tomorrow is invalid
    assert next_prayer_name == "All prayers done for today"
    assert next_prayer_time_str is None
    assert next_prayer_dt_obj is None

    # Restore original times if necessary for other tests
    app_with_valid_times.prayer_times = original_prayer_times

def test_format_time_display(app_with_valid_times):
    """Tests the formatting of prayer name and time."""
    formatted = app_with_valid_times.format_time_display("Fajr", "05:00")
    assert formatted == "Fajr: 05:00"

    formatted_na = app_with_valid_times.format_time_display("Fajr", None)
    assert formatted_na == "Fajr: N/A"

def test_run_gui_output(app_with_valid_times, capsys):
    """Tests the output of the run_gui method (simulated)."""
    # Mock datetime.now to ensure consistent output for testing
    fixed_time = datetime(2023, 10, 27, 10, 30, 0)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("datetime.datetime", lambda *args, **kwargs: fixed_time if not args else datetime.datetime(*args, **kwargs))
        app_with_valid_times.run_gui()
    
    captured = capsys.readouterr()
    
    assert "Starting Adhan Clock GUI..." in captured.out
    assert f"Current time: {fixed_time.strftime('%H:%M:%S')}" in captured.out
    assert "Next Prayer: Dhuhr at 13:00" in captured.out # Dhuhr is the next prayer after 10:30
    assert "GUI application logic would continue here..." in captured.out

def test_run_gui_output_no_times_loaded(capsys):
    """Tests run_gui output when no prayer times are loaded."""
    app = AdhanClockApp(prayer_times_filepath="non_existent_file.json")
    fixed_time = datetime(2023, 10, 27, 10, 30, 0)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("datetime.datetime", lambda *args, **kwargs: fixed_time if not args else datetime.datetime(*args, **kwargs))
        app.run_gui()
    
    captured = capsys.readouterr()
    
    assert "Starting Adhan Clock GUI..." in captured.out
    assert f"Current time: {fixed_time.strftime('%H:%M:%S')}" in captured.out
    assert "Next Prayer: No prayer times loaded at N/A" in captured.out
    assert "GUI application logic would continue here..." in captured.out
```