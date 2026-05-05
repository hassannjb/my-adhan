```python
# tests/conftest.py

import pytest
import os
import json
from datetime import datetime, timedelta

# Mock the pray.zone API to avoid making actual network requests during tests
# We'll create a dummy prayer times file that the app can read.

# Define a temporary directory for test files
@pytest.fixture(scope="session")
def tmp_test_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("adhan_test_data")

# Fixture to create a dummy adhan_times.json file
@pytest.fixture
def mock_prayer_times_file(tmp_test_dir):
    filepath = tmp_test_dir / "adhan_times.json"
    dummy_times = {
        "Fajr": "05:00",
        "Sunrise": "06:30",
        "Dhuhr": "13:00",
        "Asr": "16:00",
        "Sunset": "18:30",
        "Maghrib": "18:30",
        "Isha": "20:00",
        "Imsak": "04:55",
        "Midnight": "00:45"
    }
    with open(filepath, 'w') as f:
        json.dump(dummy_times, f, indent=4)
    return filepath

# Fixture to create a malformed adhan_times.json file
@pytest.fixture
def malformed_prayer_times_file(tmp_test_dir):
    filepath = tmp_test_dir / "malformed_adhan_times.json"
    malformed_times = {
        "Fajr": "05:00",
        "Dhuhr": "13:00",
        # Missing Asr, Maghrib, Isha
        "Sunrise": "06:30",
        "Sunset": "18:30"
    }
    with open(filepath, 'w') as f:
        json.dump(malformed_times, f, indent=4)
    return filepath

# Fixture to create a JSONDecodeError file
@pytest.fixture
def invalid_json_file(tmp_test_dir):
    filepath = tmp_test_dir / "invalid.json"
    with open(filepath, 'w') as f:
        f.write("{'Fajr': '05:00'") # Incomplete JSON
    return filepath

# Fixture to create a file with invalid time format for a prayer
@pytest.fixture
def invalid_time_format_file(tmp_test_dir):
    filepath = tmp_test_dir / "invalid_time.json"
    invalid_times = {
        "Fajr": "05:00",
        "Dhuhr": "13:00",
        "Asr": "invalid-time", # Invalid format
        "Maghrib": "18:30",
        "Isha": "20:00"
    }
    with open(filepath, 'w') as f:
        json.dump(invalid_times, f, indent=4)
    return filepath

# Fixture to mock the current time for specific tests
@pytest.fixture
def mock_datetime_now(monkeypatch):
    # We can't directly mock datetime.now() for all cases, as it's often used internally.
    # Instead, we'll provide a way to *set* the current time for specific test scenarios.
    # For tests that need to simulate a specific time, we'll pass it as an argument
    # to the method being tested.
    # If a test needs to mock datetime.now(), it can do so within the test function.
    pass
```
