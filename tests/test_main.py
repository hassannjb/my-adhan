```python
import pytest
from datetime import datetime, timedelta
import os
import sys
from unittest.mock import patch

# Assume main.py is in the root of the project, adjust path if needed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import AdhanClockApp, PRAYER_TIMES_FILE

@pytest.fixture
def app_with_default_path():
    """App instance using the default PRAYER_TIMES_FILE."""
    return AdhanClockApp()

@pytest.fixture
def app_with_custom_path(tmp_test_dir):
    """App instance using a custom (and potentially non-existent) path."""
    custom_path = os.path.join(tmp_test_dir, "custom_adhan_times.json")
    return AdhanClockApp(prayer_times_filepath=custom_path)

def test_init_default_path(app_with_default_path):
    """Test initialization with default file path."""
    assert app_with_default_path.prayer_times_filepath == PRAYER_TIMES_FILE
    # We can't assert the content of self.prayer_times here as it depends on the file system state.
    # This will be tested in other tests.

def test_init_custom_path(app_with_custom_path):
    """Test initialization with a custom file path."""
    assert app_with_custom_path.prayer_times_filepath.endswith("custom_adhan_times.json")

@pytest.mark.parametrize(
    "current_dt_str, expected_prayer_name, expected_time_str, expected_dt_offset_days",
    [
        # Test case 1: Before Fajr
        ("2023-10-27 04:00", "Fajr", "05:00", 0),
        # Test case 2: Exactly at Fajr
        ("2023-10-27 05:00", "Sunrise", "06:15", 0),
        # Test case 3: After Fajr, before Sunrise
        ("2023-10-27 05:30", "Sunrise", "06:15", 0),
        # Test case 4: After Sunrise, before Dhuhr
        ("2023-10-27 07:00", "Dhuhr", "13:00", 0),
        # Test case 5: Exactly at Dhuhr
        ("2023-10-27 13:00", "Asr", "16:30", 0),
        # Test case 6: After Dhuhr, before Asr
        ("2023-10-27 14:00", "Asr", "16:30", 0),
        # Test case 7: Exactly at Asr
        ("2023-10-27 16:30", "Maghrib", "18:45", 0),
        # Test case 8: After Asr, before Maghrib
        ("2023-10-27 17:00", "Maghrib", "18:45", 0),
        # Test case 9: Exactly at Maghrib
        ("2023-10-27 18:45", "Isha", "20:00", 0),
        # Test case 10: After Maghrib, before Isha
        ("2023-10-27 19:00", "Isha", "20:00", 0),
        # Test case 11: Exactly at Isha
        ("2023-10-27 20:00", "Fajr (Tomorrow)", "05:00", 1),
        # Test case 12: After Isha
        ("2023-10-27 21:00", "Fajr (Tomorrow)", "05:00", 1),
        # Test case 13: Midnight, before Fajr of next day
        ("2023-10-28 00:00", "Fajr (Tomorrow)", "05:00", 0), # This assumes Fajr is for the *upcoming* day, if current_dt is 2023-10-27
        # Test case 14: Date change during the day (e.g., testing Fajr of next day)
        ("2023-10-27 23:59", "Fajr (Tomorrow)", "05:00", 1),
    ]
)
def test_get_next_prayer_info_success(app_with_default_path, dummy_prayer_times_file, current_dt_str, expected_prayer_name, expected_time_str, expected_dt_offset_days):
    """Test get_next_prayer_info with various current times against a valid prayer times file."""
    # Create a dummy file for this test
    app_with_default_path.prayer_times_filepath = dummy_prayer_times_file
    app_with_default_path.prayer_times = app_with_default_path._load_prayer_times() # Reload with the dummy file

    current_dt = datetime.strptime(current_dt_str, "%Y-%m-%d %H:%M")
    prayer_name, time_str, prayer_dt = app_with_default_path.get_next_prayer_info(current_dt)

    assert prayer_name == expected_prayer_name
    assert time_str == expected_time_str

    if prayer_dt:
        # Calculate expected datetime based on offset
        expected_date = current_dt.date() + timedelta(days=expected_dt_offset_days)
        expected_time_obj = datetime.strptime(expected_time_str, "%H:%M").time()
        expected_prayer_dt = datetime.combine(expected_date, expected_time_obj)
        assert prayer_dt == expected_prayer_dt
    else:
        assert prayer_dt is None

def test_get_next_prayer_info_no_times_loaded(app_with_custom_path):
    """Test get_next_prayer_info when no prayer times are loaded."""
    current_dt = datetime.now()
    prayer_name, time_str, prayer_dt = app_with_custom_path.get_next_prayer_info(current_dt)
    assert prayer_name == "No prayer times loaded"
    assert time_str is None
    assert prayer_dt is None

def test_get_next_prayer_info_malformed_file(app_with_default_path, malformed_prayer_times_file):
    """Test get_next_prayer_info with a malformed prayer times file."""
    app_with_default_path.prayer_times_filepath = malformed_prayer_times_file
    # The _load_prayer_times method should return None for malformed files
    assert app_with_default_path._load_prayer_times() is None
    prayer_name, time_str, prayer_dt = app_with_default_path.get_next_prayer_info(datetime.now())
    assert prayer_name == "No prayer times loaded"
    assert time_str is None
    assert prayer_dt is None

def test_get_next_prayer_info_empty_file(app_with_default_path, empty_prayer_times_file):
    """Test get_next_prayer_info with an empty prayer times file."""
    app_with_default_path.prayer_times_filepath = empty_prayer_times_file
    # The _load_prayer_times method should return None for malformed files
    assert app_with_default_path._load_prayer_times() is None
    prayer_name, time_str, prayer_dt = app_with_default_path.get_next_prayer_info(datetime.now())
    assert prayer_name == "No prayer times loaded"
    assert time_str is None
    assert prayer_dt is None

def test_get_next_prayer_info_invalid_time_format_in_file(tmp_test_dir):
    """Test get_next_prayer_info when the prayer times file has invalid time formats."""
    filepath = os.path.join(tmp_test_dir, "invalid_time_adhan_times.json")
    data = {
        "Fajr": "05:00",
        "Sunrise": "invalid-time",
        "Dhuhr": "13:00",
        "Asr": "16:30",
        "Maghrib": "18:45",
        "Isha": "20:00"
    }
    with open(filepath, 'w') as f:
        import json
        json.dump(data, f)

    app = AdhanClockApp(prayer_times_filepath=filepath)
    current_dt = datetime(2023, 10, 27, 7, 0) # Time after Fajr, before Dhuhr
    prayer_name, time_str, prayer_dt = app.get_next_prayer_info(current_dt)

    # Sunrise is invalid, so it should be skipped and Dhuhr should be the next prayer
    assert prayer_name == "Dhuhr"
    assert time_str == "13:00"
    assert prayer_dt == datetime(2023, 10, 27, 13, 0)

def test_get_next_prayer_info_all_prayers_passed(app_with_default_path, dummy_prayer_times_file):
    """Test get_next_prayer_info when all prayers for the day have passed."""
    app_with_default_path.prayer_times_filepath = dummy_prayer_times_file
    app_with_default_path.prayer_times = app_with_default_path._load_prayer_times()

    # Set current time to after Isha
    current_dt = datetime(2023, 10, 27, 21, 0)
    prayer_name, time_str, prayer_dt = app_with_default_path.get_next_prayer_info(current_dt)

    assert prayer_name == "Fajr (Tomorrow)"
    assert time_str == "05:00"
    # Expected time should be Fajr of the next day
    expected_dt = datetime(2023, 10, 28, 5, 0)
    assert prayer_dt == expected_dt

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

@patch('builtins.print')
def test_run_gui_prints_info(mock_print, app_with_default_path, dummy_prayer_times_file):
    """Test that run_gui prints the current time and next prayer info."""
    app_with_default_path.prayer_times_filepath = dummy_prayer_times_file
    app_with_default_path.prayer_times = app_with_default_path._load_prayer_times()

    # Mock datetime.now() to control the "current time"
    fixed_time = datetime(2023, 10, 27, 19, 30) # After Asr, before Maghrib
    with patch('main.datetime') as mock_datetime:
        mock_datetime.now.return_value = fixed_time
        mock_datetime.strftime = datetime.strftime # Keep original strftime

        app_with_default_path.run_gui()

    # Check if print was called with the expected output
    calls = [call[0][0] for call in mock_print.call_args_list]

    assert "Starting Adhan Clock GUI..." in calls
    assert f"Current time: {fixed_time.strftime('%H:%M:%S')}" in calls
    assert "Next Prayer: Maghrib at 18:45" in calls
    assert "GUI application logic would continue here..." in calls

def test_load_prayer_times_file_not_found(app_with_custom_path):
    """Test _load_prayer_times when the file does not exist."""
    # Ensure the file path is not pointing to an existing file
    if os.path.exists(app_with_custom_path.prayer_times_filepath):
        os.remove(app_with_custom_path.prayer_times_filepath)
    
    with patch('builtins.print') as mock_print:
        prayer_times = app_with_custom_path._load_prayer_times()
    
    assert prayer_times is None
    mock_print.assert_any_call(f"Warning: Prayer times file not found at {app_with_custom_path.prayer_times_filepath}")

def test_load_prayer_times_json_decode_error(tmp_test_dir):
    """Test _load_prayer_times when the file content is invalid JSON."""
    filepath = os.path.join(tmp_test_dir, "bad_json.json")
    with open(filepath, 'w') as f:
        f.write("This is not JSON")

    app = AdhanClockApp(prayer_times_filepath=filepath)
    with patch('builtins.print') as mock_print:
        prayer_times = app._load_prayer_times()

    assert prayer_times is None
    mock_print.assert_any_call(f"Error reading or parsing prayer times from {filepath}: Expecting value: line 1 column 1 (char 0)") # Or similar JSONDecodeError message

def test_load_prayer_times_io_error(tmp_test_dir):
    """Test _load_prayer_times when there's an IOError during file read."""
    filepath = os.path.join(tmp_test_dir, "readonly.json")
    # Create an empty file and make it read-only (if possible on the OS)
    with open(filepath, 'w') as f:
        pass # Create empty file
    
    # Attempt to make it read-only (may not work on all OS/file systems)
    # For robustness, we'll simulate the error more directly or rely on specific OS behavior.
    # A more reliable way is to patch the open call to raise an IOError.
    with patch('builtins.open', side_effect=IOError("Simulated IO Error")):
        app = AdhanClockApp(prayer_times_filepath=filepath)
        with patch('builtins.print') as mock_print:
            prayer_times = app._load_prayer_times()
    
    assert prayer_times is None
    mock_print.assert_any_call(f"Error reading or parsing prayer times from {filepath}: Simulated IO Error")

def test_load_prayer_times_malformed_data(app_with_default_path, malformed_prayer_times_file):
    """Test _load_prayer_times when the JSON data is missing required keys."""
    app_with_default_path.prayer_times_filepath = malformed_prayer_times_file
    with patch('builtins.print') as mock_print:
        prayer_times = app_with_default_path._load_prayer_times()
    
    assert prayer_times is None
    mock_print.assert_any_call(f"Warning: Malformed prayer times data in {malformed_prayer_times_file} (missing expected keys).")

def test_get_next_prayer_info_tomorrow_fajr_invalid_format(tmp_test_dir):
    """Test get_next_prayer_info when tomorrow's Fajr time is malformed."""
    filepath = os.path.join(tmp_test_dir, "tomorrow_fajr_invalid.json")
    data = {
        "Fajr": "invalid-tomorrow-fajr", # This is only checked if current day's prayers are all passed
        "Sunrise": "06:15",
        "Dhuhr": "13:00",
        "Asr": "16:30",
        "Maghrib": "18:45",
        "Isha": "20:00"
    }
    with open(filepath, 'w') as f:
        import json
        json.dump(data, f)

    app = AdhanClockApp(prayer_times_filepath=filepath)
    # Set current time to after Isha
    current_dt = datetime(2023, 10, 27, 21, 0)
    
    with patch('builtins.print') as mock_print:
        prayer_name, time_str, prayer_dt = app.get_next_prayer_info(current_dt)
    
    assert prayer_name == "All prayers done for today" # Fallback when tomorrow's Fajr is also bad
    assert time_str is None
    assert prayer_dt is None
    mock_print.assert_any_call("Warning: Invalid Fajr time format for tomorrow: 'invalid-tomorrow-fajr'")

```
