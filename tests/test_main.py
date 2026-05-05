```python
import pytest
from datetime import datetime, timedelta
from main import AdhanClockApp, PRAYER_TIMES_FILE
import os
import json

# Helper to create a mock prayer times file
@pytest.fixture
def setup_prayer_times_file(tmp_path, create_prayer_times_file):
    """
    Sets up a temporary prayer times file with specific data for tests.
    """
    def _setup(data, filename=PRAYER_TIMES_FILE):
        filepath = create_prayer_times_file(data, filename)
        return filepath
    return _setup

# --- Test cases for AdhanClockApp ---

def test_init_with_default_filepath(tmp_path, setup_prayer_times_file):
    """
    Test initialization with the default file path.
    """
    prayer_data = {
        "Fajr": "05:00", "Sunrise": "06:30", "Dhuhr": "12:00",
        "Asr": "15:30", "Sunset": "18:00", "Maghrib": "18:00", "Isha": "19:30"
    }
    setup_prayer_times_file(prayer_data)
    app = AdhanClockApp()
    assert app.prayer_times_filepath == PRAYER_TIMES_FILE
    assert app.prayer_times is not None
    assert app.prayer_times["Fajr"] == "05:00"

def test_init_with_custom_filepath(tmp_path, create_prayer_times_file):
    """
    Test initialization with a custom file path.
    """
    custom_path = tmp_path / "custom_adhan.json"
    prayer_data = {
        "Fajr": "04:00", "Dhuhr": "11:00", "Asr": "14:00",
        "Maghrib": "17:00", "Isha": "18:00"
    }
    create_prayer_times_file(prayer_data, filename="custom_adhan.json")
    app = AdhanClockApp(prayer_times_filepath=str(custom_path))
    assert app.prayer_times_filepath == str(custom_path)
    assert app.prayer_times is not None
    assert app.prayer_times["Fajr"] == "04:00"

def test_load_prayer_times_file_not_found(tmp_path):
    """
    Test loading when the prayer times file does not exist.
    """
    app = AdhanClockApp(prayer_times_filepath=str(tmp_path / "non_existent_file.json"))
    # Expecting print statement to indicate warning, but main function doesn't capture stdout easily
    # We check that prayer_times is None
    assert app.prayer_times is None

def test_load_prayer_times_invalid_json(tmp_path, create_prayer_times_file):
    """
    Test loading when the prayer times file contains invalid JSON.
    """
    filepath = create_prayer_times_file("invalid json data", filename="invalid.json")
    app = AdhanClockApp(prayer_times_filepath=str(filepath))
    assert app.prayer_times is None

def test_load_prayer_times_malformed_data(tmp_path, create_prayer_times_file):
    """
    Test loading when the prayer times file has missing keys.
    """
    malformed_data = {"Fajr": "05:00", "Dhuhr": "12:00"} # Missing Asr, Maghrib, Isha
    filepath = create_prayer_times_file(malformed_data, filename="malformed.json")
    app = AdhanClockApp(prayer_times_filepath=str(filepath))
    assert app.prayer_times is None

def test_load_prayer_times_io_error(tmp_path, monkeypatch):
    """
    Test loading when there's an IOError during file reading.
    """
    filepath = tmp_path / "readable_but_error.json"
    with open(filepath, "w") as f:
        f.write("{}") # Create a valid file first

    def mock_open(*args, **kwargs):
        if str(filepath) in args[0]:
            raise IOError("Simulated IO Error")
        return open(*args, **kwargs)

    monkeypatch.setattr(os.path, 'exists', lambda p: True) # Ensure exists returns true
    monkeypatch.setattr("builtins.open", mock_open)

    app = AdhanClockApp(prayer_times_filepath=str(filepath))
    assert app.prayer_times is None

def test_get_next_prayer_info_no_data(tmp_path):
    """
    Test get_next_prayer_info when no prayer times are loaded.
    """
    app = AdhanClockApp(prayer_times_filepath=str(tmp_path / "non_existent.json"))
    current_dt = datetime.now()
    name, time_str, dt_obj = app.get_next_prayer_info(current_dt)
    assert name == "No prayer times loaded"
    assert time_str is None
    assert dt_obj is None

@pytest.mark.parametrize("current_time_str, expected_next_prayer_name, expected_next_prayer_time, expected_next_prayer_dt_str", [
    ("2023-10-27 04:55:00", "Fajr", "05:00", "2023-10-27 05:00:00"), # Before Fajr
    ("2023-10-27 05:10:00", "Sunrise", "06:30", "2023-10-27 06:30:00"), # After Fajr, before Sunrise
    ("2023-10-27 06:40:00", "Dhuhr", "12:00", "2023-10-27 12:00:00"), # After Sunrise, before Dhuhr
    ("2023-10-27 11:59:00", "Dhuhr", "12:00", "2023-10-27 12:00:00"), # Just before Dhuhr
    ("2023-10-27 12:05:00", "Asr", "15:30", "2023-10-27 15:30:00"), # After Dhuhr, before Asr
    ("2023-10-27 15:29:00", "Asr", "15:30", "2023-10-27 15:30:00"), # Just before Asr
    ("2023-10-27 15:45:00", "Sunset", "18:00", "2023-10-27 18:00:00"), # After Asr, before Sunset
    ("2023-10-27 17:59:00", "Sunset", "18:00", "2023-10-27 18:00:00"), # Just before Sunset
    ("2023-10-27 18:10:00", "Isha", "19:30", "2023-10-27 19:30:00"), # After Sunset/Maghrib, before Isha
    ("2023-10-27 19:29:00", "Isha", "19:30", "2023-10-27 19:30:00"), # Just before Isha
    ("2023-10-27 23:59:00", "Fajr (Tomorrow)", "05:00", "2023-10-28 05:00:00"), # After last prayer of the day
])
def test_get_next_prayer_info_today_and_tomorrow(tmp_path, setup_prayer_times_file, current_time_str, expected_next_prayer_name, expected_next_prayer_time, expected_next_prayer_dt_str):
    """
    Test get_next_prayer_info for various times within a day, including rolling over to tomorrow's Fajr.
    """
    prayer_data = {
        "Fajr": "05:00", "Sunrise": "06:30", "Dhuhr": "12:00",
        "Asr": "15:30", "Sunset": "18:00", "Maghrib": "18:00", "Isha": "19:30"
    }
    setup_prayer_times_file(prayer_data)
    app = AdhanClockApp()
    
    # Use a fixed date for deterministic testing
    base_dt_str = "2023-10-27 "
    current_dt = datetime.strptime(base_dt_str + current_time_str.split(" ")[1], "%Y-%m-%d %H:%M:%S")
    expected_dt = datetime.strptime(expected_next_prayer_dt_str, "%Y-%m-%d %H:%M:%S")
    
    name, time_str, dt_obj = app.get_next_prayer_info(current_dt)
    
    assert name == expected_next_prayer_name
    assert time_str == expected_next_prayer_time
    assert dt_obj == expected_dt

def test_get_next_prayer_info_all_prayers_passed_no_fajr_tomorrow(tmp_path, setup_prayer_times_file):
    """
    Test case where all prayers for the day have passed and Fajr for tomorrow is malformed.
    """
    prayer_data = {
        "Fajr": "05:00", "Dhuhr": "12:00", "Asr": "15:00",
        "Maghrib": "17:00", "Isha": "18:00", "Sunrise": "06:00", "Sunset": "17:30",
        "Fajr": "invalid-time" # Malformed Fajr for tomorrow
    }
    setup_prayer_times_file(prayer_data)
    app = AdhanClockApp()
    current_dt = datetime(2023, 10, 27, 23, 0, 0) # End of the day
    
    name, time_str, dt_obj = app.get_next_prayer_info(current_dt)
    
    # Since tomorrow's Fajr is malformed, it should fall back to "All prayers done for today"
    # Note: The code currently prints a warning for invalid Fajr, but then the logic
    # `if next_prayer_name is None and "Fajr" in self.prayer_times:` might still try to process.
    # Re-evaluation of the code shows that if the `strptime` for next day's Fajr fails, it `pass`es
    # and then the final `if next_prayer_name and next_prayer_dt:` check will fail, leading to the fallback.
    assert name == "All prayers done for today"
    assert time_str is None
    assert dt_obj is None

def test_get_next_prayer_info_invalid_time_format_in_data(tmp_path, setup_prayer_times_file):
    """
    Test get_next_prayer_info when some prayer times in the data are invalid.
    """
    prayer_data = {
        "Fajr": "05:00", "Sunrise": "06:30", "Dhuhr": "invalid-time", # Invalid Dhuhr
        "Asr": "15:30", "Sunset": "18:00", "Maghrib": "18:00", "Isha": "19:30"
    }
    setup_prayer_times_file(prayer_data)
    app = AdhanClockApp()
    current_dt = datetime(2023, 10, 27, 11, 0, 0) # Time before Dhuhr

    # Dhuhr is skipped due to invalid format. Next should be Asr.
    name, time_str, dt_obj = app.get_next_prayer_info(current_dt)
    
    assert name == "Asr"
    assert time_str == "15:30"
    expected_dt = datetime(2023, 10, 27, 15, 30, 0)
    assert dt_obj == expected_dt

def test_format_time_display_with_time():
    """
    Test format_time_display when time string is provided.
    """
    app = AdhanClockApp()
    formatted_string = app.format_time_display("Fajr", "05:00")
    assert formatted_string == "Fajr: 05:00"

def test_format_time_display_without_time():
    """
    Test format_time_display when time string is None or empty.
    """
    app = AdhanClockApp()
    formatted_string_none = app.format_time_display("Fajr", None)
    assert formatted_string_none == "Fajr: N/A"
    formatted_string_empty = app.format_time_display("Fajr", "")
    assert formatted_string_empty == "Fajr: N/A" # Assuming empty string should also be N/A

def test_run_gui_prints_basic_info(monkeypatch):
    """
    Test that run_gui prints basic information.
    This test mocks datetime.now to ensure deterministic output.
    """
    class MockDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2023, 10, 27, 14, 30, 0) # Mocked current time

    monkeypatch.setattr(datetime, "now", MockDateTime.now)
    
    # Mock the prayer times file creation for this test
    prayer_data = {
        "Fajr": "05:00", "Sunrise": "06:30", "Dhuhr": "12:00",
        "Asr": "15:30", "Sunset": "18:00", "Maghrib": "18:00", "Isha": "19:30"
    }
    
    # Temporarily create the file for the app to load
    with open(PRAYER_TIMES_FILE, "w") as f:
        json.dump(prayer_data, f, indent=4)

    app = AdhanClockApp()

    # Capture stdout
    captured_output = []
    def mock_print(*args, **kwargs):
        captured_output.append(" ".join(map(str, args)))

    monkeypatch.setattr("builtins.print", mock_print)
    
    app.run_gui()

    # Clean up the created file
    if os.path.exists(PRAYER_TIMES_FILE):
        os.remove(PRAYER_TIMES_FILE)

    assert "Starting Adhan Clock GUI..." in captured_output[0]
    assert "Current time: 14:30:00" in captured_output[1]
    assert "Next Prayer: Asr at 15:30" in captured_output[2]
    assert "GUI application logic would continue here..." in captured_output[3]

```
