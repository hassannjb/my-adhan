import pytest
import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch, mock_open

# Adjust sys.path to allow importing main from the parent directory
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import AdhanClockApp, PRAYER_TIMES_FILE

# --- Fixtures ---

@pytest.fixture
def temp_prayer_times_file(tmp_path):
    """Provides a temporary path for the prayer times JSON file."""
    filepath = tmp_path / "test_adhan_times.json"
    yield filepath

@pytest.fixture
def mock_prayer_times_data():
    """Provides a dictionary of sample prayer times."""
    return {
        "Fajr": "05:00",
        "Sunrise": "06:30",
        "Dhuhr": "13:00",
        "Asr": "17:00",
        "Sunset": "19:30",
        "Maghrib": "19:45",
        "Isha": "21:00"
    }

# --- AdhanClockApp Initialization and _load_prayer_times tests ---

def test_init_default_filepath(tmp_path):
    """Tests that the app initializes with the default filepath if none is provided."""
    # Create a dummy file at the default path for mock_open to read
    default_path = tmp_path / PRAYER_TIMES_FILE
    dummy_content = json.dumps({"Fajr": "05:00", "Dhuhr": "12:00", "Asr": "15:00", "Maghrib": "18:00", "Isha": "20:00"})

    # Patch os.path.exists and builtins.open
    with patch('os.path.exists', return_value=True), \
         patch('builtins.open', mock_open(read_data=dummy_content)) as mocked_open_func, \
         patch('main.PRAYER_TIMES_FILE', str(default_path)): # Mock the constant to use our temp path
        
        app = AdhanClockApp()
        assert app.prayer_times_filepath == str(default_path)
        assert app.prayer_times is not None 
        mocked_open_func.assert_called_once_with(str(default_path), 'r')

def test_init_custom_filepath(temp_prayer_times_file, mock_prayer_times_data):
    """Tests that the app initializes with a custom filepath."""
    dummy_content = json.dumps(mock_prayer_times_data)

    with patch('os.path.exists', return_value=True), \
         patch('builtins.open', mock_open(read_data=dummy_content)) as mocked_open_func:
        app = AdhanClockApp(prayer_times_filepath=str(temp_prayer_times_file))
        assert app.prayer_times_filepath == str(temp_prayer_times_file)
        assert app.prayer_times == mock_prayer_times_data
        mocked_open_func.assert_called_once_with(str(temp_prayer_times_file), 'r')

def test_load_prayer_times_success(temp_prayer_times_file, mock_prayer_times_data, capsys):
    """Tests successful loading of prayer times from a valid JSON file."""
    temp_prayer_times_file.write_text(json.dumps(mock_prayer_times_data))

    app = AdhanClockApp(prayer_times_filepath=str(temp_prayer_times_file))
    assert app.prayer_times == mock_prayer_times_data
    captured = capsys.readouterr()
    assert f"Prayer times loaded successfully from {temp_prayer_times_file}" in captured.out

def test_load_prayer_times_file_not_found(temp_prayer_times_file, capsys):
    """Tests loading when the prayer times file does not exist."""
    # Ensure the file does not exist for this test
    app = AdhanClockApp(prayer_times_filepath=str(temp_prayer_times_file))
    assert app.prayer_times is None
    captured = capsys.readouterr()
    assert f"Warning: Prayer times file not found at {temp_prayer_times_file}" in captured.out

def test_load_prayer_times_empty_file(temp_prayer_times_file, capsys):
    """Tests loading from an empty file (should cause JSONDecodeError)."""
    temp_prayer_times_file.write_text("")
    app = AdhanClockApp(prayer_times_filepath=str(temp_prayer_times_file))
    assert app.prayer_times is None
    captured = capsys.readouterr()
    # JSONDecodeError message can vary slightly by Python version, but "Expecting value" is common.
    assert "Error reading or parsing prayer times from" in captured.err
    assert "Expecting value" in captured.err

def test_load_prayer_times_malformed_json(temp_prayer_times_file, capsys):
    """Tests loading from a file with malformed JSON."""
    temp_prayer_times_file.write_text("{'Fajr': '05:00',}") # Invalid JSON
    app = AdhanClockApp(prayer_times_filepath=str(temp_prayer_times_file))
    assert app.prayer_times is None
    captured = capsys.readouterr()
    assert "Error reading or parsing prayer times from" in captured.err
    assert "Expecting property name enclosed in double quotes" in captured.err

def test_load_prayer_times_missing_expected_keys(temp_prayer_times_file, capsys):
    """Tests loading from a JSON file missing some expected prayer keys."""
    partial_data = {"Fajr": "05:00", "Dhuhr": "13:00"} # Missing Asr, Maghrib, Isha
    temp_prayer_times_file.write_text(json.dumps(partial_data))
    
    app = AdhanClockApp(prayer_times_filepath=str(temp_prayer_times_file))
    assert app.prayer_times is None
    captured = capsys.readouterr()
    assert f"Warning: Malformed prayer times data in {temp_prayer_times_file} (missing expected keys)." in captured.out

def test_load_prayer_times_io_error(temp_prayer_times_file, capsys):
    """Tests handling of an IOError during file reading."""
    # Simulate an IOError during file open
    with patch('builtins.open', mock_open()) as mocked_open:
        mocked_open.side_effect = IOError("Permission denied")
        with patch('os.path.exists', return_value=True): # Pretend file exists
            app = AdhanClockApp(prayer_times_filepath=str(temp_prayer_times_file))
            assert app.prayer_times is None
            captured = capsys.readouterr()
            assert f"Error reading or parsing prayer times from {temp_prayer_times_file}: Permission denied" in captured.err

# --- get_next_prayer_info tests ---

def test_get_next_prayer_info_no_times_loaded():
    """Tests get_next_prayer_info when no prayer times are loaded."""
    # Ensure no times are loaded by using a non-existent file path
    app = AdhanClockApp(prayer_times_filepath="nonexistent_file.json") 
    name, time, dt = app.get_next_prayer_info(datetime.now())
    assert name == "No prayer times loaded"
    assert time is None
    assert dt is None

@pytest.mark.parametrize("current_time_str, expected_prayer_name, expected_time_str", [
    ("04:30", "Fajr", "05:00"),  # Before Fajr
    ("05:30", "Sunrise", "06:30"), # Between Fajr and Sunrise
    ("06:45", "Dhuhr", "13:00"),  # After Sunrise, before Dhuhr
    ("13:15", "Asr", "17:00"),   # After Dhuhr, before Asr
    ("17:15", "Sunset", "19:30"), # After Asr, before Sunset
    ("19:35", "Maghrib", "19:45"), # After Sunset, before Maghrib
    ("20:00", "Isha", "21:00"),   # After Maghrib, before Isha
])
def test_get_next_prayer_info_next_prayer_today(temp_prayer_times_file, mock_prayer_times_data, current_time_str, expected_prayer_name, expected_time_str):
    """Tests finding the next prayer for various times of the day."""
    temp_prayer_times_file.write_text(json.dumps(mock_prayer_times_data))
    app = AdhanClockApp(prayer_times_filepath=str(temp_prayer_times_file))

    current_dt = datetime.strptime(f"2023-10-27 {current_time_str}", "%Y-%m-%d %H:%M")
    name, time, dt = app.get_next_prayer_info(current_dt)

    assert name == expected_prayer_name
    assert time == expected_time_str
    assert dt == datetime.strptime(f"2023-10-27 {expected_time_str}", "%Y-%m-%d %H:%M")

def test_get_next_prayer_info_all_prayers_done_today(temp_prayer_times_file, mock_prayer_times_data):
    """Tests when all prayers for today are passed, it suggests Fajr for tomorrow."""
    temp_prayer_times_file.write_text(json.dumps(mock_prayer_times_data))
    app = AdhanClockApp(prayer_times_filepath=str(temp_prayer_times_file))

    current_dt = datetime.strptime("2023-10-27 22:00", "%Y-%m-%d %H:%M") # After Isha
    name, time, dt = app.get_next_prayer_info(current_dt)

    assert name == "Fajr (Tomorrow)"
    assert time == "05:00" # Fajr time from mock data
    assert dt == datetime.strptime("2023-10-28 05:00", "%Y-%m-%d %H:%M")

def test_get_next_prayer_info_invalid_time_format_in_data(temp_prayer_times_file, capsys):
    """Tests that invalid time formats in the prayer times data are skipped."""
    bad_data = {
        "Fajr": "05:00",
        "Dhuhr": "invalid_time", # This will be skipped
        "Asr": "17:00",
        "Maghrib": "19:45",
        "Isha": "21:00"
    }
    temp_prayer_times_file.write_text(json.dumps(bad_data))
    app = AdhanClockApp(prayer_times_filepath=str(temp_prayer_times_file))

    current_dt = datetime.strptime("2023-10-27 13:30", "%Y-%m-%d %H:%M") # After Fajr, Dhuhr is invalid, so next is Asr
    name, time, dt = app.get_next_prayer_info(current_dt)

    assert name == "Asr" # Should skip invalid Dhuhr and go to Asr
    assert time == "17:00"
    captured = capsys.readouterr()
    assert "Warning: Invalid time format for Dhuhr: 'invalid_time'" in captured.out

def test_get_next_prayer_info_malformed_fajr_tomorrow(temp_prayer_times_file, capsys):
    """Tests behavior when tomorrow's Fajr time is malformed."""
    bad_fajr_data = {
        "Fajr": "bad_fajr_time",
        "Dhuhr": "13:00", "Asr": "17:00", "Maghrib": "19:45", "Isha": "21:00"
    }
    temp_prayer_times_file.write_text(json.dumps(bad_fajr_data))
    app = AdhanClockApp(prayer_times_filepath=str(temp_prayer_times_file))

    current_dt = datetime.strptime("2023-10-27 22:00", "%Y-%m-%d %H:%M") # After Isha
    name, time, dt = app.get_next_prayer_info(current_dt)

    # The current logic will print a warning and then fall through to "All prayers done for today"
    assert name == "All prayers done for today"
    assert time is None
    assert dt is None
    captured = capsys.readouterr()
    assert "Warning: Invalid Fajr time format for tomorrow: 'bad_fajr_time'" in captured.out

def test_get_next_prayer_info_all_prayers_done_no_fajr_key(temp_prayer_times_file, capsys):
    """Tests when all prayers for today are passed and Fajr is not in the data."""
    no_fajr_data = {
        "Dhuhr": "13:00", "Asr": "17:00", "Maghrib": "19:45", "Isha": "21:00"
    }
    temp_prayer_times_file.write_text(json.dumps(no_fajr_data))
    app = AdhanClockApp(prayer_times_filepath=str(temp_prayer_times_file))

    current_dt = datetime.strptime("2023-10-27 22:00", "%Y-%m-%d %H:%M") # After Isha
    name, time, dt = app.get_next_prayer_info(current_dt)

    assert name == "All prayers done for today"
    assert time is None
    assert dt is None

# --- format_time_display tests ---

def test_format_time_display_valid():
    """Tests formatting with a valid prayer name and time."""
    app = AdhanClockApp() # No file needed for this method
    result = app.format_time_display("Fajr", "05:00")
    assert result == "Fajr: 05:00"

def test_format_time_display_none_time():
    """Tests formatting when the time string is None."""
    app = AdhanClockApp()
    result = app.format_time_display("Maghrib", None)
    assert result == "Maghrib: N/A"

def test_format_time_display_empty_time_string():
    """Tests formatting when the time string is empty."""
    app = AdhanClockApp()
    result = app.format_time_display("Isha", "")
    assert result == "Isha: N/A"

# --- run_gui tests ---

def test_run_gui(mock_prayer_times_data, temp_prayer_times_file, capsys):
    """Tests that run_gui calls get_next_prayer_info and prints output."""
    temp_prayer_times_file.write_text(json.dumps(mock_prayer_times_data))
    
    app = AdhanClockApp(prayer_times_filepath=str(temp_prayer_times_file))

    # Patch datetime.now() but allow other datetime functions to work normally
    with patch('main.datetime') as mock_dt:
        mock_dt.now.return_value = datetime(2023, 10, 27, 10, 0) # Mock current time to 10:00
        mock_dt.strptime = datetime.strptime # Ensure strptime still works
        # Allow other datetime methods (like timedelta) to work on mocked datetime objects
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw) 
        
        app.run_gui()
        captured = capsys.readouterr()

        assert "Starting Adhan Clock GUI..." in captured.out
        assert "Current time: 10:00:00" in captured.out
        # Based on mock_prayer_times_data and current_time 10:00, next prayer should be Dhuhr at 13:00
        assert "Next Prayer: Dhuhr at 13:00" in captured.out
        assert "GUI application logic would continue here..." in captured.out

def test_run_gui_no_prayer_times(capsys):
    """Tests run_gui when no prayer times are loaded."""
    # Ensure no prayer times are loaded by passing a non-existent file
    app = AdhanClockApp(prayer_times_filepath="non_existent.json")

    with patch('main.datetime') as mock_dt:
        mock_dt.now.return_value = datetime(2023, 10, 27, 10, 0)
        mock_dt.strptime = datetime.strptime
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

        app.run_gui()
        captured = capsys.readouterr()

        assert "Starting Adhan Clock GUI..." in captured.out
        assert "Current time: 10:00:00" in captured.out
        assert "Next Prayer: No prayer times loaded at N/A" in captured.out
        assert "GUI application logic would continue here..." in captured.out
```