```python
import pytest
import json
import os
from datetime import datetime, timedelta
from unittest.mock import mock_open, patch

# Add parent directory to sys.path to allow importing main.py
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import AdhanClockApp, PRAYER_TIMES_FILE

# Fixture for a valid prayer times dictionary
@pytest.fixture
def valid_prayer_times_data():
    return {
        "Fajr": "05:00",
        "Sunrise": "06:30",
        "Dhuhr": "12:30",
        "Asr": "16:00",
        "Sunset": "19:30",
        "Maghrib": "19:45",
        "Isha": "21:00",
        "Midnight": "00:00" # Extra key, should not cause issues in existing logic
    }

# Fixture for a malformed prayer times dictionary (missing expected keys)
@pytest.fixture
def malformed_prayer_times_data():
    return {
        "Fajr": "05:00",
        "Dhuhr": "12:30",
        "Isha": "21:00"
        # Missing Asr, Maghrib for validation in _load_prayer_times
    }

# Fixture for prayer times with an invalid time format for one of the prayers
@pytest.fixture
def invalid_format_prayer_times_data():
    return {
        "Fajr": "05:00",
        "Sunrise": "06:30",
        "Dhuhr": "invalid-time", # This will cause a ValueError in strptime
        "Asr": "16:00",
        "Maghrib": "19:45",
        "Isha": "21:00"
    }

# Fixture to create a temporary prayer times file with valid data
@pytest.fixture
def create_temp_prayer_file(tmp_path, valid_prayer_times_data):
    file_path = tmp_path / "test_adhan_times.json"
    with open(file_path, 'w') as f:
        json.dump(valid_prayer_times_data, f)
    return str(file_path)

# region: Tests for AdhanClockApp initialization and _load_prayer_times

def test_init_default_filepath(mocker):
    """Test if the app initializes with the default filepath when none is provided."""
    mocker.patch('os.path.exists', return_value=False) # Prevent actual file loading
    mocker.patch('builtins.open', mock_open()) # Mock open to prevent file operations
    app = AdhanClockApp()
    assert app.prayer_times_filepath == PRAYER_TIMES_FILE

def test_init_custom_filepath(mocker):
    """Test if the app initializes with a custom filepath when provided."""
    mocker.patch('os.path.exists', return_value=False)
    mocker.patch('builtins.open', mock_open())
    custom_path = "/path/to/custom_times.json"
    app = AdhanClockApp(custom_path)
    assert app.prayer_times_filepath == custom_path

def test_load_prayer_times_file_not_found(mocker, capsys):
    """Test behavior when the prayer times file does not exist."""
    mocker.patch('os.path.exists', return_value=False)
    app = AdhanClockApp("non_existent.json")
    assert app.prayer_times is None
    captured = capsys.readouterr()
    assert "Warning: Prayer times file not found at non_existent.json" in captured.out

def test_load_prayer_times_empty_file(mocker, capsys):
    """Test behavior when the prayer times file is empty."""
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('builtins.open', mock_open(read_data=""))
    app = AdhanClockApp("empty.json")
    assert app.prayer_times is None
    captured = capsys.readouterr()
    assert "Error reading or parsing prayer times from empty.json: Expecting value" in captured.out # JSONDecodeError message

def test_load_prayer_times_invalid_json(mocker, capsys):
    """Test behavior when the prayer times file contains invalid JSON."""
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('builtins.open', mock_open(read_data="{invalid json"))
    app = AdhanClockApp("invalid.json")
    assert app.prayer_times is None
    captured = capsys.readouterr()
    assert "Error reading or parsing prayer times from invalid.json: Expecting property name enclosed in double quotes" in captured.out # JSONDecodeError message

def test_load_prayer_times_malformed_data(mocker, capsys, malformed_prayer_times_data):
    """Test behavior when the JSON file is valid but misses expected prayer keys."""
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('builtins.open', mock_open(read_data=json.dumps(malformed_prayer_times_data)))
    app = AdhanClockApp("malformed.json")
    assert app.prayer_times is None
    captured = capsys.readouterr()
    assert "Warning: Malformed prayer times data in malformed.json (missing expected keys)." in captured.out

def test_load_prayer_times_valid_data(mocker, capsys, valid_prayer_times_data):
    """Test successful loading of a valid prayer times JSON file."""
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('builtins.open', mock_open(read_data=json.dumps(valid_prayer_times_data)))
    app = AdhanClockApp("valid.json")
    assert app.prayer_times == valid_prayer_times_data
    captured = capsys.readouterr()
    assert "Prayer times loaded successfully from valid.json" in captured.out

def test_load_prayer_times_io_error(mocker, capsys):
    """Test behavior when an IOError occurs during file reading."""
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('builtins.open', side_effect=IOError("Permission denied"))
    app = AdhanClockApp("permission.json")
    assert app.prayer_times is None
    captured = capsys.readouterr()
    assert "Error reading or parsing prayer times from permission.json: Permission denied" in captured.out

# endregion

# region: Tests for get_next_prayer_info

def test_get_next_prayer_info_no_prayer_times_loaded():
    """Test when no prayer times have been loaded into the app."""
    app = AdhanClockApp()
    app.prayer_times = None # Explicitly set to None to simulate load failure
    name, time_str, dt_obj = app.get_next_prayer_info(datetime.now())
    assert name == "No prayer times loaded"
    assert time_str is None
    assert dt_obj is None

@pytest.mark.parametrize(
    "current_time_str, expected_prayer_name, expected_time_str",
    [
        ("04:30", "Fajr", "05:00"),  # Before Fajr
        ("05:30", "Sunrise", "06:30"), # After Fajr, before Sunrise
        ("06:45", "Dhuhr", "12:30"), # After Sunrise, before Dhuhr
        ("12:45", "Asr", "16:00"),   # After Dhuhr, before Asr
        ("16:30", "Sunset", "19:30"), # After Asr, before Sunset
        ("19:35", "Maghrib", "19:45"), # After Sunset, before Maghrib
        ("20:00", "Isha", "21:00"),  # After Maghrib, before Isha
    ]
)
def test_get_next_prayer_info_upcoming_today(mocker, create_temp_prayer_file, current_time_str, expected_prayer_name, expected_time_str):
    """Test various scenarios where the next prayer is later today."""
    app = AdhanClockApp(create_temp_prayer_file)
    test_date = datetime(2023, 10, 27) # Fixed date for consistent testing
    current_dt = datetime.strptime(f"{test_date.strftime('%Y-%m-%d')} {current_time_str}", "%Y-%m-%d %H:%M")

    name, time_str, dt_obj = app.get_next_prayer_info(current_dt)

    assert name == expected_prayer_name
    assert time_str == expected_time_str
    expected_dt = datetime.strptime(f"{test_date.strftime('%Y-%m-%d')} {expected_time_str}", "%Y-%m-%d %H:%M")
    assert dt_obj == expected_dt

def test_get_next_prayer_info_all_prayers_done_today(mocker, create_temp_prayer_file):
    """Test scenario where all prayers for today have passed, expecting tomorrow's Fajr."""
    app = AdhanClockApp(create_temp_prayer_file)
    test_date = datetime(2023, 10, 27)
    current_dt = datetime.strptime(f"{test_date.strftime('%Y-%m-%d')} 22:00", "%Y-%m-%d %H:%M") # After Isha 21:00

    name, time_str, dt_obj = app.get_next_prayer_info(current_dt)

    assert name == "Fajr (Tomorrow)"
    assert time_str == "05:00" # Fajr time from the fixture
    expected_dt = datetime.strptime(f"{(test_date + timedelta(days=1)).strftime('%Y-%m-%d')} 05:00", "%Y-%m-%d %H:%M")
    assert dt_obj == expected_dt

def test_get_next_prayer_info_current_time_at_prayer(mocker, create_temp_prayer_file):
    """Test behavior when current time is exactly at a prayer time."""
    app = AdhanClockApp(create_temp_prayer_file)
    test_date = datetime(2023, 10, 27)
    current_dt = datetime.strptime(f"{test_date.strftime('%Y-%m-%d')} 12:30", "%Y-%m-%d %H:%M") # Exactly Dhuhr time

    name, time_str, dt_obj = app.get_next_prayer_info(current_dt)

    # The condition `prayer_dt_objects[prayer] > current_dt` means it picks the *next* prayer strictly after current_dt.
    assert name == "Asr"
    assert time_str == "16:00"
    expected_dt = datetime.strptime(f"{test_date.strftime('%Y-%m-%d')} 16:00", "%Y-%m-%d %H:%M")
    assert dt_obj == expected_dt

def test_get_next_prayer_info_invalid_time_format_in_data(mocker, capsys, tmp_path, invalid_format_prayer_times_data):
    """Test that invalid time formats in the loaded data are handled and skipped."""
    file_path = tmp_path / "invalid_format.json"
    with open(file_path, 'w') as f:
        json.dump(invalid_format_prayer_times_data, f)
    app = AdhanClockApp(str(file_path))

    test_date = datetime(2023, 10, 27)
    current_dt = datetime.strptime(f"{test_date.strftime('%Y-%m-%d')} 07:00", "%Y-%m-%d %H:%M") # After Sunrise, before Dhuhr

    name, time_str, dt_obj = app.get_next_prayer_info(current_dt)
    captured = capsys.readouterr()
    assert "Warning: Invalid time format for Dhuhr: 'invalid-time'" in captured.out

    # Should skip the invalid Dhuhr and find Asr
    assert name == "Asr"
    assert time_str == "16:00"
    expected_dt = datetime.strptime(f"{test_date.strftime('%Y-%m-%d')} 16:00", "%Y-%m-%d %H:%M")
    assert dt_obj == expected_dt

def test_get_next_prayer_info_fajr_not_in_prayer_times_for_tomorrow_check(mocker, tmp_path):
    """Test behavior when Fajr is missing from the prayer times data and all prayers for today are done."""
    # Create a prayer times file without Fajr
    no_fajr_data = {
        "Dhuhr": "12:30",
        "Asr": "16:00",
        "Maghrib": "19:45",
        "Isha": "21:00"
    }
    file_path = tmp_path / "no_fajr.json"
    with open(file_path, 'w') as f:
        json.dump(no_fajr_data, f)
    app = AdhanClockApp(str(file_path))

    test_date = datetime(2023, 10, 27)
    current_dt = datetime.strptime(f"{test_date.strftime('%Y-%m-%d')} 22:00", "%Y-%m-%d %H:%M") # After Isha

    name, time_str, dt_obj = app.get_next_prayer_info(current_dt)

    assert name == "All prayers done for today"
    assert time_str is None
    assert dt_obj is None
    # No warning printed as the explicit check for "Fajr" in self.prayer_times handles this cleanly.

def test_get_next_prayer_info_invalid_fajr_time_format_for_tomorrow(mocker, tmp_path, capsys):
    """Test behavior when Fajr time for tomorrow is malformed."""
    # Create a prayer times file with invalid Fajr format
    invalid_fajr_tomorrow_data = {
        "Fajr": "invalid-fajr-time",
        "Sunrise": "06:30",
        "Dhuhr": "12:30",
        "Asr": "16:00",
        "Maghrib": "19:45",
        "Isha": "21:00"
    }
    file_path = tmp_path / "invalid_fajr_tomorrow.json"
    with open(file_path, 'w') as f:
        json.dump(invalid_fajr_tomorrow_data, f)
    app = AdhanClockApp(str(file_path))

    test_date = datetime(2023, 10, 27)
    current_dt = datetime.strptime(f"{test_date.strftime('%Y-%m-%d')} 22:00", "%Y-%m-%d %H:%M") # After Isha

    name, time_str, dt_obj = app.get_next_prayer_info(current_dt)
    captured = capsys.readouterr()
    assert "Warning: Invalid Fajr time format for tomorrow: 'invalid-fajr-time'" in captured.out

    # Fallback to "All prayers done for today" message if tomorrow's Fajr cannot be parsed.
    assert name == "All prayers done for today"
    assert time_str is None
    assert dt_obj is None

# endregion

# region: Tests for format_time_display

def test_format_time_display_with_time():
    """Test formatting with a valid time string."""
    app = AdhanClockApp() # This method doesn't depend on loaded prayer times
    result = app.format_time_display("Fajr", "05:00")
    assert result == "Fajr: 05:00"

def test_format_time_display_without_time():
    """Test formatting when the time string is None or empty."""
    app = AdhanClockApp()
    result = app.format_time_display("Fajr", None)
    assert result == "Fajr: N/A"
    result = app.format_time_display("Isha", "")
    assert result == "Isha: N/A"

# endregion

# region: Tests for run_gui (smoke tests for output)
def test_run_gui_output(mocker, capsys, create_temp_prayer_file):
    """Smoke test for run_gui to check its print output with loaded prayer times."""
    app = AdhanClockApp(create_temp_prayer_file)
    # Mock datetime.now() for consistent current time
    fixed_time = datetime(2023, 10, 27, 10, 0)
    mocker.patch('main.datetime', mocker.MagicMock(now=mocker.MagicMock(return_value=fixed_time)))

    app.run_gui()
    captured = capsys.readouterr()

    assert "Starting Adhan Clock GUI..." in captured.out
    assert "Current time: 10:00:00" in captured.out
    assert "Next Prayer: Dhuhr at 12:30" in captured.out # Based on fixed_time and valid_prayer_times_data
    assert "GUI application logic would continue here..." in captured.out

def test_run_gui_no_prayer_times_loaded_output(mocker, capsys):
    """Smoke test for run_gui when no prayer times are loaded."""
    # Initialize app such that prayer_times will be None (e.g., non-existent file)
    mocker.patch('os.path.exists', return_value=False)
    mocker.patch('builtins.open', mock_open())
    app = AdhanClockApp("non_existent.json")
    
    # Mock datetime.now() for consistent current time
    fixed_time = datetime(2023, 10, 27, 10, 0)
    mocker.patch('main.datetime', mocker.MagicMock(now=mocker.MagicMock(return_value=fixed_time)))

    app.run_gui()
    captured = capsys.readouterr()
    
    assert "Starting Adhan Clock GUI..." in captured.out
    assert "Current time: 10:00:00" in captured.out
    assert "Next Prayer: No prayer times loaded at N/A" in captured.out
    assert "GUI application logic would continue here..." in captured.out
    assert "Warning: Prayer times file not found at non_existent.json" in captured.out # From _load_prayer_times called during init
# endregion
```
