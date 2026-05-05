import pytest
import json
import os
from unittest.mock import patch, mock_open, MagicMock
import sys
import requests # Import requests to catch its exceptions

# Adjust sys.path to allow importing updateAzaanTimers from the parent directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from updateAzaanTimers import fetch_prayer_times, save_prayer_times, main, PRAYER_TIMES_API_URL

# --- Fixtures ---

@pytest.fixture
def temp_output_file(tmp_path):
    """Provides a temporary path for the output JSON file."""
    filepath = tmp_path / "test_adhan_times_output.json"
    yield filepath

@pytest.fixture
def mock_api_response_data():
    """Provides a sample dictionary of prayer times as returned by the API."""
    return {
        "Fajr": "05:00",
        "Sunrise": "06:30",
        "Dhuhr": "13:00",
        "Asr": "17:00",
        "Sunset": "19:30",
        "Maghrib": "19:45",
        "Isha": "21:00"
    }

@pytest.fixture
def mock_successful_api_json_response(mock_api_response_data):
    """Mocks a successful API response with nested prayer times data structure."""
    return {
        "code": 200,
        "status": "OK",
        "results": {
            "datetime": [
                {
                    "times": mock_api_response_data,
                    "date": {
                        "timestamp": "1678886400"
                    }
                }
            ],
            "location": {
                "latitude": 51.5,
                "longitude": -0.12
            }
        }
    }

# --- fetch_prayer_times tests ---

@patch('requests.get')
def test_fetch_prayer_times_success(mock_get, mock_successful_api_json_response, mock_api_response_data):
    """Tests successful fetching of prayer times from the API."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_successful_api_json_response
    mock_response.raise_for_status.return_value = None # No HTTP errors
    mock_get.return_value = mock_response

    times = fetch_prayer_times("London", "UK", "2")
    
    mock_get.assert_called_once_with(
        PRAYER_TIMES_API_URL,
        params={"city": "London", "country": "UK", "method": "2"},
        timeout=10
    )
    assert times == mock_api_response_data

@patch('requests.get')
def test_fetch_prayer_times_network_error(mock_get, capsys):
    """Tests handling of network-related RequestException."""
    mock_get.side_effect = requests.exceptions.ConnectionError("Network is down")

    times = fetch_prayer_times("London", "UK")
    assert times is None
    captured = capsys.readouterr()
    assert "Error fetching prayer times for London, UK: Network is down" in captured.err

@patch('requests.get')
def test_fetch_prayer_times_http_error(mock_get, capsys):
    """Tests handling of an HTTP error response (e.g., 404, 500)."""
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Client Error: Not Found for url: ...")
    mock_get.return_value = mock_response

    times = fetch_prayer_times("NonExistentCity", "NonExistentCountry")
    assert times is None
    captured = capsys.readouterr()
    assert "Error fetching prayer times for NonExistentCity, NonExistentCountry: 404 Client Error" in captured.err

@patch('requests.get')
def test_fetch_prayer_times_invalid_json_response(mock_get):
    """
    Tests handling of a response that is not valid JSON.
    The current application logic in updateAzaanTimers.py does not catch json.JSONDecodeError,
    so this test expects the unhandled exception.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", doc="<html...>", pos=0)
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    # The current code will raise json.JSONDecodeError without catching it.
    with pytest.raises(json.JSONDecodeError):
        fetch_prayer_times("London", "UK")

@patch('requests.get')
def test_fetch_prayer_times_malformed_api_response_missing_results(mock_get, capsys):
    """Tests handling of API response missing the 'results' key."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {} # Missing 'results'
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    times = fetch_prayer_times("London", "UK")
    assert times is None
    captured = capsys.readouterr()
    assert "Error parsing API response: Missing 'results' or 'datetime' key in response for London, UK." in captured.err

@patch('requests.get')
def test_fetch_prayer_times_malformed_api_response_missing_datetime(mock_get, capsys):
    """Tests handling of API response missing the 'datetime' key within 'results'."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"results": {}} # Missing 'datetime'
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    times = fetch_prayer_times("London", "UK")
    assert times is None
    captured = capsys.readouterr()
    assert "Error parsing API response: Missing 'results' or 'datetime' key in response for London, UK." in captured.err

@patch('requests.get')
def test_fetch_prayer_times_malformed_api_response_empty_datetime(mock_get, capsys):
    """Tests handling of API response with an empty 'datetime' list."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"results": {"datetime": []}} # Empty datetime list
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    times = fetch_prayer_times("London", "UK")
    assert times is None
    captured = capsys.readouterr()
    assert "Error parsing API response: Missing 'results' or 'datetime' key in response for London, UK." in captured.err

@patch('requests.get')
def test_fetch_prayer_times_malformed_api_response_missing_times(mock_get, capsys):
    """Tests handling of API response where 'times' key is missing from the first datetime entry."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": {
            "datetime": [{"date": {}}] # Missing 'times'
        }
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    times = fetch_prayer_times("London", "UK")
    assert times is None
    captured = capsys.readouterr()
    assert "Error parsing API response structure for London, UK: 'times'" in captured.err

# --- save_prayer_times tests ---

def test_save_prayer_times_success(temp_output_file, mock_api_response_data, capsys):
    """Tests successful saving of prayer times to a JSON file."""
    result = save_prayer_times(str(temp_output_file), mock_api_response_data)
    assert result is True
    assert temp_output_file.exists()
    
    with open(temp_output_file, 'r') as f:
        saved_data = json.load(f)
    assert saved_data == mock_api_response_data
    captured = capsys.readouterr()
    assert f"Prayer times saved to {temp_output_file}" in captured.out

def test_save_prayer_times_creates_directory(tmp_path, mock_api_response_data, capsys):
    """Tests that save_prayer_times creates the directory if it doesn't exist."""
    nested_dir = tmp_path / "subdir" / "nested"
    filepath = nested_dir / "output.json"
    
    assert not nested_dir.exists()
    result = save_prayer_times(str(filepath), mock_api_response_data)
    assert result is True
    assert nested_dir.is_dir()
    assert filepath.exists()
    captured = capsys.readouterr()
    assert f"Prayer times saved to {filepath}" in captured.out

def test_save_prayer_times_io_error(temp_output_file, mock_api_response_data, capsys):
    """Tests handling of an IOError during file writing."""
    with patch('builtins.open', mock_open()) as mocked_open:
        mocked_open.side_effect = IOError("Disk full")
        result = save_prayer_times(str(temp_output_file), mock_api_response_data)
        assert result is False
        captured = capsys.readouterr()
        assert f"Error saving prayer times to file '{temp_output_file}': Disk full" in captured.err

def test_save_prayer_times_no_data(temp_output_file, capsys):
    """Tests handling when no prayer times data is provided to save."""
    result = save_prayer_times(str(temp_output_file), None)
    assert result is False
    assert not temp_output_file.exists()
    captured = capsys.readouterr()
    assert "No prayer times data to save." in captured.out

# --- main function tests ---

@patch('updateAzaanTimers.fetch_prayer_times')
@patch('updateAzaanTimers.save_prayer_times')
@patch('argparse.ArgumentParser.parse_args')
@patch('sys.stdout', new_callable=MagicMock) # Use MagicMock to capture write calls
def test_main_success(mock_parse_args, mock_save_prayer_times, mock_fetch_prayer_times, mock_stdout, mock_api_response_data):
    """Tests successful execution of the main CLI function."""
    mock_parse_args.return_value = MagicMock(
        city="London", country="UK", method="2", output="adhan_times.json"
    )
    mock_fetch_prayer_times.return_value = mock_api_response_data
    mock_save_prayer_times.return_value = True # Simulate successful save (its own prints are handled separately)

    main()

    mock_fetch_prayer_times.assert_called_once_with("London", "UK", "2")
    mock_save_prayer_times.assert_called_once_with("adhan_times.json", mock_api_response_data)
    
    # Check printed output
    output_calls = "".join([call.args[0] for call in mock_stdout.write.call_args_list])
    assert "Fetching prayer times for London, UK using method 2..." in output_calls
    # The 'Prayer times saved to ...' message comes from save_prayer_times itself,
    # which is mocked here, so it's not captured by `main`'s stdout.
    # If we wanted to capture that, we'd need to mock the print inside save_prayer_times
    # or let save_prayer_times run naturally with a temp file.
    # For now, asserting main's direct prints and call counts is sufficient.

@patch('updateAzaanTimers.fetch_prayer_times')
@patch('updateAzaanTimers.save_prayer_times')
@patch('argparse.ArgumentParser.parse_args')
@patch('sys.stdout', new_callable=MagicMock)
def test_main_fetch_failure(mock_parse_args, mock_save_prayer_times, mock_fetch_prayer_times, mock_stdout):
    """Tests main function behavior when fetching prayer times fails."""
    mock_parse_args.return_value = MagicMock(
        city="London", country="UK", method="2", output="adhan_times.json"
    )
    mock_fetch_prayer_times.return_value = None # Simulate failure
    mock_save_prayer_times.return_value = True # Should not be called

    main()

    mock_fetch_prayer_times.assert_called_once_with("London", "UK", "2")
    mock_save_prayer_times.assert_not_called()
    output_calls = "".join([call.args[0] for call in mock_stdout.write.call_args_list])
    assert "Failed to retrieve or save prayer times." in output_calls


@patch('updateAzaanTimers.fetch_prayer_times')
@patch('updateAzaanTimers.save_prayer_times')
@patch('argparse.ArgumentParser.parse_args')
@patch('sys.stdout', new_callable=MagicMock)
def test_main_save_failure(mock_parse_args, mock_save_prayer_times, mock_fetch_prayer_times, mock_stdout, mock_api_response_data):
    """Tests main function behavior when saving prayer times fails."""
    mock_parse_args.return_value = MagicMock(
        city="London", country="UK", method="2", output="adhan_times.json"
    )
    mock_fetch_prayer_times.return_value = mock_api_response_data
    mock_save_prayer_times.return_value = False # Simulate failure

    main()

    mock_fetch_prayer_times.assert_called_once_with("London", "UK", "2")
    mock_save_prayer_times.assert_called_once_with("adhan_times.json", mock_api_response_data)
    output_calls = "".join([call.args[0] for call in mock_stdout.write.call_args_list])
    assert "Failed to retrieve or save prayer times." in output_calls

```