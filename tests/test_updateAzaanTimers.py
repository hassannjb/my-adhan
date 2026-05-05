import pytest
import json
import os
from unittest.mock import patch, MagicMock

# Assume updateAzaanTimers.py is in the project root or accessible in sys.path
# If not, adjust the import path accordingly.
from updateAzaanTimers import fetch_prayer_times, save_prayer_times, main

# Define default file paths for tests
MOCK_PRAYER_TIMES_FILE = "mock_adhan_times.json"

@pytest.fixture
def mock_prayer_times_data():
    """Provides a sample prayer times dictionary."""
    return {
        "Fajr": "03:45",
        "Sunrise": "05:05",
        "Dhuhr": "12:30",
        "Asr": "16:00",
        "Sunset": "19:40",
        "Maghrib": "19:40",
        "Isha": "21:00"
    }

@pytest.fixture
def mock_api_response():
    """Provides a sample response structure from the prayer times API."""
    return {
        "status": "OK",
        "results": {
            "datetime": [
                {
                    "date": {"readable": "15 Feb 2024", "timestamp": "1707955200"},
                    "times": {
                        "Fajr": "03:45",
                        "Sunrise": "05:05",
                        "Dhuhr": "12:30",
                        "Asr": "16:00",
                        "Sunset": "19:40",
                        "Maghrib": "19:40",
                        "Isha": "21:00"
                    }
                }
            ]
        }
    }

@pytest.fixture
def mock_invalid_api_response():
    """Provides a sample invalid response structure from the prayer times API."""
    return {
        "status": "OK",
        "results": {} # Missing datetime or times
    }

@pytest.fixture
def mock_api_error_response():
    """Provides a sample response for an API error."""
    return {
        "status": "ERROR",
        "message": "Invalid parameters"
    }

@pytest.fixture(autouse=True)
def cleanup_test_files():
    """Cleans up any created test files after each test."""
    yield
    if os.path.exists(MOCK_PRAYER_TIMES_FILE):
        os.remove(MOCK_PRAYER_TIMES_FILE)
    if os.path.exists("temp_output.json"):
        os.remove("temp_output.json")
    if os.path.exists("temp_dir/temp_output.json"):
        os.remove("temp_dir/temp_output.json")
        os.rmdir("temp_dir")


@patch("updateAzaanTimers.requests.get")
def test_fetch_prayer_times_success(mock_get, mock_api_response):
    """Tests successful fetching of prayer times from the API."""
    mock_response = MagicMock()
    mock_response.json.return_value = mock_api_response
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    city = "London"
    country = "UK"
    method = "2"
    expected_times = mock_api_response['results']['datetime'][0]['times']

    actual_times = fetch_prayer_times(city, country, method)

    assert actual_times == expected_times
    mock_get.assert_called_once_with(
        "https://api.pray.zone/v2/times/today.json",
        params={"city": city, "country": country, "method": method},
        timeout=10
    )

@patch("updateAzaanTimers.requests.get")
def test_fetch_prayer_times_api_error(mock_get):
    """Tests fetching prayer times when the API returns an error status."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": "ERROR", "message": "City not found"}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    city = "InvalidCity"
    country = "InvalidCountry"
    method = "2"

    assert fetch_prayer_times(city, country, method) is None
    mock_get.assert_called_once()

@patch("updateAzaanTimers.requests.get")
def test_fetch_prayer_times_request_exception(mock_get):
    """Tests fetching prayer times when a network request exception occurs."""
    mock_get.side_effect = requests.exceptions.RequestException("Network error")

    city = "London"
    country = "UK"
    method = "2"

    assert fetch_prayer_times(city, country, method) is None
    mock_get.assert_called_once()

@patch("updateAzaanTimers.requests.get")
def test_fetch_prayer_times_invalid_response_structure(mock_get, mock_invalid_api_response):
    """Tests fetching prayer times with a malformed API response."""
    mock_response = MagicMock()
    mock_response.json.return_value = mock_invalid_api_response
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    city = "London"
    country = "UK"
    method = "2"

    assert fetch_prayer_times(city, country, method) is None
    mock_get.assert_called_once()

def test_save_prayer_times_success(mock_prayer_times_data):
    """Tests successful saving of prayer times to a file."""
    filepath = MOCK_PRAYER_TIMES_FILE
    success = save_prayer_times(filepath, mock_prayer_times_data)

    assert success is True
    assert os.path.exists(filepath)
    with open(filepath, 'r') as f:
        saved_data = json.load(f)
    assert saved_data == mock_prayer_times_data

def test_save_prayer_times_no_data():
    """Tests saving with empty prayer times data."""
    filepath = MOCK_PRAYER_TIMES_FILE
    success = save_prayer_times(filepath, None)
    assert success is False
    assert not os.path.exists(filepath)

def test_save_prayer_times_io_error(mock_prayer_times_data):
    """Tests saving prayer times when an IO error occurs."""
    # To simulate an IOError, we can try to write to a protected directory or use a mock
    # For simplicity, we'll mock the open function to raise an IOError
    with patch("builtins.open", side_effect=IOError("Permission denied")):
        filepath = MOCK_PRAYER_TIMES_FILE
        success = save_prayer_times(filepath, mock_prayer_times_data)
        assert success is False
        assert not os.path.exists(filepath)

def test_save_prayer_times_creates_directory(mock_prayer_times_data):
    """Tests if save_prayer_times creates parent directories if they don't exist."""
    filepath = os.path.join("temp_dir", MOCK_PRAYER_TIMES_FILE)
    assert not os.path.exists("temp_dir")
    success = save_prayer_times(filepath, mock_prayer_times_data)
    assert success is True
    assert os.path.exists(filepath)
    assert os.path.exists("temp_dir")

@patch("updateAzaanTimers.fetch_prayer_times")
@patch("updateAzaanTimers.save_prayer_times")
def test_main_success(mock_save_prayer_times, mock_fetch_prayer_times, mock_prayer_times_data):
    """Tests the main CLI function when fetching and saving are successful."""
    mock_fetch_prayer_times.return_value = mock_prayer_times_data
    mock_save_prayer_times.return_value = True

    # Mock argparse to simulate command-line arguments
    with patch('argparse.ArgumentParser.parse_args', return_value=argparse.Namespace(
        city="London", country="UK", method="2", output=MOCK_PRAYER_TIMES_FILE
    )):
        main()

    mock_fetch_prayer_times.assert_called_once_with("London", "UK", "2")
    mock_save_prayer_times.assert_called_once_with(MOCK_PRAYER_TIMES_FILE, mock_prayer_times_data)

@patch("updateAzaanTimers.fetch_prayer_times")
@patch("updateAzaanTimers.save_prayer_times")
def test_main_fetch_failure(mock_save_prayer_times, mock_fetch_prayer_times):
    """Tests the main CLI function when fetching prayer times fails."""
    mock_fetch_prayer_times.return_value = None
    
    with patch('argparse.ArgumentParser.parse_args', return_value=argparse.Namespace(
        city="London", country="UK", method="2", output=MOCK_PRAYER_TIMES_FILE
    )):
        main()

    mock_fetch_prayer_times.assert_called_once_with("London", "UK", "2")
    mock_save_prayer_times.assert_not_called()

@patch("updateAzaanTimers.fetch_prayer_times")
@patch("updateAzaanTimers.save_prayer_times")
def test_main_save_failure(mock_save_prayer_times, mock_fetch_prayer_times, mock_prayer_times_data):
    """Tests the main CLI function when saving prayer times fails."""
    mock_fetch_prayer_times.return_value = mock_prayer_times_data
    mock_save_prayer_times.return_value = False

    with patch('argparse.ArgumentParser.parse_args', return_value=argparse.Namespace(
        city="London", country="UK", method="2", output=MOCK_PRAYER_TIMES_FILE
    )):
        main()

    mock_fetch_prayer_times.assert_called_once_with("London", "UK", "2")
    mock_save_prayer_times.assert_called_once_with(MOCK_PRAYER_TIMES_FILE, mock_prayer_times_data)

@patch("updateAzaanTimers.fetch_prayer_times")
@patch("updateAzaanTimers.save_prayer_times")
def test_main_uses_custom_output_path(mock_save_prayer_times, mock_fetch_prayer_times, mock_prayer_times_data):
    """Tests if main correctly uses the --output argument."""
    mock_fetch_prayer_times.return_value = mock_prayer_times_data
    mock_save_prayer_times.return_value = True
    
    custom_output = "temp_output.json"
    with patch('argparse.ArgumentParser.parse_args', return_value=argparse.Namespace(
        city="Kuala Lumpur", country="Malaysia", method="1", output=custom_output
    )):
        main()

    mock_fetch_prayer_times.assert_called_once_with("Kuala Lumpur", "Malaysia", "1")
    mock_save_prayer_times.assert_called_once_with(custom_output, mock_prayer_times_data)

```