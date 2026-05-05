```python
import pytest
import json
import os
from unittest.mock import patch, MagicMock
import requests # For mocking exceptions

# Add parent directory to sys.path to allow importing updateAzaanTimers.py
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from updateAzaanTimers import fetch_prayer_times, save_prayer_times, main, PRAYER_TIMES_API_URL

# Fixture for a successful API response
@pytest.fixture
def mock_success_response():
    return {
        "code": 200,
        "status": "OK",
        "results": {
            "datetime": [
                {
                    "times": {
                        "Fajr": "05:00",
                        "Sunrise": "06:30",
                        "Dhuhr": "12:30",
                        "Asr": "16:00",
                        "Sunset": "19:30",
                        "Maghrib": "19:45",
                        "Isha": "21:00"
                    },
                    "date": {
                        "timestamp": "1678886400"
                    }
                }
            ],
            "location": {
                "latitude": 51.5,
                "longitude": -0.1,
                "timezone": "Europe/London"
            },
            "settings": {
                "calculation_method": "MWL"
            }
        }
    }

# Fixture for prayer times data to save
@pytest.fixture
def prayer_times_to_save():
    return {
        "Fajr": "05:05",
        "Dhuhr": "12:35",
        "Asr": "16:05",
        "Maghrib": "19:50",
        "Isha": "21:05"
    }

# region: Tests for fetch_prayer_times

def test_fetch_prayer_times_success(mocker, mock_success_response):
    """Test successful fetching and parsing of prayer times from the API."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_success_response
    mock_response.raise_for_status.return_value = None # Simulate no HTTP errors
    mocker.patch('requests.get', return_value=mock_response)

    times = fetch_prayer_times("London", "UK", method="2")
    assert times == mock_success_response['results']['datetime'][0]['times']
    requests.get.assert_called_once_with(
        PRAYER_TIMES_API_URL,
        params={"city": "London", "country": "UK", "method": "2"},
        timeout=10
    )

def test_fetch_prayer_times_http_error(mocker, capsys):
    """Test handling of HTTP errors (e.g., 404, 500) from the API."""
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Client Error: Not Found for url: ...")
    mocker.patch('requests.get', return_value=mock_response)

    times = fetch_prayer_times("InvalidCity", "InvalidCountry")
    assert times is None
    captured = capsys.readouterr()
    assert "Error fetching prayer times for InvalidCity, InvalidCountry: 404 Client Error" in captured.err

def test_fetch_prayer_times_connection_error(mocker, capsys):
    """Test handling of network connection errors."""
    mocker.patch('requests.get', side_effect=requests.exceptions.ConnectionError("Network unreachable"))

    times = fetch_prayer_times("London", "UK")
    assert times is None
    captured = capsys.readouterr()
    assert "Error fetching prayer times for London, UK: Network unreachable" in captured.err

def test_fetch_prayer_times_timeout_error(mocker, capsys):
    """Test handling of request timeout errors."""
    mocker.patch('requests.get', side_effect=requests.exceptions.Timeout("Request timed out"))

    times = fetch_prayer_times("London", "UK")
    assert times is None
    captured = capsys.readouterr()
    assert "Error fetching prayer times for London, UK: Request timed out" in captured.err

def test_fetch_prayer_times_invalid_json_response(mocker, capsys):
    """Test handling when the API returns non-JSON or malformed JSON."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "doc", 0)
    mock_response.raise_for_status.return_value = None
    mocker.patch('requests.get', return_value=mock_response)

    times = fetch_prayer_times("London", "UK")
    assert times is None
    captured = capsys.readouterr()
    assert "Error fetching prayer times for London, UK: Expecting value: line 1 column 1 (char 0)" in captured.err

def test_fetch_prayer_times_missing_results_key(mocker, capsys):
    """Test handling when the API response misses the 'results' key."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"code": 200, "status": "OK"} # Missing 'results'
    mock_response.raise_for_status.return_value = None
    mocker.patch('requests.get', return_value=mock_response)

    times = fetch_prayer_times("London", "UK")
    assert times is None
    captured = capsys.readouterr()
    assert "Error parsing API response: Missing 'results' or 'datetime' key in response for London, UK." in captured.out

def test_fetch_prayer_times_missing_datetime_key(mocker, capsys):
    """Test handling when the API response misses the 'datetime' key."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"code": 200, "status": "OK", "results": {}} # Missing 'datetime'
    mock_response.raise_for_status.return_value = None
    mocker.patch('requests.get', return_value=mock_response)

    times = fetch_prayer_times("London", "UK")
    assert times is None
    captured = capsys.readouterr()
    assert "Error parsing API response: Missing 'results' or 'datetime' key in response for London, UK." in captured.out

def test_fetch_prayer_times_empty_datetime_list(mocker, capsys):
    """Test handling when the 'datetime' list in the API response is empty."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"code": 200, "status": "OK", "results": {"datetime": []}} # Empty 'datetime' list
    mock_response.raise_for_status.return_value = None
    mocker.patch('requests.get', return_value=mock_response)

    times = fetch_prayer_times("London", "UK")
    assert times is None
    captured = capsys.readouterr()
    assert "Error parsing API response: Missing 'results' or 'datetime' key in response for London, UK." in captured.out

def test_fetch_prayer_times_missing_times_in_datetime(mocker, capsys):
    """Test handling when the 'times' key is missing inside a datetime object."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "code": 200,
        "status": "OK",
        "results": {
            "datetime": [{"date": {"timestamp": "1678886400"}}] # Missing 'times' key
        }
    }
    mock_response.raise_for_status.return_value = None
    mocker.patch('requests.get', return_value=mock_response)

    times = fetch_prayer_times("London", "UK")
    assert times is None
    captured = capsys.readouterr()
    assert "Error parsing API response structure for London, UK: 'times'" in captured.err

# endregion

# region: Tests for save_prayer_times

def test_save_prayer_times_success_new_file(tmp_path, prayer_times_to_save):
    """Test successful saving of prayer times to a new JSON file."""
    output_path = tmp_path / "adhan_times_test.json"
    result = save_prayer_times(str(output_path), prayer_times_to_save)
    assert result is True
    assert output_path.exists()
    with open(output_path, 'r') as f:
        data = json.load(f)
    assert data == prayer_times_to_save

def test_save_prayer_times_success_existing_file(tmp_path, prayer_times_to_save):
    """Test successful saving of prayer times, overwriting an existing JSON file."""
    output_path = tmp_path / "adhan_times_test.json"
    # Create a dummy existing file
    with open(output_path, 'w') as f:
        f.write('{"OldFajr": "04:00"}')

    result = save_prayer_times(str(output_path), prayer_times_to_save)
    assert result is True
    assert output_path.exists()
    with open(output_path, 'r') as f:
        data = json.load(f)
    assert data == prayer_times_to_save

def test_save_prayer_times_no_data_to_save(capsys):
    """Test behavior when no prayer times data is provided to save."""
    # Test with None
    result = save_prayer_times("dummy.json", None)
    assert result is False
    captured = capsys.readouterr()
    assert "No prayer times data to save." in captured.out

    # Test with empty dictionary
    result = save_prayer_times("dummy.json", {})
    # Note: capsys accumulates output, so previous message might still be there.
    # We re-read to confirm current behavior.
    captured = capsys.readouterr()
    assert "No prayer times data to save." in captured.out


def test_save_prayer_times_io_error(mocker, tmp_path, prayer_times_to_save, capsys):
    """Test handling of IOError during file writing (e.g., permission denied)."""
    # Create a path that would fail due to permission (mocking open)
    output_path = tmp_path / "forbidden_dir" / "adhan_times_test.json"
    mocker.patch('builtins.open', side_effect=IOError("Permission denied"))
    mocker.patch('os.makedirs') # Mock this to prevent actual directory creation, as open() will fail first

    result = save_prayer_times(str(output_path), prayer_times_to_save)
    assert result is False
    captured = capsys.readouterr()
    assert f"Error saving prayer times to file '{output_path}': Permission denied" in captured.out

def test_save_prayer_times_creates_directory(tmp_path, prayer_times_to_save):
    """Test that save_prayer_times creates necessary parent directories."""
    output_dir = tmp_path / "subdir" / "another_subdir"
    output_path = output_dir / "adhan_times_test.json"
    assert not output_dir.exists()

    result = save_prayer_times(str(output_path), prayer_times_to_save)
    assert result is True
    assert output_dir.is_dir() # Verify directory was created
    assert output_path.exists()

# endregion

# region: Tests for main function (CLI script entry point)

def test_main_success(mocker, capsys, tmp_path, mock_success_response):
    """Test successful execution of the main CLI function."""
    # Mock argparse arguments
    mocker.patch('argparse.ArgumentParser.parse_args', return_value=mocker.MagicMock(
        city="TestCity", country="TestCountry", method="5", output=str(tmp_path / "output.json")
    ))
    # Mock fetch_prayer_times to return data
    mocker.patch('updateAzaanTimers.fetch_prayer_times', return_value=mock_success_response['results']['datetime'][0]['times'])
    # Mock save_prayer_times to simulate success and prevent actual file IO
    mocker.patch('updateAzaanTimers.save_prayer_times', return_value=True)

    main()

    captured = capsys.readouterr()
    assert "Fetching prayer times for TestCity, TestCountry using method 5..." in captured.out
    updateAzaanTimers.fetch_prayer_times.assert_called_once_with("TestCity", "TestCountry", "5")
    updateAzaanTimers.save_prayer_times.assert_called_once_with(
        str(tmp_path / "output.json"), mock_success_response['results']['datetime'][0]['times']
    )
    # The actual `save_prayer_times` prints "Prayer times saved to {filepath}", but since it's mocked,
    # that specific output won't be in `captured.out` for this test.

def test_main_fetch_failure(mocker, capsys, tmp_path):
    """Test main function behavior when fetching prayer times fails."""
    mocker.patch('argparse.ArgumentParser.parse_args', return_value=mocker.MagicMock(
        city="TestCity", country="TestCountry", method="2", output=str(tmp_path / "output.json")
    ))
    mocker.patch('updateAzaanTimers.fetch_prayer_times', return_value=None)
    mocker.patch('updateAzaanTimers.save_prayer_times') # Should not be called

    main()

    captured = capsys.readouterr()
    assert "Fetching prayer times for TestCity, TestCountry using method 2..." in captured.out
    assert "Failed to retrieve or save prayer times." in captured.out
    updateAzaanTimers.fetch_prayer_times.assert_called_once()
    updateAzaanTimers.save_prayer_times.assert_not_called()

def test_main_save_failure(mocker, capsys, tmp_path, mock_success_response):
    """Test main function behavior when saving prayer times fails."""
    mocker.patch('argparse.ArgumentParser.parse_args', return_value=mocker.MagicMock(
        city="TestCity", country="TestCountry", method="2", output=str(tmp_path / "output.json")
    ))
    mocker.patch('updateAzaanTimers.fetch_prayer_times', return_value=mock_success_response['results']['datetime'][0]['times'])
    mocker.patch('updateAzaanTimers.save_prayer_times', return_value=False) # Simulate save failure

    main()

    captured = capsys.readouterr()
    assert "Fetching prayer times for TestCity, TestCountry using method 2..." in captured.out
    assert "Failed to retrieve or save prayer times." in captured.out
    updateAzaanTimers.fetch_prayer_times.assert_called_once()
    updateAzaanTimers.save_prayer_times.assert_called_once()

# endregion
```