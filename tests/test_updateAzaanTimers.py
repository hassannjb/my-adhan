```python
import pytest
from unittest.mock import Mock, patch
import json
import sys
import os
import requests # Need to import requests to mock it

# Assume updateAzaanTimers.py exists at the root of the project and is importable.
# If not, adjust sys.path or project structure for imports to work.
import updateAzaanTimers # Import the script as a module

# Mock API response for successful fetches
MOCK_SUCCESS_API_RESPONSE = {
    "results": {
        "datetime": [
            {
                "times": {
                    "Fajr": "05:00", "Dhuhr": "12:30", "Asr": "16:00",
                    "Maghrib": "18:00", "Isha": "20:00", "Sunrise": "06:30", "Sunset": "17:45"
                },
                "date": {
                    "timestamp": 1678886400,
                    "gregorian": "2023-03-15",
                    "hijri": "1444-08-23"
                }
            }
        ]
    }
}

@pytest.fixture
def mock_requests_get():
    """Fixture to mock requests.get calls made by updateAzaanTimers."""
    with patch('updateAzaanTimers.requests.get') as mock_get:
        yield mock_get

@pytest.fixture(autouse=True)
def restore_sys_argv():
    """Fixture to restore sys.argv after each test that modifies it."""
    original_argv = sys.argv[:]
    yield
    sys.argv = original_argv

# --- Tests for fetch_prayer_times function ---
def test_fetch_prayer_times_success(mock_requests_get):
    """Test successful fetching of prayer times from the API."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_SUCCESS_API_RESPONSE
    mock_requests_get.return_value = mock_response

    times = updateAzaanTimers.fetch_prayer_times("London", "UK")
    assert times == MOCK_SUCCESS_API_RESPONSE['results']['datetime'][0]['times']
    mock_requests_get.assert_called_once_with(
        updateAzaanTimers.PRAYER_TIMES_API_URL,
        params={"city": "London", "country": "UK", "method": "2"},
        timeout=10
    )

def test_fetch_prayer_times_api_error(mock_requests_get, capsys):
    """Test fetching prayer times when the API returns an HTTP error."""
    mock_requests_get.side_effect = requests.exceptions.HTTPError("404 Not Found")

    times = updateAzaanTimers.fetch_prayer_times("InvalidCity", "InvalidCountry")
    assert times is None
    captured = capsys.readouterr()
    assert "Error fetching prayer times for InvalidCity, InvalidCountry: 404 Not Found" in captured.out

def test_fetch_prayer_times_network_error(mock_requests_get, capsys):
    """Test fetching prayer times when a network connection error occurs."""
    mock_requests_get.side_effect = requests.exceptions.ConnectionError("Network unreachable")

    times = updateAzaanTimers.fetch_prayer_times("SomeCity", "SomeCountry")
    assert times is None
    captured = capsys.readouterr()
    assert "Error fetching prayer times for SomeCity, SomeCountry: Network unreachable" in captured.out

def test_fetch_prayer_times_invalid_api_response_structure(mock_requests_get, capsys):
    """Test fetching prayer times when API returns malformed JSON structure."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"bad_key": "bad_value"} # Missing expected keys
    mock_requests_get.return_value = mock_response

    times = updateAzaanTimers.fetch_prayer_times("City", "Country")
    assert times is None
    captured = capsys.readouterr()
    assert "Error parsing API response: Missing 'results' or 'datetime' key in response for City, Country." in captured.out

def test_fetch_prayer_times_timeout(mock_requests_get, capsys):
    """Test fetching prayer times when the API request times out."""
    mock_requests_get.side_effect = requests.exceptions.Timeout("Request timed out")

    times = updateAzaanTimers.fetch_prayer_times("SlowCity", "SlowCountry")
    assert times is None
    captured = capsys.readouterr()
    assert "Error fetching prayer times for SlowCity, SlowCountry: Request timed out" in captured.out

# --- Tests for save_prayer_times function ---
def test_save_prayer_times_success(tmp_path):
    """Test successful saving of prayer times to a JSON file."""
    output_file = tmp_path / "test_adhan_times.json"
    prayer_data = {"Fajr": "05:00", "Dhuhr": "12:30"}

    success = updateAzaanTimers.save_prayer_times(str(output_file), prayer_data)
    assert success is True
    assert output_file.exists()
    content = json.loads(output_file.read_text())
    assert content == prayer_data

def test_save_prayer_times_to_nonexistent_directory(tmp_path):
    """Test saving prayer times to a file in a non-existent directory."""
    output_dir = tmp_path / "new_dir"
    output_file = output_dir / "test_adhan_times.json"
    prayer_data = {"Fajr": "05:00"}

    # os.makedirs(..., exist_ok=True) handles this, so it should succeed
    success = updateAzaanTimers.save_prayer_times(str(output_file), prayer_data)
    assert success is True
    assert output_file.exists()
    assert output_dir.exists()

def test_save_prayer_times_file_write_error(tmp_path, capsys):
    """Test saving prayer times when a file write error occurs."""
    # Simulate a permission denied error by patching builtins.open
    with patch('builtins.open', mock_open()) as mock_file:
        mock_file.side_effect = IOError("Permission denied")

        output_file = tmp_path / "test_adhan_times.json"
        prayer_data = {"Fajr": "05:00"}

        success = updateAzaanTimers.save_prayer_times(str(output_file), prayer_data)
        assert success is False
        captured = capsys.readouterr()
        assert f"Error saving prayer times to file '{output_file}': Permission denied" in captured.out

def test_save_prayer_times_no_data(tmp_path, capsys):
    """Test saving prayer times when no data is provided."""
    output_file = tmp_path / "test_adhan_times.json"
    
    success = updateAzaanTimers.save_prayer_times(str(output_file), None)
    assert success is False
    captured = capsys.readouterr()
    assert "No prayer times data to save." in captured.out
    assert not output_file.exists()


# --- Tests for main() function (CLI entry point) ---
def test_main_success(mock_requests_get, tmp_path, capsys):
    """Test successful fetching and saving of prayer times via main CLI function."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_SUCCESS_API_RESPONSE
    mock_requests_get.return_value = mock_response

    test_output_file = tmp_path / "test_adhan_times.json"
    sys.argv = [
        "updateAzaanTimers.py",
        "--city", "London",
        "--country", "UK",
        "--method", "2",
        "--output", str(test_output_file)
    ]

    updateAzaanTimers.main()

    mock_requests_get.assert_called_once_with(
        updateAzaanTimers.PRAYER_TIMES_API_URL,
        params={"city": "London", "country": "UK", "method": "2"},
        timeout=10
    )

    assert test_output_file.exists()
    content = json.loads(test_output_file.read_text())
    assert content == MOCK_SUCCESS_API_RESPONSE['results']['datetime'][0]['times']

    captured = capsys.readouterr()
    assert "Fetching prayer times for London, UK using method 2..." in captured.out
    assert f"Prayer times saved to {test_output_file}" in captured.out

def test_main_api_failure_path(mock_requests_get, tmp_path, capsys):
    """Test main function when API call fails (e.g., HTTP error)."""
    mock_requests_get.side_effect = requests.exceptions.HTTPError("404 Not Found")

    test_output_file = tmp_path / "test_adhan_times_error.json"
    sys.argv = [
        "updateAzaanTimers.py",
        "--city", "InvalidCity",
        "--country", "InvalidCountry",
        "--output", str(test_output_file)
    ]

    updateAzaanTimers.main()

    assert not test_output_file.exists()
    captured = capsys.readouterr()
    assert "Error fetching prayer times for InvalidCity, InvalidCountry: 404 Not Found" in captured.out
    assert "Failed to retrieve or save prayer times." in captured.out

def test_main_file_write_failure_path(mock_requests_get, tmp_path, capsys):
    """Test main function when saving to file fails after successful API fetch."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_SUCCESS_API_RESPONSE
    mock_requests_get.return_value = mock_response

    # Simulate permission denied during file write
    mock_open_patch = patch('builtins.open', mock_open())
    with mock_open_patch as mock_file_open:
        mock_file_open.side_effect = IOError("Permission denied")

        test_output_file = tmp_path / "test_adhan_times_permission_denied.json"
        sys.argv = [
            "updateAzaanTimers.py",
            "--city", "City",
            "--country", "Country",
            "--output", str(test_output_file)
        ]

        updateAzaanTimers.main()

        captured = capsys.readouterr()
        assert "Fetching prayer times for City, Country using method 2..." in captured.out
        assert f"Error saving prayer times to file '{test_output_file}': Permission denied" in captured.out
        assert "Failed to retrieve or save prayer times." in captured.out
        assert not test_output_file.exists() # Should not be created

def test_main_default_output_file(mock_requests_get, tmp_path, capsys):
    """Test main function uses default output file if not specified."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_SUCCESS_API_RESPONSE
    mock_requests_get.return_value = mock_response

    # Change current working directory to tmp_path so default file lands there
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    sys.argv = [
        "updateAzaanTimers.py",
        "--city", "London",
        "--country", "UK",
        "--method", "2"
    ]

    try:
        updateAzaanTimers.main()

        default_output_file = tmp_path / "adhan_times.json"
        assert default_output_file.exists()
        content = json.loads(default_output_file.read_text())
        assert content == MOCK_SUCCESS_API_RESPONSE['results']['datetime'][0]['times']

        captured = capsys.readouterr()
        # The script prints the full path, but if run in CWD, it might just print the name.
        # Let's ensure the full path is tested given our main.py prints f"Prayer times saved to {filepath}"
        assert f"Prayer times saved to {default_output_file}" in captured.out
    finally:
        os.chdir(original_cwd) # Restore original CWD
```