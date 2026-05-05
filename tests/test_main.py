```python
import pytest
import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Assuming main.py is in the root directory of the project
# If it's in a subdirectory, adjust the import path accordingly.
from main import AdhanClockApp, PRAYER_TIMES_FILE

# --- Fixtures ---

@pytest.fixture
def app():
    """Fixture to create an instance of AdhanClockApp."""
    return AdhanClockApp()

@pytest.fixture
def mock_prayer_times_file(tmp_path):
    """Fixture to create a temporary prayer times JSON file."""
    filepath = tmp_path / PRAYER_TIMES_FILE
    prayer_times_data = {
        "Fajr": "05:00",
        "Sunrise": "06:15",
        "Dhuhr": "13:00",
        "Asr": "16:30",
        "Sunset": "17:30",
        "Maghrib": "17:30",
        "Isha": "19:00"
    }
    with open(filepath, 'w') as f:
        json.dump(prayer_times_data, f)
    return str(filepath)

@pytest.fixture
def mock_malformed_prayer_times_file(tmp_path):
    """Fixture to create a temporary malformed prayer times JSON file."""
    filepath = tmp_path / PRAYER_TIMES_FILE
    malformed_data = {
        "Fajr": "05:00",
        "Dhuhr": "13:00",
        # Missing Asr, Maghrib, Isha
    }
    with open(filepath, 'w') as f:
        json.dump(malformed_data, f)
    return str(filepath)

@pytest.fixture
def mock_invalid_time_format_file(tmp_path):
    """Fixture to create a temporary prayer times JSON file with invalid time format."""
    filepath = tmp_path / PRAYER_TIMES_FILE
    data_with_invalid_time = {
        "Fajr": "05:00",
        "Sunrise": "06:15",
        "Dhuhr": "13:00",
        "Asr": "16:30",
        "Sunset": "17:30",
        "Maghrib": "invalid-time", # Invalid time
        "Isha": "19:00"
    }
    with open(filepath, 'w') as f:
        json.dump(data_with_invalid_time, f)
    return str(filepath)

# --- Test __init__ ---

def test_init_default_filepath(app):
    """Test initialization with default filepath."""
    assert app.prayer_times_filepath == PRAYER_TIMES_FILE
    # When initialized without a specific file, it tries to load the default.
    # If the default doesn't exist, it will print a warning and self.prayer_times will be None.
    # For this test, we don't create the file, so we expect None.
    assert app.prayer_times is None

def test_init_custom_filepath(tmp_path):
    """Test initialization with a custom filepath."""
    custom_path = tmp_path / "custom_adhan.json"
    app = AdhanClockApp(prayer_times_filepath=str(custom_path))
    assert app.prayer_times_filepath == str(custom_path)
    # Again, file doesn't exist, so prayer_times should be None.
    assert app.prayer_times is None

# --- Test _load_prayer_times ---

def test_load_prayer_times_file_not_found(app, capsys):
    """Test loading prayer times when the file does not exist."""
    # Ensure the default file does not exist for this test
    if os.path.exists(PRAYER_TIMES_FILE):
        os.remove(PRAYER_TIMES_FILE)

    loaded_times = app._load_prayer_times()
    captured = capsys.readouterr()

    assert loaded_times is None
    assert f"Warning: Prayer times file not found at {PRAYER_TIMES_FILE}" in captured.out

def test_load_prayer_times_malformed_json(tmp_path, capsys):
    """Test loading prayer times with malformed JSON."""
    filepath = tmp_path / "malformed.json"
    with open(filepath, 'w') as f:
        f.write("{invalid json")

    app = AdhanClockApp(prayer_times_filepath=str(filepath))
    loaded_times = app._load_prayer_times()
    captured = capsys.readouterr()

    assert loaded_times is None
    assert "Error reading or parsing prayer times from" in captured.out
    assert "JSONDecodeError" in captured.out

def test_load_prayer_times_io_error(tmp_path, capsys):
    """Test loading prayer times with an IOError."""
    filepath = tmp_path / "unreadable.json"
    # Create an empty file but make it unreadable (requires OS-level permissions, tricky to mock directly)
    # For simplicity, we can simulate the error using patch if direct file manipulation is hard.
    # A more robust way is to patch open itself to raise an error.
    with open(filepath, 'w') as f: # Create the file
        f.write('{"Fajr": "05:00"}')

    with patch('builtins.open', side_effect=IOError("Permission denied")) as mock_open:
        app = AdhanClockApp(prayer_times_filepath=str(filepath))
        loaded_times = app._load_prayer_times()
        captured = capsys.readouterr()

        assert loaded_times is None
        mock_open.assert_called_once_with(str(filepath), 'r')
        assert "Error reading or parsing prayer times from" in captured.out
        assert "IOError" in captured.out

def test_load_prayer_times_malformed_data_missing_keys(tmp_path, capsys):
    """Test loading prayer times with valid JSON but missing expected keys."""
    filepath = tmp_path / PRAYER_TIMES_FILE
    malformed_data = {"Fajr": "05:00", "Dhuhr": "13:00"} # Missing Asr, Maghrib, Isha
    with open(filepath, 'w') as f:
        json.dump(malformed_data, f)

    app = AdhanClockApp(prayer_times_filepath=str(filepath))
    loaded_times = app._load_prayer_times()
    captured = capsys.readouterr()

    assert loaded_times is None
    assert f"Warning: Malformed prayer times data in {filepath} (missing expected keys)." in captured.out

def test_load_prayer_times_success(mock_prayer_times_file, capsys):
    """Test successfully loading prayer times from a valid JSON file."""
    # The fixture mock_prayer_times_file creates the file and returns its path.
    app = AdhanClockApp(prayer_times_filepath=mock_prayer_times_file)
    loaded_times = app._load_prayer_times()
    captured = capsys.readouterr()

    expected_times = {
        "Fajr": "05:00",
        "Sunrise": "06:15",
        "Dhuhr": "13:00",
        "Asr": "16:30",
        "Sunset": "17:30",
        "Maghrib": "17:30",
        "Isha": "19:00"
    }
    assert loaded_times == expected_times
    assert f"Prayer times loaded successfully from {mock_prayer_times_file}" in captured.out

def test_load_prayer_times_with_invalid_time_format(mock_invalid_time_format_file, capsys):
    """Test loading prayer times where one time entry is invalid."""
    app = AdhanClockApp(prayer_times_filepath=mock_invalid_time_format_file)
    loaded_times = app._load_prayer_times()
    captured = capsys.readouterr()

    expected_times = {
        "Fajr": "05:00",
        "Sunrise": "06:15",
        "Dhuhr": "13:00",
        "Asr": "16:30",
        "Sunset": "17:30",
        # Maghrib is missing because of invalid time format
        "Isha": "19:00"
    }
    # The function loads what it can, and issues warnings for bad ones.
    # The get_next_prayer_info method will also need to handle this.
    # The _load_prayer_times should still return the valid ones.
    # BUT, the current _load_prayer_times returns None if validation fails based on expected_prayers.
    # Re-reading the code: "if all(p in data for p in expected_prayers)"
    # This means it will return None if ANY expected prayer is missing.
    # So, if Maghrib time is invalid, it's not loaded, then 'Maghrib' won't be in the returned dict.
    # The current implementation of _load_prayer_times would return None here due to missing Maghrib.
    # Let's adjust the test expectation to match the current `_load_prayer_times` behavior.

    # Current _load_prayer_times returns None if any expected prayer is missing
    # OR if there's a JSON error.
    # It does print a warning for invalid time formats *after* successful loading and validation.
    # Let's refine the test to check the behavior *after* loading, and then how `get_next_prayer_info` uses it.

    # Test for _load_prayer_times itself: It should have printed a warning for invalid time.
    # And it should return the dictionary *only if* all expected prayers are present.
    # If 'Maghrib' is invalid, it won't be in the dict, and thus 'all(p in data for p in expected_prayers)' will fail.
    assert loaded_times is None # Based on current _load_prayer_times validation
    assert f"Warning: Malformed prayer times data in {mock_invalid_time_format_file} (missing expected keys)." in captured.out
    # The "Invalid time format for Maghrib" warning happens inside `get_next_prayer_info` if `prayer_times` is not None.
    # Since `_load_prayer_times` returns None, that warning won't appear here.

# --- Test get_next_prayer_info ---

@pytest.fixture
def app_with_times(mock_prayer_times_file):
    """Fixture to create an AdhanClockApp instance with loaded prayer times."""
    app = AdhanClockApp(prayer_times_filepath=mock_prayer_times_file)
    return app

def test_get_next_prayer_info_no_times_loaded(app, capsys):
    """Test get_next_prayer_info when no prayer times are loaded."""
    current_dt = datetime.now()
    name, time_str, dt_obj = app.get_next_prayer_info(current_dt)
    captured = capsys.readouterr()
    assert name == "No prayer times loaded"
    assert time_str is None
    assert dt_obj is None
    assert "Warning: Prayer times file not found at" in captured.out # From __init__ calling _load_prayer_times

def test_get_next_prayer_info_current_time_before_all_prayers(app_with_times):
    """Test finding the next prayer when current time is before all prayers for the day."""
    # Assume today is 2023-10-27
    current_dt = datetime(2023, 10, 27, 4, 0) # Before Fajr
    name, time_str, dt_obj = app_with_times.get_next_prayer_info(current_dt)

    assert name == "Fajr"
    assert time_str == "05:00"
    assert dt_obj == datetime(2023, 10, 27, 5, 0)

def test_get_next_prayer_info_current_time_between_prayers(app_with_times):
    """Test finding the next prayer when current time is between two prayers."""
    current_dt = datetime(2023, 10, 27, 14, 0) # After Dhuhr, before Asr
    name, time_str, dt_obj = app_with_times.get_next_prayer_info(current_dt)

    assert name == "Asr"
    assert time_str == "16:30"
    assert dt_obj == datetime(2023, 10, 27, 16, 30)

def test_get_next_prayer_info_current_time_is_a_prayer_time(app_with_times):
    """Test finding the next prayer when current time exactly matches a prayer time."""
    # The logic should find the *next* prayer, so if current_dt is exactly Dhuhr,
    # it should find Asr.
    current_dt = datetime(2023, 10, 27, 13, 0) # Exactly Dhuhr time
    name, time_str, dt_obj = app_with_times.get_next_prayer_info(current_dt)

    assert name == "Asr"
    assert time_str == "16:30"
    assert dt_obj == datetime(2023, 10, 27, 16, 30)

def test_get_next_prayer_info_current_time_after_last_prayer(app_with_times):
    """Test finding the next prayer when current time is after all prayers for today."""
    current_dt = datetime(2023, 10, 27, 20, 0) # After Isha
    name, time_str, dt_obj = app_with_times.get_next_prayer_info(current_dt)

    assert name == "Fajr (Tomorrow)"
    assert time_str == "05:00"
    assert dt_obj == datetime(2023, 10, 28, 5, 0) # Fajr tomorrow

def test_get_next_prayer_info_with_sunset_and_maghrib_same_time(app_with_times):
    """Test edge case where Sunset and Maghrib times are identical."""
    # Modify app_with_times to simulate this condition for the test
    app_with_times.prayer_times["Sunset"] = "17:30" # Already set
    app_with_times.prayer_times["Maghrib"] = "17:30" # Already set

    current_dt = datetime(2023, 10, 27, 17, 0) # Before Sunset/Maghrib
    name, time_str, dt_obj = app_with_times.get_next_prayer_info(current_dt)

    # The loop iterates in prayer_order. It will find Sunset first.
    # Since 'Sunset' is not in expected_prayers for direct comparison to 'next_prayer_dt',
    # and it's handled as a marker. The logic for finding next prayer checks `prayer_dt_objects[prayer] > current_dt`.
    # So if current_dt is 17:00, Sunset (17:30) will be picked as next.
    # But Maghrib is also at 17:30. The code *should* ideally pick Maghrib if it's after Sunset,
    # or handle them.
    # The current logic iterates through prayer_order: Fajr, Sunrise, Dhuhr, Asr, Sunset, Maghrib, Isha.
    # If current_dt = 17:00, then:
    # Sunset (17:30) > current_dt. So `next_prayer_name` becomes "Sunset", `next_prayer_dt` becomes 17:30.
    # The loop breaks.
    # The return value will be based on `next_prayer_name` which is "Sunset".
    # This behavior might be unexpected if Maghrib is also at 17:30.
    # The existing code picks 'Sunset' as the next prayer. We must preserve this.
    assert name == "Sunset"
    assert time_str == "17:30"
    assert dt_obj == datetime(2023, 10, 27, 17, 30)

def test_get_next_prayer_info_tomorrow_fajr_invalid_time(tmp_path, capsys):
    """Test next prayer logic when tomorrow's Fajr time is invalid."""
    filepath = tmp_path / PRAYER_TIMES_FILE
    data_invalid_tomorrow_fajr = {
        "Fajr": "invalid-fajr-time", # Invalid time for Fajr
        "Sunrise": "06:15",
        "Dhuhr": "13:00",
        "Asr": "16:30",
        "Sunset": "17:30",
        "Maghrib": "17:30",
        "Isha": "19:00"
    }
    with open(filepath, 'w') as f:
        json.dump(data_invalid_tomorrow_fajr, f)

    app = AdhanClockApp(prayer_times_filepath=str(filepath))
    # Manually load times, as _load_prayer_times validates `all(p in data)` which would fail here.
    # Let's assume _load_prayer_times returned valid data, and then we test the tomorrow logic.
    # To achieve this, we need to mock `_load_prayer_times` or carefully construct data.

    # A more direct way: set prayer_times directly for testing.
    app.prayer_times = {
        "Fajr": "05:00", # Valid today
        "Sunrise": "06:15",
        "Dhuhr": "13:00",
        "Asr": "16:30",
        "Sunset": "17:30",
        "Maghrib": "17:30",
        "Isha": "19:00",
        # Now test the scenario where *tomorrow's* Fajr is invalid
        # This requires simulating current_dt being after Isha.
    }
    # Let's simulate Fajr time being invalid FOR THE PURPOSE OF LOADING FOR TOMORROW
    # This is tricky because `datetime.strptime` is called inside `get_next_prayer_info`.
    # The `self.prayer_times["Fajr"]` is used. If `self.prayer_times` contains "invalid-fajr-time",
    # `strptime` will raise ValueError.

    # Scenario: Current time is late, all prayers for today are past.
    current_dt = datetime(2023, 10, 27, 20, 0) # After Isha

    # Mock `self.prayer_times` to have an invalid Fajr entry for tomorrow's calculation.
    original_prayer_times = app.prayer_times.copy()
    app.prayer_times["Fajr"] = "invalid-fajr-time"

    with patch('builtins.print') as mock_print:
        name, time_str, dt_obj = app.get_next_prayer_info(current_dt)

        assert name == "All prayers done for today" # Fallback message because tomorrow's Fajr failed.
        assert time_str is None
        assert dt_obj is None
        assert "Warning: Invalid Fajr time format for tomorrow: 'invalid-fajr-time'" in captured.out.strip()

    # Restore original prayer times if needed for subsequent tests if this app instance is reused.
    app.prayer_times = original_prayer_times

def test_get_next_prayer_info_tomorrow_fajr_not_in_times(app_with_times):
    """Test next prayer logic when tomorrow's Fajr is needed but not present in times."""
    current_dt = datetime(2023, 10, 27, 20, 0) # After Isha

    # Remove Fajr from prayer times for this test scenario
    original_fajr_time = app_with_times.prayer_times.pop("Fajr", None)

    with patch('builtins.print') as mock_print:
        name, time_str, dt_obj = app_with_times.get_next_prayer_info(current_dt)

        assert name == "All prayers done for today" # Fallback message
        assert time_str is None
        assert dt_obj is None
        assert "Warning: Malformed prayer times data" not in captured.out # Should not trigger malformed if current day is fine

    # Restore Fajr if this app instance is reused
    if original_fajr_time:
        app_with_times.prayer_times["Fajr"] = original_fajr_time

def test_get_next_prayer_info_all_prayers_done_for_today_fallback(app_with_times):
    """Test the fallback message when all prayers are done and no tomorrow Fajr can be set."""
    # This scenario is covered by test_get_next_prayer_info_tomorrow_fajr_invalid_time
    # and test_get_next_prayer_info_tomorrow_fajr_not_in_times.
    # The current implementation returns "All prayers done for today" if the tomorrow Fajr calculation fails.
    pass # Covered by other tests.

def test_get_next_prayer_info_current_dt_on_sunset(app_with_times):
    """Test behavior when current time matches Sunset."""
    # Sunrise, Dhuhr, Asr, Sunset, Maghrib, Isha are all in prayer_order.
    # If current_dt = 17:30, and Sunset is at 17:30, and Maghrib is at 17:30.
    # The loop finds `prayer_dt_objects[prayer] > current_dt`.
    # So, if current_dt is exactly 17:30, then Sunset (17:30) is NOT > current_dt.
    # Maghrib (17:30) is NOT > current_dt.
    # Isha (19:00) IS > current_dt.
    current_dt = datetime(2023, 10, 27, 17, 30) # Exactly Sunset/Maghrib time
    name, time_str, dt_obj = app_with_times.get_next_prayer_info(current_dt)

    assert name == "Isha"
    assert time_str == "19:00"
    assert dt_obj == datetime(2023, 10, 27, 19, 0)

def test_get_next_prayer_info_with_invalid_times_in_loaded_data(mock_invalid_time_format_file, capsys):
    """
    Test get_next_prayer_info when _load_prayer_times returned None due to
    malformed data (e.g., missing keys, or in this case, invalid time format leading to missing keys).
    """
    app = AdhanClockApp(prayer_times_filepath=mock_invalid_time_format_file)
    # _load_prayer_times will return None because Maghrib is missing due to invalid time format.
    # So self.prayer_times will be None.
    current_dt = datetime.now()
    name, time_str, dt_obj = app.get_next_prayer_info(current_dt)

    assert name == "No prayer times loaded"
    assert time_str is None
    assert dt_obj is None
    # The warning about invalid time format for Maghrib is printed inside _load_prayer_times,
    # which returns None *before* get_next_prayer_info is called.
    # Then get_next_prayer_info prints its own "No prayer times loaded" warning from the None check.
    captured = capsys.readouterr()
    assert "Warning: Malformed prayer times data in" in captured.out
    # The print from `_load_prayer_times` indicating missing keys should appear.


# --- Test format_time_display ---

def test_format_time_display_with_time(app):
    """Test format_time_display when time string is provided."""
    prayer_name = "Fajr"
    time_str = "05:00"
    formatted_string = app.format_time_display(prayer_name, time_str)
    assert formatted_string == "Fajr: 05:00"

def test_format_time_display_without_time(app):
    """Test format_time_display when time string is None or empty."""
    prayer_name = "Isha"
    time_str = None
    formatted_string = app.format_time_display(prayer_name, time_str)
    assert formatted_string == "Isha: N/A"

    time_str_empty = ""
    formatted_string_empty = app.format_time_display(prayer_name, time_str_empty)
    assert formatted_string_empty == "Isha: N/A"

# --- Test run_gui ---

@patch('builtins.print')
def test_run_gui_prints_status(mock_print, app_with_times):
    """Test that run_gui prints the current status."""
    # Monkeypatch datetime.now to control current time for predictability
    fixed_time = datetime(2023, 10, 27, 14, 0) # After Dhuhr, before Asr
    with patch('datetime.datetime') as mock_datetime:
        mock_datetime.now.return_value = fixed_time
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw) # Allow other datetime calls

        app_with_times.run_gui()

    # Expected calls to print. Order matters here.
    mock_print.assert_any_call("Starting Adhan Clock GUI...")
    mock_print.assert_any_call(f"Current time: {fixed_time.strftime('%H:%M:%S')}")
    mock_print.assert_any_call("Next Prayer: Asr at 16:30")
    mock_print.assert_any_call("GUI application logic would continue here...")

def test_run_gui_no_times_loaded(app, capsys):
    """Test run_gui when no prayer times are loaded."""
    # Monkeypatch datetime.now
    fixed_time = datetime(2023, 10, 27, 10, 0)
    with patch('datetime.datetime') as mock_datetime:
        mock_datetime.now.return_value = fixed_time
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        app.run_gui()

    captured = capsys.readouterr()
    assert "Starting Adhan Clock GUI..." in captured.out
    assert "Current time: 10:00:00" in captured.out # Default seconds will be 00
    # The warning "No prayer times loaded" comes from get_next_prayer_info which is called by run_gui.
    # It is also preceded by the "Warning: Prayer times file not found at..." from __init__.
    assert "Next Prayer: No prayer times loaded at N/A" in captured.out
    assert "GUI application logic would continue here..." in captured.out

```