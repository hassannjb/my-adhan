```python
import pytest
import requests
import json
from datetime import datetime
import os

# Assuming updateAzaanTimers.py is in the root directory
from updateAzaanTimers import fetch_prayer_times, save_prayer_times, main

# --- Mocking API requests ---
MOCK_API_URL = "https://api.pray.zone/v2/times/today.json"

# Dummy response from the API
DUMMY_API_RESPONSE = {
    "results": {
        "settings": {
            "location": {
                "city": "London",
                "country": "UK"
            },
            "method": 2
        },
        "datetime": [
            {
                "date": {
                    "readable": "27 Oct 2023",
                    "timestamp": "1698374400"
                },
                "times": {
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
            }
        ]
    }
}

# Expected parsed prayer times dictionary
EXPECTED_PARSED_TIMES = {
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

# --- Tests for fetch_prayer_times ---

def test_fetch_prayer_times_success(requests_mock, tmp_test_dir):
    """Test successfully fetching prayer times from the API."""
    requests_mock.get(MOCK_API_URL, json=DUMMY_API_RESPONSE)
    city = "London"
    country = "UK"
    method = "2"

    prayer_times = fetch_prayer_times(city, country, method)

    assert prayer_times == EXPECTED_PARSED_TIMES
    assert requests_mock.called_once
    assert requests_mock.last_request.url == MOCK_API_URL
    assert requests_mock.last_request.qs == {
        'city': [city],
        'country': [country],
        'method': [method]
    }

def test_fetch_prayer_times_api_error(requests_mock):
    """Test fetching prayer times when the API returns an error."""
    requests_mock.get(MOCK_API_URL, status_code=500)
    city = "London"
    country = "UK"
    method = "2"

    prayer_times = fetch_prayer_times(city, country, method)

    assert prayer_times is None
    assert requests_mock.called_once

def test_fetch_prayer_times_network_error(requests_mock):
    """Test fetching prayer times when a network error occurs."""
    requests_mock.get(MOCK_API_URL, exc=requests.exceptions.ConnectionError)
    city = "London"
    country = "UK"
    method = "2"

    prayer_times = fetch_prayer_times(city, country, method)

    assert prayer_times is None
    assert requests_mock.called_once

def test_fetch_prayer_times_invalid_response_structure(requests_mock):
    """Test fetching prayer times with an unexpected response structure."""
    invalid_response = {"message": "Something went wrong"}
    requests_mock.get(MOCK_API_URL, json=invalid_response)
    city = "London"
    country = "UK"
    method = "2"

    prayer_times = fetch_prayer_times(city, country, method)

    assert prayer_times is None
    assert requests_mock.called_once

def test_fetch_prayer_times_empty_datetime(requests_mock):
    """Test fetching prayer times when datetime list is empty."""
    empty_datetime_response = {
        "results": {
            "settings": {},
            "datetime": [] # Empty list
        }
    }
    requests_mock.get(MOCK_API_URL, json=empty_datetime_response)
    city = "London"
    country = "UK"
    method = "2"

    prayer_times = fetch_prayer_times(city, country, method)

    assert prayer_times is None
    assert requests_mock.called_once

# --- Tests for save_prayer_times ---

def test_save_prayer_times_success(tmp_test_dir):
    """Test successfully saving prayer times to a file."""
    filepath = tmp_test_dir / "test_save.json"
    success = save_prayer_times(filepath, EXPECTED_PARSED_TIMES)

    assert success is True
    assert os.path.exists(filepath)
    with open(filepath, 'r') as f:
        saved_data = json.load(f)
    assert saved_data == EXPECTED_PARSED_TIMES

def test_save_prayer_times_empty_data():
    """Test saving when prayer_times dictionary is empty or None."""
    # save_prayer_times should return False and print a message
    # We can't easily capture stdout here for the print message, but check return value
    # and file creation.
    # For this specific function, it checks `if not prayer_times:` which handles None and {}
    assert save_prayer_times("dummy.json", None) is False
    assert save_prayer_times("dummy.json", {}) is False

def test_save_prayer_times_io_error(tmp_test_dir):
    """Test saving prayer times when an IO error occurs."""
    # Create a directory that we cannot write to (e.g., root directory if permissions deny)
    # This is hard to reliably mock. For now, let's assume a path that might cause error if directory doesn't exist.
    # A simpler way is to try writing to a read-only location, but that depends on OS.
    # For robustness, we'll test creating a file in a valid location.
    # If the `os.makedirs` fails, it will raise an exception.
    # The current implementation handles IOError from open()
    
    # Mock os.makedirs to fail for a specific path if needed, but it's complex.
    # Instead, let's rely on the fact that open() can raise IOError.
    # We'll test the case where the directory itself is problematic.
    
    # For example, trying to save to a path like '/root/test.json' without root privileges.
    # This test might fail on systems where the user has write access to root.
    # A better approach might be to mock `open` and `os.makedirs` if a direct IO error is needed.
    
    # For simplicity, let's assume the path is valid but the `open` call might fail for other reasons
    # like disk full, etc. The test can't easily simulate that.
    # We'll check that it returns False and doesn't crash.
    
    # This test is more about ensuring the `except IOError` block is hit.
    # We can't easily force an IOError from `open` or `os.makedirs` in a portable way.
    # Let's assume the `try` block *would* raise an `IOError` if it happened.
    # The function handles it by returning False.
    filepath = "/nonexistent_directory_for_test/adhan_times.json" # This path should cause an error for os.makedirs
    success = save_prayer_times(filepath, EXPECTED_PARSED_TIMES)
    assert success is False
    # Check if directory creation failed, which implies `os.makedirs` failed.
    # `os.path.dirname(filepath)` would be `/nonexistent_directory_for_test`.
    # If it exists and is not a dir, or if permissions prevent creation.

# --- Tests for main CLI function ---

def test_main_success(requests_mock, tmp_test_dir, monkeypatch, capsys):
    """Test the main function when all operations succeed."""
    requests_mock.get(MOCK_API_URL, json=DUMMY_API_RESPONSE)
    output_filepath = tmp_test_dir / "test_output.json"
    
    # Mock sys.argv to simulate command-line arguments
    test_args = [
        "updateAzaanTimers.py",
        "--city", "London",
        "--country", "UK",
        "--output", str(output_filepath)
    ]
    monkeypatch.setattr("sys.argv", test_args)
    
    main()
    
    captured = capsys.readouterr()
    assert f"Fetching prayer times for London, UK using method 2..." in captured.out
    assert f"Prayer times saved to {output_filepath}" in captured.out
    
    assert os.path.exists(output_filepath)
    with open(output_filepath, 'r') as f:
        saved_data = json.load(f)
    assert saved_data == EXPECTED_PARSED_TIMES

def test_main_fetch_error(requests_mock, monkeypatch, capsys):
    """Test the main function when fetching prayer times fails."""
    requests_mock.get(MOCK_API_URL, exc=requests.exceptions.RequestException("Simulated error"))
    
    test_args = [
        "updateAzaanTimers.py",
        "--city", "London",
        "--country", "UK"
    ]
    monkeypatch.setattr("sys.argv", test_args)
    
    main()
    
    captured = capsys.readouterr()
    assert "Fetching prayer times for London, UK using method 2..." in captured.out
    assert "Error fetching prayer times for London, UK: Simulated error" in captured.out
    assert "Failed to retrieve or save prayer times." in captured.out

def test_main_save_error(requests_mock, monkeypatch, capsys):
    """Test the main function when saving prayer times fails."""
    requests_mock.get(MOCK_API_URL, json=DUMMY_API_RESPONSE)
    
    # Attempt to save to a directory where we don't have write permissions
    # This is OS dependent, so we'll simulate by providing a path that `save_prayer_times` might fail on.
    # For demonstration, we'll make it return False.
    # A more robust test would mock os.makedirs and open to raise IOError.
    
    # We'll mock `save_prayer_times` to always return False for this test case
    # to isolate the failure path for saving.
    
    # Mocking the `save_prayer_times` function itself to simulate failure
    # and ensure the correct messages are printed.
    original_save_prayer_times = updateAzaanTimers.save_prayer_times
    def mock_save_failure(filepath, prayer_times):
        print(f"Error saving prayer times to file '{filepath}': Simulated IO Error")
        return False
    
    monkeypatch.setattr("updateAzaanTimers.save_prayer_times", mock_save_failure)

    test_args = [
        "updateAzaanTimers.py",
        "--city", "London",
        "--country", "UK"
    ]
    monkeypatch.setattr("sys.argv", test_args)
    
    main()
    
    captured = capsys.readouterr()
    assert "Fetching prayer times for London, UK using method 2..." in captured.out
    assert "Error saving prayer times to file 'adhan_times.json': Simulated IO Error" in captured.out
    assert "Failed to retrieve or save prayer times." in captured.out

    # Restore the original function after the test
    monkeypatch.undo()

```