```python
import pytest
from datetime import datetime, timedelta
import json
import os

from main import AdhanClockApp

# Helper to create a dummy prayer times file
def create_dummy_prayer_times_file(filepath="adhan_times.json", content=None):
    if content is None:
        content = {
            "Fajr": "05:00",
            "Sunrise": "06:30",
            "Dhuhr": "13:00",
            "Asr": "16:00",
            "Sunset": "18:30",
            "Maghrib": "18:30",
            "Isha": "20:00"
        }
    with open(filepath, 'w') as f:
        json.dump(content, f, indent=4)

# --- Tests for AdhanClockApp ---

def test_init_default_filepath():
    """Test initialization with default filepath."""
    app = AdhanClockApp()
    assert app.prayer_times_filepath == "adhan_times.json"

def test_init_custom_filepath():
    """Test initialization with a custom filepath."""
    custom_path = "my_custom_times.json"
    app = AdhanClockApp(prayer_times_filepath=custom_path)
    assert app.prayer_times_filepath == custom_path

def test_load_prayer_times_success(tmp_path):
    """Test successful loading of prayer times from a valid JSON file."""
    filepath = tmp_path / "test_adhan.json"
    dummy_content = {
        "Fajr": "05:00",
        "Dhuhr": "13:00",
        "Asr": "16:00",
        "Maghrib": "18:30",
        "Isha": "20:00"
    }
    create_dummy_prayer_times_file(filepath=filepath, content=dummy_content)
    
    app = AdhanClockApp(prayer_times_filepath=str(filepath))
    assert app.prayer_times == dummy_content
    # Check if default file is NOT loaded if custom exists
    assert app.prayer_times_filepath == str(filepath)

def test_load_prayer_times_file_not_found():
    """Test loading when the prayer times file does not exist."""
    non_existent_file = "non_existent_times.json"
    app = AdhanClockApp(prayer_times_filepath=non_existent_file)
    assert app.prayer_times is None
    assert not os.path.exists(non_existent_file) # Ensure we don't create it

def test_load_prayer_times_invalid_json(tmp_path):
    """Test loading when the prayer times file contains invalid JSON."""
    filepath = tmp_path / "invalid.json"
    with open(filepath, 'w') as f:
        f.write("{ 'Fajr': '05:00', ") # Malformed JSON
    
    app = AdhanClockApp(prayer_times_filepath=str(filepath))
    assert app.prayer_times is None

def test_load_prayer_times_malformed_data(tmp_path):
    """Test loading when the JSON data is missing required keys."""
    filepath = tmp_path / "malformed.json"
    malformed_content = {
        "Fajr": "05:00",
        "Dhuhr": "13:00",
        # Missing Asr, Maghrib, Isha
    }
    create_dummy_prayer_times_file(filepath=filepath, content=malformed_content)
    
    app = AdhanClockApp(prayer_times_filepath=str(filepath))
    assert app.prayer_times is None

def test_get_next_prayer_info_before_fajr():
    """Test when current time is before Fajr."""
    create_dummy_prayer_times_file() # Ensures adhan_times.json exists for the test
    app = AdhanClockApp()
    current_dt = datetime(2023, 10, 27, 4, 0) # 4:00 AM
    name, time_str, dt_obj = app.get_next_prayer_info(current_dt)
    
    assert name == "Fajr"
    assert time_str == "05:00"
    assert dt_obj == datetime(2023, 10, 27, 5, 0)

def test_get_next_prayer_info_after_fajr_before_dhuhr():
    """Test when current time is after Fajr but before Dhuhr."""
    create_dummy_prayer_times_file()
    app = AdhanClockApp()
    current_dt = datetime(2023, 10, 27, 10, 0) # 10:00 AM
    name, time_str, dt_obj = app.get_next_prayer_info(current_dt)
    
    assert name == "Dhuhr"
    assert time_str == "13:00"
    assert dt_obj == datetime(2023, 10, 27, 13, 0)

def test_get_next_prayer_info_after_all_prayers_today():
    """Test when current time is after all prayers for the day, expecting Fajr tomorrow."""
    create_dummy_prayer_times_file()
    app = AdhanClockApp()
    current_dt = datetime(2023, 10, 27, 22, 0) # 10:00 PM
    name, time_str, dt_obj = app.get_next_prayer_info(current_dt)
    
    assert name == "Fajr (Tomorrow)"
    assert time_str == "05:00"
    assert dt_obj == datetime(2023, 10, 28, 5, 0)

def test_get_next_prayer_info_no_prayer_times_loaded():
    """Test behavior when no prayer times are loaded."""
    app = AdhanClockApp(prayer_times_filepath="non_existent_file.json")
    current_dt = datetime.now()
    name, time_str, dt_obj = app.get_next_prayer_info(current_dt)
    
    assert name == "No prayer times loaded"
    assert time_str is None
    assert dt_obj is None

def test_get_next_prayer_info_malformed_time_in_data(tmp_path):
    """Test with malformed time string for a prayer."""
    filepath = tmp_path / "malformed_time.json"
    malformed_content = {
        "Fajr": "05:00",
        "Dhuhr": "invalid-time",
        "Asr": "16:00",
        "Maghrib": "18:30",
        "Isha": "20:00"
    }
    create_dummy_prayer_times_file(filepath=filepath, content=malformed_content)
    
    app = AdhanClockApp(prayer_times_filepath=str(filepath))
    current_dt = datetime(2023, 10, 27, 12, 0) # Before Dhuhr
    name, time_str, dt_obj = app.get_next_prayer_info(current_dt)
    
    # Dhuhr should be skipped, so Asr should be next
    assert name == "Asr"
    assert time_str == "16:00"
    assert dt_obj == datetime(2023, 10, 27, 16, 0)

def test_get_next_prayer_info_malformed_tomorrow_fajr(tmp_path):
    """Test scenario where today's prayers are passed, but tomorrow's Fajr time is malformed."""
    filepath = tmp_path / "malformed_fajr.json"
    malformed_content = {
        "Fajr": "invalid-fajr-time", # Malformed
        "Dhuhr": "13:00",
        "Asr": "16:00",
        "Maghrib": "18:30",
        "Isha": "20:00"
    }
    create_dummy_prayer_times_file(filepath=filepath, content=malformed_content)
    
    app = AdhanClockApp(prayer_times_filepath=str(filepath))
    current_dt = datetime(2023, 10, 27, 22, 0) # After all today's prayers
    name, time_str, dt_obj = app.get_next_prayer_info(current_dt)
    
    # Should fall back to "All prayers done for today" if tomorrow's Fajr is malformed
    assert name == "All prayers done for today"
    assert time_str is None
    assert dt_obj is None

def test_format_time_display_with_time():
    """Test formatting a prayer name and time when time is present."""
    app = AdhanClockApp()
    formatted = app.format_time_display("Fajr", "05:00")
    assert formatted == "Fajr: 05:00"

def test_format_time_display_without_time():
    """Test formatting a prayer name when time is None or empty."""
    app = AdhanClockApp()
    formatted = app.format_time_display("Asr", None)
    assert formatted == "Asr: N/A"
    formatted = app.format_time_display("Maghrib", "")
    assert formatted == "Maghrib: N/A"

def test_run_gui_prints_info(capsys):
    """Test that run_gui prints basic information (mocking current time)."""
    # Create a dummy file so it's not considered "not found"
    create_dummy_prayer_times_file() 
    
    app = AdhanClockApp()
    
    # Mock datetime.now to control the "current" time for predictable output
    original_datetime_now = datetime.now
    mock_current_dt = datetime(2023, 10, 27, 10, 30) # Example time
    datetime.now = lambda: mock_current_dt
    
    app.run_gui()
    
    # Restore original datetime.now
    datetime.now = original_datetime_now
    
    captured = capsys.readouterr()
    assert "Starting Adhan Clock GUI..." in captured.out
    assert f"Current time: {mock_current_dt.strftime('%H:%M:%S')}" in captured.out
    assert "Next Prayer: Dhuhr at 13:00" in captured.out
    assert "GUI application logic would continue here..." in captured.out

# Test with custom filepath for run_gui
def test_run_gui_with_custom_file(capsys, tmp_path):
    """Test that run_gui uses a custom file if provided."""
    custom_filepath = tmp_path / "custom_gui_times.json"
    custom_content = {
        "Fajr": "04:00",
        "Dhuhr": "12:00",
        "Asr": "15:00",
        "Maghrib": "17:00",
        "Isha": "19:00"
    }
    create_dummy_prayer_times_file(filepath=custom_filepath, content=custom_content)
    
    app = AdhanClockApp(prayer_times_filepath=str(custom_filepath))
    
    mock_current_dt = datetime(2023, 10, 27, 10, 0) # Example time
    original_datetime_now = datetime.now
    datetime.now = lambda: mock_current_dt
    
    app.run_gui()
    
    datetime.now = original_datetime_now # Restore
    
    captured = capsys.readouterr()
    assert "Starting Adhan Clock GUI..." in captured.out
    assert f"Current time: {mock_current_dt.strftime('%H:%M:%S')}" in captured.out
    assert "Next Prayer: Dhuhr at 12:00" in captured.out # Should use custom times
    assert "GUI application logic would continue here..." in captured.out

```
