```python
from datetime import datetime, timedelta
import pytest
import os
from main import AdhanClockApp, PRAYER_TIMES_FILE

# Assume conftest.py is in the tests/ directory and provides fixtures like:
# setup_prayer_times_file: creates a valid adhan_times.json
# setup_malformed_prayer_times_file: creates a JSON with missing keys
# setup_invalid_time_format_file: creates a JSON with bad time formats
# setup_empty_prayer_times_file: creates an empty JSON

def test_init_with_default_filepath(setup_prayer_times_file):
    """Test initialization with default filepath."""
    # Ensure the default file exists in the current directory (pytest tmp_path context)
    with open(PRAYER_TIMES_FILE, 'w') as f:
        f.write(setup_prayer_times_file.read_text())
        
    app = AdhanClockApp()
    assert app.prayer_times_filepath == PRAYER_TIMES_FILE
    assert app.prayer_times is not None
    assert "Fajr" in app.prayer_times

def test_init_with_custom_filepath(tmp_path, setup_prayer_times_file):
    """Test initialization with a custom filepath."""
    custom_filepath = tmp_path / "custom_adhan.json"
    with open(custom_filepath, 'w') as f:
        f.write(setup_prayer_times_file.read_text())
        
    app = AdhanClockApp(prayer_times_filepath=str(custom_filepath))
    assert app.prayer_times_filepath == str(custom_filepath)
    assert app.prayer_times is not None
    assert "Fajr" in app.prayer_times

def test_load_prayer_times_file_not_found():
    """Test loading when the prayer times file does not exist."""
    non_existent_file = "non_existent_adhan_times.json"
    if os.path.exists(non_existent_file):
        os.remove(non_existent_file) # Ensure it doesn't exist

    app = AdhanClockApp(prayer_times_filepath=non_existent_file)
    # Expecting a warning message from _load_prayer_times
    # The message printing is a side effect, not directly testable without mocking stdout.
    # For now, we check the return value of the load method indirectly via app.prayer_times.
    assert app.prayer_times is None

def test_load_prayer_times_malformed_data(setup_malformed_prayer_times_file):
    """Test loading a malformed prayer times JSON file."""
    app = AdhanClockApp()
    # Expecting a warning message about missing keys
    assert app.prayer_times is None

def test_load_prayer_times_invalid_json(tmp_path):
    """Test loading a file with invalid JSON content."""
    invalid_json_filepath = tmp_path / "invalid.json"
    with open(invalid_json_filepath, 'w') as f:
        f.write("{ 'Fajr': '05:00', ") # Incomplete JSON
    
    app = AdhanClockApp(prayer_times_filepath=str(invalid_json_filepath))
    # Expecting an error message during load
    assert app.prayer_times is None

def test_load_prayer_times_invalid_time_format(setup_invalid_time_format_file):
    """Test loading a file with invalid time formats for some prayers."""
    app = AdhanClockApp()
    # _load_prayer_times itself might succeed, but the internal conversion might fail later
    # The current _load_prayer_times doesn't strictly validate time formats, 
    # it relies on datetime.strptime which will raise ValueError.
    # This test ensures that the app can handle such cases gracefully (e.g., skip or report)
    assert app.prayer_times is not None
    assert len(app.prayer_times) == 6 # All entries are loaded, even if some have bad format for datetime conversion
    # The warning for invalid time format will be printed when get_next_prayer_info is called.

def test_get_next_prayer_info_before_fajr(setup_prayer_times_file):
    """Test when current time is before the first prayer (Fajr)."""
    # Assume current_dt is just before Fajr
    current_dt = datetime(2023, 10, 27, 4, 59, 0)
    app = AdhanClockApp()
    name, time_str, prayer_dt = app.get_next_prayer_info(current_dt)
    
    assert name == "Fajr"
    assert time_str == "05:00"
    assert prayer_dt == datetime(2023, 10, 27, 5, 0, 0)

def test_get_next_prayer_info_after_fajr_before_sunrise(setup_prayer_times_file):
    """Test when current time is after Fajr but before Sunrise."""
    current_dt = datetime(2023, 10, 27, 6, 0, 0)
    app = AdhanClockApp()
    name, time_str, prayer_dt = app.get_next_prayer_info(current_dt)
    
    assert name == "Sunrise"
    assert time_str == "06:15"
    assert prayer_dt == datetime(2023, 10, 27, 6, 15, 0)

def test_get_next_prayer_info_after_all_prayers_today(setup_prayer_times_file):
    """Test when current time is after the last prayer (Isha) for today."""
    current_dt = datetime(2023, 10, 27, 21, 0, 0)
    app = AdhanClockApp()
    name, time_str, prayer_dt = app.get_next_prayer_info(current_dt)
    
    # Should suggest Fajr for the next day
    assert name == "Fajr (Tomorrow)"
    assert time_str == "05:00"
    assert prayer_dt == datetime(2023, 10, 28, 5, 0, 0)

def test_get_next_prayer_info_exactly_at_prayer_time(setup_prayer_times_file):
    """Test when current time is exactly at a prayer time."""
    current_dt = datetime(2023, 10, 27, 13, 0, 0) # Dhuhr time
    app = AdhanClockApp()
    name, time_str, prayer_dt = app.get_next_prayer_info(current_dt)
    
    # Since current_dt is *at* Dhuhr, the next prayer should be Asr
    assert name == "Asr"
    assert time_str == "16:30"
    assert prayer_dt == datetime(2023, 10, 27, 16, 30, 0)

def test_get_next_prayer_info_no_prayer_times_loaded():
    """Test get_next_prayer_info when prayer_times is None."""
    app = AdhanClockApp()
    app.prayer_times = None # Manually set to None to simulate loading failure
    current_dt = datetime.now()
    name, time_str, prayer_dt = app.get_next_prayer_info(current_dt)
    
    assert name == "No prayer times loaded"
    assert time_str is None
    assert prayer_dt is None

def test_get_next_prayer_info_with_invalid_time_formats_present(setup_invalid_time_format_file):
    """Test get_next_prayer_info when the loaded data has invalid time formats."""
    # Invalid time format for Sunrise, but others are valid.
    current_dt = datetime(2023, 10, 27, 5, 30, 0) # After Fajr, before Sunrise
    app = AdhanClockApp()
    
    # The `get_next_prayer_info` should skip the invalid Sunrise time and find the next valid prayer.
    # In this case, it should correctly proceed to Dhuhr.
    name, time_str, prayer_dt = app.get_next_prayer_info(current_dt)
    
    assert name == "Dhuhr"
    assert time_str == "13:00"
    assert prayer_dt == datetime(2023, 10, 27, 13, 0, 0)

def test_get_next_prayer_info_all_today_passed_tomorrow_fajr_invalid(tmp_path):
    """Test when all today's prayers are passed, and tomorrow's Fajr time is invalid."""
    file_path = tmp_path / PRAYER_TIMES_FILE
    invalid_fajr_data = {
        "Fajr": "invalid-time", # Invalid Fajr time
        "Sunrise": "06:15",
        "Dhuhr": "13:00",
        "Asr": "16:30",
        "Maghrib": "18:45",
        "Isha": "20:00"
    }
    with open(file_path, 'w') as f:
        json.dump(invalid_fajr_data, f, indent=4)

    app = AdhanClockApp(prayer_times_filepath=str(file_path))
    current_dt = datetime(2023, 10, 27, 21, 0, 0) # After Isha
    name, time_str, prayer_dt = app.get_next_prayer_info(current_dt)
    
    # Since tomorrow's Fajr is invalid and no other prayer is found, it should fall back.
    assert name == "All prayers done for today"
    assert time_str is None
    assert prayer_dt is None

def test_format_time_display_with_time():
    """Test format_time_display with a valid time string."""
    app = AdhanClockApp()
    prayer_name = "Fajr"
    time_str = "05:00"
    formatted = app.format_time_display(prayer_name, time_str)
    assert formatted == "Fajr: 05:00"

def test_format_time_display_without_time():
    """Test format_time_display when time string is None or empty."""
    app = AdhanClockApp()
    prayer_name = "Isha"
    time_str = None
    formatted = app.format_time_display(prayer_name, time_str)
    assert formatted == "Isha: N/A"

    time_str_empty = ""
    formatted_empty = app.format_time_display(prayer_name, time_str_empty)
    assert formatted_empty == "Isha: N/A"

def test_run_gui_prints_basic_info(capsys):
    """Test that run_gui prints basic information without crashing."""
    # This is a basic smoke test for the run_gui method.
    # It primarily checks if it runs and prints expected output.
    app = AdhanClockApp()
    
    # Mock the datetime.now() to get deterministic results for testing.
    # This requires patching datetime.now
    with pytest.MonkeyPatch.context() as mp:
        fixed_time = datetime(2023, 10, 27, 12, 0, 0) # Around Dhuhr
        mp.setattr(datetime, 'now', lambda: fixed_time)
        
        app.run_gui()
        
        captured = capsys.readouterr()
        
        assert "Starting Adhan Clock GUI..." in captured.out
        assert f"Current time: {fixed_time.strftime('%H:%M:%S')}" in captured.out
        # Based on the fixed time and default prayer times, next prayer is Asr
        assert "Next Prayer: Asr at 16:30" in captured.out 
        assert "GUI application logic would continue here..." in captured.out

```

**3. Add Tests for `updateAzaanTimers.py`**

This involves testing the `fetch_prayer_times`, `save_prayer_times`, and `main` functions. Mocking `requests` and `argparse` will be crucial here.
