import pytest
import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Assume main.py is in the project root or accessible in sys.path
from main import AdhanClockApp, PRAYER_TIMES_FILE

# Helper to create a dummy adhan_times.json file
def create_dummy_prayer_times(filepath=PRAYER_TIMES_FILE, data=None):
    if data is None:
        data = {
            "Fajr": "03:30",
            "Sunrise": "05:00",
            "Dhuhr": "12:30",
            "Asr": "16:00",
            "Sunset": "19:30",
            "Maghrib": "19:30",
            "Isha": "21:00"
        }
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f)

# Helper to clean up dummy files
def cleanup_dummy_prayer_times(filepath=PRAYER_TIMES_FILE):
    if os.path.exists(filepath):
        os.remove(filepath)
    # Clean up directory if it was created solely for this test file
    dir_name = os.path.dirname(filepath)
    if dir_name and dir_name != "." and not os.listdir(dir_name):
        os.rmdir(dir_name)

# Fixture to manage dummy prayer times file for tests
@pytest.fixture(autouse=True)
def setup_test_environment():
    """Sets up and tears down the test environment."""
    # Ensure no lingering files from previous runs
    cleanup_dummy_prayer_times()
    
    # Create a dummy file for tests that need it
    create_dummy_prayer_times()
    
    yield # Run the test
    
    # Clean up after the test
    cleanup_dummy_prayer_times()

# Test cases for AdhanClockApp
class TestAdhanClockApp:

    def test_init_default_filepath(self):
        """Tests initialization with the default prayer times filepath."""
        app = AdhanClockApp()
        assert app.prayer_times_filepath == PRAYER_TIMES_FILE
        assert app.prayer_times is not None # Should load the created dummy file

    def test_init_custom_filepath(self):
        """Tests initialization with a custom prayer times filepath."""
        custom_file = "custom_times.json"
        create_dummy_prayer_times(custom_file)
        app = AdhanClockApp(prayer_times_filepath=custom_file)
        assert app.prayer_times_filepath == custom_file
        assert app.prayer_times is not None
        cleanup_dummy_prayer_times(custom_file) # Clean up the custom file

    def test_load_prayer_times_file_not_found(self):
        """Tests loading when the prayer times file does not exist."""
        non_existent_file = "non_existent.json"
        app = AdhanClockApp(prayer_times_filepath=non_existent_file)
        assert app.prayer_times is None

    def test_load_prayer_times_malformed_json(self):
        """Tests loading when the prayer times file contains malformed JSON."""
        malformed_file = "malformed.json"
        with open(malformed_file, 'w') as f:
            f.write("This is not JSON")
        
        app = AdhanClockApp(prayer_times_filepath=malformed_file)
        assert app.prayer_times is None
        os.remove(malformed_file)

    def test_load_prayer_times_missing_keys(self):
        """Tests loading when the prayer times file is missing required keys."""
        missing_keys_file = "missing_keys.json"
        data = {"Fajr": "03:30", "Dhuhr": "12:30"} # Missing Asr, Maghrib, Isha, Sunrise, Sunset
        create_dummy_prayer_times(missing_keys_file, data)
        
        app = AdhanClockApp(prayer_times_filepath=missing_keys_file)
        assert app.prayer_times is None
        cleanup_dummy_prayer_times(missing_keys_file)

    def test_load_prayer_times_invalid_time_format(self):
        """Tests loading when a prayer time has an invalid format."""
        invalid_time_file = "invalid_time.json"
        data = {
            "Fajr": "03:30",
            "Sunrise": "invalid-time", # Invalid format
            "Dhuhr": "12:30",
            "Asr": "16:00",
            "Sunset": "19:30",
            "Maghrib": "19:30",
            "Isha": "21:00"
        }
        create_dummy_prayer_times(invalid_time_file, data)
        
        app = AdhanClockApp(prayer_times_filepath=invalid_time_file)
        # The app should load partially, but the invalid time will cause issues later.
        # The _load_prayer_times method itself might not return None but log a warning.
        # We'll test the impact in get_next_prayer_info.
        assert app.prayer_times is not None # It loads if the JSON is valid and has expected keys
        cleanup_dummy_prayer_times(invalid_time_file)

    def test_get_next_prayer_info_basic(self):
        """Tests finding the next prayer when current time is before all prayers."""
        app = AdhanClockApp() # Uses the dummy file created by setup_test_environment
        current_dt = datetime(2023, 10, 27, 6, 0, 0) # After Sunrise, before Dhuhr
        name, time_str, dt_obj = app.get_next_prayer_info(current_dt)
        
        expected_dt = datetime(2023, 10, 27, 12, 30, 0) # Dhuhr time from dummy file
        assert name == "Dhuhr"
        assert time_str == "12:30"
        assert dt_obj == expected_dt

    def test_get_next_prayer_info_after_last_prayer(self):
        """Tests finding the next prayer when current time is after all prayers for today."""
        app = AdhanClockApp()
        current_dt = datetime(2023, 10, 27, 23, 0, 0) # After Isha
        name, time_str, dt_obj = app.get_next_prayer_info(current_dt)
        
        expected_dt = datetime(2023, 10, 28, 3, 30, 0) # Fajr of next day from dummy file
        assert name == "Fajr (Tomorrow)"
        assert time_str == "03:30"
        assert dt_obj == expected_dt

    def test_get_next_prayer_info_exactly_on_prayer_time(self):
        """Tests finding the next prayer when current time is exactly on a prayer time."""
        app = AdhanClockApp()
        current_dt = datetime(2023, 10, 27, 12, 30, 0) # Exactly Dhuhr time
        name, time_str, dt_obj = app.get_next_prayer_info(current_dt)
        
        # The logic is to find the *next* prayer that is *after* current_dt.
        # So if current_dt is 12:30, the next prayer is Asr.
        expected_dt = datetime(2023, 10, 27, 16, 0, 0) # Asr time
        assert name == "Asr"
        assert time_str == "16:00"
        assert dt_obj == expected_dt

    def test_get_next_prayer_info_no_prayer_times_loaded(self):
        """Tests get_next_prayer_info when no prayer times were loaded."""
        app = AdhanClockApp(prayer_times_filepath="non_existent.json")
        current_dt = datetime.now()
        name, time_str, dt_obj = app.get_next_prayer_info(current_dt)
        
        assert name == "No prayer times loaded"
        assert time_str is None
        assert dt_obj is None

    def test_get_next_prayer_info_with_invalid_time_format_in_data(self):
        """Tests get_next_prayer_info when the loaded data has invalid time formats."""
        invalid_time_file = "invalid_time_test.json"
        data = {
            "Fajr": "03:30",
            "Sunrise": "invalid-time", # Invalid format
            "Dhuhr": "12:30",
            "Asr": "16:00",
            "Sunset": "19:30",
            "Maghrib": "19:30",
            "Isha": "21:00"
        }
        create_dummy_prayer_times(invalid_time_file, data)
        app = AdhanClockApp(prayer_times_filepath=invalid_time_file)
        
        current_dt = datetime(2023, 10, 27, 5, 30, 0) # After Sunrise, before Dhuhr
        
        # The warning for invalid time should be printed, but it should proceed without crashing.
        # It should skip the invalid time and find the next valid prayer.
        name, time_str, dt_obj = app.get_next_prayer_info(current_dt)
        
        expected_dt = datetime(2023, 10, 27, 12, 30, 0) # Dhuhr time
        assert name == "Dhuhr"
        assert time_str == "12:30"
        assert dt_obj == expected_dt
        
        cleanup_dummy_prayer_times(invalid_time_file)

    def test_get_next_prayer_info_tomorrow_fajr_invalid_format(self):
        """Tests the case where tomorrow's Fajr time is invalid."""
        # Create a file where today's prayers are valid, but tomorrow's Fajr is invalid.
        invalid_fajr_file = "invalid_fajr_tomorrow.json"
        data = {
            "Fajr": "invalid-fajr-time", # Invalid format for Fajr
            "Sunrise": "05:00",
            "Dhuhr": "12:30",
            "Asr": "16:00",
            "Sunset": "19:30",
            "Maghrib": "19:30",
            "Isha": "21:00"
        }
        create_dummy_prayer_times(invalid_fajr_file, data)
        app = AdhanClockApp(prayer_times_filepath=invalid_fajr_file)
        
        current_dt = datetime(2023, 10, 27, 23, 0, 0) # After Isha
        
        # Should fall back to "All prayers done for today" if tomorrow's Fajr is malformed
        name, time_str, dt_obj = app.get_next_prayer_info(current_dt)
        
        assert name == "All prayers done for today"
        assert time_str is None
        assert dt_obj is None
        
        cleanup_dummy_prayer_times(invalid_fajr_file)

    def test_format_time_display_with_time(self):
        """Tests formatting a prayer name and time string when time is present."""
        app = AdhanClockApp()
        prayer_name = "Fajr"
        time_str = "03:30"
        formatted = app.format_time_display(prayer_name, time_str)
        assert formatted == "Fajr: 03:30"

    def test_format_time_display_without_time(self):
        """Tests formatting a prayer name and time string when time is None."""
        app = AdhanClockApp()
        prayer_name = "Fajr"
        time_str = None
        formatted = app.format_time_display(prayer_name, time_str)
        assert formatted == "Fajr: N/A"

    @patch('builtins.print')
    def test_run_gui_prints_status(self, mock_print):
        """Tests that run_gui prints the current status information."""
        app = AdhanClockApp() # Uses the dummy file
        
        # Capture current time to assert against
        now = datetime.now()
        
        app.run_gui()
        
        # Check if the expected print statements were called
        mock_print.assert_any_call("Starting Adhan Clock GUI...")
        mock_print.assert_any_call(f"Current time: {now.strftime('%H:%M:%S')}")
        # The next prayer info depends on the exact `now` time.
        # We can check for the presence of "Next Prayer:" and a prayer name.
        found_next_prayer_line = False
        for call in mock_print.call_args_list:
            if "Next Prayer:" in call[0][0]:
                found_next_prayer_line = True
                assert "Fajr" in call[0][0] or "Dhuhr" in call[0][0] or "Asr" in call[0][0] or \
                       "Maghrib" in call[0][0] or "Isha" in call[0][0] or "Sunrise" in call[0][0] or \
                       "Sunset" in call[0][0] # Could be any prayer based on current_dt
                break
        assert found_next_prayer_line
        mock_print.assert_any_call("GUI application logic would continue here...")

```