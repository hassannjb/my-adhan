```python
import pytest
import os
import sys
from unittest.mock import patch, MagicMock

# Assume updateAzaanTimers.py is in the root of the project, adjust path if needed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from updateAzaanTimers import fetch_prayer_times, save_prayer_times, main

# Mock requests.get to avoid making actual network calls
@pytest.fixture
def mock_requests_get(monkeypatch):
    def mock_get(*args, **kwargs):
        # Simulate a successful response for pray.zone API
        url = args[0]
        params = kwargs.get("params")

        if url == "https://api.pray.zone/v2/times/today.json":
            if params.get("city") == "London" and params.get("country") == "UK":
                return MagicMock(
                    json=lambda: {
                        "results": {
                            "datetime": [
                                {
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
                    },
                    raise_for_status=lambda: None # Simulate successful status
                )
            elif params.get("city") == "FailCity" and params.get("country") == "FailCountry":
                return MagicMock(
                    json=lambda: {"error": "City not found"},
                    raise_for_status=lambda: MagicMock(side_effect=requests.exceptions.HTTPError("404 Client Error: Not Found for url: ..."))
                )
            else:
                 # Default successful response for other calls
                 return MagicMock(
                    json=lambda: {
                        "results": {
                            "datetime": [
                                {
                                    "times": {
                                        "Fajr": "04:30",
                                        "Sunrise": "05:45",
                                        "Dhuhr": "12:30",
                                        "Asr": "16:00",
                                        "Maghrib": "18:15",
                                        "Isha": "19:30"
                                    }
                                }
                            ]
                        }
                    },
                    raise_for_status=lambda: None
                )
        # If the URL or params don't match, raise an error
        raise NotImplementedError(f"Mock not implemented for URL: {url} with params: {params}")

    monkeypatch.setattr("requests.get", mock_get)
    return mock_get

def test_fetch_prayer_times_success(mock_requests_get):
    """Test fetching prayer times successfully."""
    city = "London"
    country = "UK"
    times = fetch_prayer_times(city, country)
    assert times is not None
    assert times["Fajr"] == "05:00"
    assert times["Isha"] == "20:00"

def test_fetch_prayer_times_api_error(mock_requests_get):
    """Test fetching prayer times when the API returns an error."""
    city = "FailCity"
    country = "FailCountry"
    with patch('builtins.print') as mock_print:
        times = fetch_prayer_times(city, country)
    
    assert times is None
    mock_print.assert_any_call(f"Error fetching prayer times for {city}, {country}: HTTP Error: 404 Client Error: Not Found for url: ...")

def test_fetch_prayer_times_request_exception(monkeypatch):
    """Test fetching prayer times when a request exception occurs."""
    def mock_get_exception(*args, **kwargs):
        raise requests.exceptions.RequestException("Network error")

    monkeypatch.setattr("requests.get", mock_get_exception)
    
    with patch('builtins.print') as mock_print:
        times = fetch_prayer_times("City", "Country")
    
    assert times is None
    mock_print.assert_any_call("Error fetching prayer times for City, Country: Network error")

def test_fetch_prayer_times_parse_error_missing_keys(mock_requests_get, monkeypatch):
    """Test fetching prayer times when the API response is missing expected keys."""
    def mock_get_bad_structure(*args, **kwargs):
        return MagicMock(
            json=lambda: {"results": {"datetime": []}}, # Empty datetime list
            raise_for_status=lambda: None
        )
    monkeypatch.setattr("requests.get", mock_get_bad_structure)

    with patch('builtins.print') as mock_print:
        times = fetch_prayer_times("City", "Country")
    
    assert times is None
    mock_print.assert_any_call("Error parsing API response: Missing 'results' or 'datetime' key in response for City, Country.")

def test_save_prayer_times_success(tmp_test_dir):
    """Test saving prayer times to a JSON file."""
    filepath = os.path.join(tmp_test_dir, "test_prayer_times.json")
    prayer_times = {
        "Fajr": "05:00",
        "Dhuhr": "13:00"
    }
    result = save_prayer_times(filepath, prayer_times)
    assert result is True
    assert os.path.exists(filepath)
    with open(filepath, 'r') as f:
        saved_data = json.load(f)
    assert saved_data == prayer_times

def test_save_prayer_times_empty_data(tmp_test_dir):
    """Test saving when prayer_times dictionary is empty or None."""
    filepath = os.path.join(tmp_test_dir, "empty_save.json")
    with patch('builtins.print') as mock_print:
        result_none = save_prayer_times(filepath, None)
        result_empty = save_prayer_times(filepath, {})
    
    assert result_none is False
    assert result_empty is False
    mock_print.assert_any_call("No prayer times data to save.")
    assert not os.path.exists(filepath) # File should not be created if no data

def test_save_prayer_times_io_error(tmp_test_dir):
    """Test saving prayer times when an IOError occurs."""
    # Create a directory and make it read-only to simulate an IO error on file writing.
    # This is OS-dependent, so we'll patch 'open' to simulate the error.
    filepath = os.path.join(tmp_test_dir, "nonexistent_dir", "output.json")
    
    with patch('builtins.open', side_effect=IOError("Simulated IO Error for write")):
        with patch('os.makedirs', return_value=None): # Prevent makedirs from failing if it's called
            prayer_times = {"Fajr": "05:00"}
            with patch('builtins.print') as mock_print:
                result = save_prayer_times(filepath, prayer_times)
            
            assert result is False
            mock_print.assert_any_call(f"Error saving prayer times to file '{filepath}': Simulated IO Error for write")

def test_main_cli_success(tmp_test_dir, mock_requests_get):
    """Test the main CLI function when everything succeeds."""
    output_filepath = os.path.join(tmp_test_dir, "updated_adhan_times.json")
    
    # Mock sys.argv to simulate command-line arguments
    with patch('sys.argv', ['updateAzaanTimers.py', '--city', 'London', '--country', 'UK', '--output', output_filepath]):
        with patch('builtins.print') as mock_print:
            main()
    
    assert os.path.exists(output_filepath)
    with open(output_filepath, 'r') as f:
        saved_data = json.load(f)
    assert saved_data["Fajr"] == "05:00"
    assert "Fetching prayer times for London, UK using method 2..." in mock_print.call_args_list[0][0][0]
    assert f"Prayer times saved to {output_filepath}" in mock_print.call_args_list[2][0][0]

def test_main_cli_fetch_failure(tmp_test_dir, mock_requests_get):
    """Test the main CLI function when fetching prayer times fails."""
    output_filepath = os.path.join(tmp_test_dir, "failed_update.json")
    
    # Make fetch_prayer_times return None by mocking its return value directly
    with patch('updateAzaanTimers.fetch_prayer_times', return_value=None):
        with patch('sys.argv', ['updateAzaanTimers.py', '--city', 'FailCity', '--country', 'FailCountry', '--output', output_filepath]):
            with patch('builtins.print') as mock_print:
                main()
    
    assert not os.path.exists(output_filepath)
    mock_print.assert_any_call("Failed to retrieve or save prayer times.")

def test_main_cli_save_failure(tmp_test_dir, mock_requests_get):
    """Test the main CLI function when saving prayer times fails."""
    output_filepath = os.path.join(tmp_test_dir, "failed_save.json")
    
    # Mock save_prayer_times to return False
    with patch('updateAzaanTimers.save_prayer_times', return_value=False) as mock_save:
        with patch('sys.argv', ['updateAzaanTimers.py', '--city', 'London', '--country', 'UK', '--output', output_filepath]):
            with patch('builtins.print') as mock_print:
                main()
    
    mock_save.assert_called_once() # Ensure save_prayer_times was called
    mock_print.assert_any_call("Failed to retrieve or save prayer times.")

```