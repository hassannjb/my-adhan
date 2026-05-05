```python
import pytest
import os
import json
from unittest.mock import patch, MagicMock

# Assume updateAzaanTimers.py is in the root of the project
from updateAzaanTimers import fetch_prayer_times, save_prayer_times, main

# Constants for testing
TEST_CITY = "TestCity"
TEST_COUNTRY = "TestCountry"
TEST_METHOD = "1"
TEST_OUTPUT_FILE = "test_adhan_times.json"
DEFAULT_OUTPUT_FILE = "adhan_times.json"
SAMPLE_API_RESPONSE = {
    "results": {
        "datetime": [
            {
                "date": {"readable": "2023-10-27"},
                "times": {
                    "Fajr": "05:00",
                    "Sunrise": "06:15",
                    "Dhuhr": "13:00",
                    "Asr": "16:30",
                    "Maghrib": "18:45",
                    "Isha": "20:00"
                }
            }
        ]
    }
}
EXPECTED_FETCHED_TIMES = SAMPLE_API_RESPONSE['results']['datetime'][0]['times']

@pytest.fixture
def cleanup_test_file():
    """Fixture to clean up the test output file after each test."""
    if os.path.exists(TEST_OUTPUT_FILE):
        os.remove(TEST_OUTPUT_FILE)
    if os.path.exists(DEFAULT_OUTPUT_FILE): # Clean up default if it was created
        os.remove(DEFAULT_OUTPUT_FILE)
    yield
    if os.path.exists(TEST_OUTPUT_FILE):
        os.remove(TEST_OUTPUT_FILE)
    if os.path.exists(DEFAULT_OUTPUT_FILE):
        os.remove(DEFAULT_OUTPUT_FILE)

@pytest.fixture
def mock_api_request(monkeypatch):
    """Fixture to mock the requests.get call."""
    def mock_get(*args, **kwargs):
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_API_RESPONSE
        mock_response.raise_for_status.return_value = None # No HTTP errors
        return mock_response
    monkeypatch.setattr("requests.get", mock_get)

@pytest.fixture
def mock_api_request_error(monkeypatch):
    """Fixture to mock a requests.get call that raises an exception."""
    def mock_get(*args, **kwargs):
        raise requests.exceptions.RequestException("Mock connection error")
    monkeypatch.setattr("requests.get", mock_get)

@pytest.fixture
def mock_api_response_parse_error(monkeypatch):
    """Fixture to mock a response that cannot be parsed."""
    def mock_get(*args, **kwargs):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": {"datetime": []}} # Missing times
        mock_response.raise_for_status.return_value = None
        return mock_response
    monkeypatch.setattr("requests.get", mock_get)


def test_fetch_prayer_times_success(mock_api_request):
    """Tests successful fetching of prayer times."""
    times = fetch_prayer_times(TEST_CITY, TEST_COUNTRY, TEST_METHOD)
    assert times == EXPECTED_FETCHED_TIMES
    # Check if requests.get was called with correct parameters
    from requests import get
    get.assert_called_once_with(
        "https://api.pray.zone/v2/times/today.json",
        params={"city": TEST_CITY, "country": TEST_COUNTRY, "method": TEST_METHOD},
        timeout=10
    )

def test_fetch_prayer_times_request_error(mock_api_request_error):
    """Tests fetching prayer times when a request error occurs."""
    # Mock sys.stdout to capture print statements if needed, but here we just check return
    with patch('sys.stdout', new_callable=MagicMock) as mock_stdout:
        times = fetch_prayer_times(TEST_CITY, TEST_COUNTRY, TEST_METHOD)
        assert times is None
        mock_stdout.write.assert_any_call(f"Error fetching prayer times for {TEST_CITY}, {TEST_COUNTRY}: Mock connection error\n")

def test_fetch_prayer_times_parse_error(mock_api_response_parse_error):
    """Tests fetching prayer times when API response parsing fails."""
    with patch('sys.stdout', new_callable=MagicMock) as mock_stdout:
        times = fetch_prayer_times(TEST_CITY, TEST_COUNTRY, TEST_METHOD)
        assert times is None
        mock_stdout.write.assert_any_call(f"Error parsing API response: Missing 'results' or 'datetime' key in response for {TEST_CITY}, {TEST_COUNTRY}.\n")

def test_fetch_prayer_times_invalid_json_error(monkeypatch):
    """Tests fetching prayer times when the API returns invalid JSON."""
    def mock_get(*args, **kwargs):
        mock_response = MagicMock()
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "doc", 0)
        mock_response.raise_for_status.return_value = None
        return mock_response
    monkeypatch.setattr("requests.get", mock_get)
    with patch('sys.stdout', new_callable=MagicMock) as mock_stdout:
        times = fetch_prayer_times(TEST_CITY, TEST_COUNTRY, TEST_METHOD)
        assert times is None
        mock_stdout.write.assert_any_call(f"Error parsing API response structure for {TEST_CITY}, {TEST_COUNTRY}: Invalid JSON ('doc', 0)\n")


def test_save_prayer_times_success(cleanup_test_file):
    """Tests successful saving of prayer times to a file."""
    success = save_prayer_times(TEST_OUTPUT_FILE, EXPECTED_FETCHED_TIMES)
    assert success is True
    assert os.path.exists(TEST_OUTPUT_FILE)
    with open(TEST_OUTPUT_FILE, 'r') as f:
        saved_data = json.load(f)
    assert saved_data == EXPECTED_FETCHED_TIMES

def test_save_prayer_times_no_data():
    """Tests saving when no prayer times data is provided."""
    with patch('sys.stdout', new_callable=MagicMock) as mock_stdout:
        success = save_prayer_times(TEST_OUTPUT_FILE, None)
        assert success is False
        mock_stdout.write.assert_any_call("No prayer times data to save.\n")

def test_save_prayer_times_io_error(cleanup_test_file):
    """Tests saving when an IO error occurs."""
    # Create a directory that cannot be written to
    # On Linux/macOS: create a directory and change its permissions to read-only
    # On Windows: create a read-only directory
    
    # This is a bit tricky to reliably simulate across OSes.
    # A simpler approach is to mock os.makedirs and open.
    with patch('os.makedirs', side_effect=IOError("Mock permission denied")), \
         patch('builtins.open', side_effect=IOError("Mock permission denied")):
        with patch('sys.stdout', new_callable=MagicMock) as mock_stdout:
            success = save_prayer_times(TEST_OUTPUT_FILE, EXPECTED_FETCHED_TIMES)
            assert success is False
            mock_stdout.write.assert_any_call(f"Error saving prayer times to file '{TEST_OUTPUT_FILE}': Mock permission denied\n")


def test_main_success(mock_api_request, cleanup_test_file):
    """Tests the main function when API call and saving are successful."""
    with patch('sys.stdout', new_callable=MagicMock) as mock_stdout:
        # Mocking sys.argv to simulate command-line arguments
        with patch('sys.argv', ['updateAzaanTimers.py', '--city', TEST_CITY, '--country', TEST_COUNTRY, '--method', TEST_METHOD, '--output', TEST_OUTPUT_FILE]):
            main()
            mock_stdout.write.assert_any_call(f"Fetching prayer times for {TEST_CITY}, {TEST_COUNTRY} using method {TEST_METHOD}...\n")
            mock_stdout.write.assert_any_call(f"Prayer times saved to {TEST_OUTPUT_FILE}\n")
    
    assert os.path.exists(TEST_OUTPUT_FILE)
    with open(TEST_OUTPUT_FILE, 'r') as f:
        saved_data = json.load(f)
    assert saved_data == EXPECTED_FETCHED_TIMES

def test_main_api_failure(mock_api_request_error, cleanup_test_file):
    """Tests the main function when the API call fails."""
    with patch('sys.stdout', new_callable=MagicMock) as mock_stdout:
        with patch('sys.argv', ['updateAzaanTimers.py', '--city', TEST_CITY, '--country', TEST_COUNTRY, '--method', TEST_METHOD, '--output', TEST_OUTPUT_FILE]):
            main()
            mock_stdout.write.assert_any_call(f"Fetching prayer times for {TEST_CITY}, {TEST_COUNTRY} using method {TEST_METHOD}...\n")
            mock_stdout.write.assert_any_call(f"Failed to retrieve or save prayer times.\n")
    assert not os.path.exists(TEST_OUTPUT_FILE)

def test_main_save_failure(monkeypatch, cleanup_test_file):
    """Tests the main function when saving fails."""
    # Mock fetch_prayer_times to succeed but save_prayer_times to fail
    monkeypatch.setattr("updateAzaanTimers.fetch_prayer_times", MagicMock(return_value=EXPECTED_FETCHED_TIMES))
    monkeypatch.setattr("updateAzaanTimers.save_prayer_times", MagicMock(return_value=False))

    with patch('sys.stdout', new_callable=MagicMock) as mock_stdout:
        with patch('sys.argv', ['updateAzaanTimers.py', '--city', TEST_CITY, '--country', TEST_COUNTRY, '--output', TEST_OUTPUT_FILE]):
            main()
            mock_stdout.write.assert_any_call(f"Fetching prayer times for {TEST_CITY}, {TEST_COUNTRY} using method 2...\n") # Default method
            mock_stdout.write.assert_any_call(f"Failed to retrieve or save prayer times.\n")
    assert not os.path.exists(TEST_OUTPUT_FILE)

def test_main_default_output_file(mock_api_request, cleanup_test_file):
    """Tests the main function uses the default output file if not specified."""
    with patch('sys.argv', ['updateAzaanTimers.py', '--city', TEST_CITY, '--country', TEST_COUNTRY]):
        main()
    
    assert os.path.exists(DEFAULT_OUTPUT_FILE)
    with open(DEFAULT_OUTPUT_FILE, 'r') as f:
        saved_data = json.load(f)
    assert saved_data == EXPECTED_FETCHED_TIMES
```
