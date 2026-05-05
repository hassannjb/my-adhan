```python
import pytest
import json
import os
import requests # Import requests to use its exceptions
from unittest.mock import patch, Mock

# Assuming updateAzaanTimers.py is in the root directory of the project
# If it's in a subdirectory, adjust the import path accordingly.
from updateAzaanTimers import fetch_prayer_times, save_prayer_times, main, PRAYER_TIMES_API_URL

# --- Fixtures ---

@pytest.fixture
def mock_response():
    """Fixture to mock requests.Response object."""
    return Mock()

@pytest.fixture
def mock_requests_get(mock_response):
    """Fixture to mock requests.get and return a mock response."""
    with patch('requests.get', return_value=mock_response) as mock_get:
        yield mock_get

# --- Test fetch_prayer_times ---

def test_fetch_prayer_times_success(mock_requests_get, mock_response):
    """Test successful fetching of prayer times."""
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": {
            "datetime": [
                {
                    "times": {
                        "Fajr": "05:00",
                        "Sunrise": "06:15",
                        "Dhuhr": "13:00",
                        "Asr": "16:30",
                        "Sunset": "17:30",
                        "Maghrib": "17:30",
                        "Isha": "19:00",
                        "Imsak": "04:50"
                    }
                }
            ]
        }
    }
    city = "London"
    country = "UK"
    method = "2"

    times = fetch_prayer_times(city, country, method)

    mock_requests_get.assert_called_once_with(
        PRAYER_TIMES_API_URL, # Use the imported constant
        params={"city": city, "country": country, "method": method},
        timeout=10
    )
    assert times == mock_response.json.return_value['results']['datetime'][0]['times']

def test_fetch_prayer_times_api_error(mock_requests_get, mock_response):
    """Test handling of HTTP errors during API fetch."""
    mock_response.raise_for_status.side_effect = requests.exceptions.RequestException("HTTP Error")
    city = "London"
    country = "UK"
    method = "2"

    with patch('builtins.print') as mock_print:
        times = fetch_prayer_times(city, country, method)
        mock_print.assert_called_with(f"Error fetching prayer times for {city}, {country}: HTTP Error")
    assert times is None

def test_fetch_prayer_times_parse_error_missing_results(mock_requests_get, mock_response):
    """Test handling of API response missing 'results'."""
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": "something_else"} # Missing 'results'
    city = "London"
    country = "UK"
    method = "2"

    with patch('builtins.print') as mock_print:
        times = fetch_prayer_times(city, country, method)
        mock_print.assert_called_with(f"Error parsing API response: Missing 'results' or 'datetime' key in response for {city}, {country}.")
    assert times is None

def test_fetch_prayer_times_parse_error_missing_datetime(mock_requests_get, mock_response):
    """Test handling of API response missing 'datetime'."""
    mock_response.status_code = 200
    mock_response.json.return_value = {"results": {"data": "something_else"}} # Missing 'datetime'
    city = "London"
    country = "UK"
    method = "2"

    with patch('builtins.print') as mock_print:
        times = fetch_prayer_times(city, country, method)
        mock_print.assert_called_with(f"Error parsing API response: Missing 'results' or 'datetime' key in response for {city}, {country}.")
    assert times is None

def test_fetch_prayer_times_parse_error_empty_datetime_list(mock_requests_get, mock_response):
    """Test handling of API response with empty 'datetime' list."""
    mock_response.status_code = 200
    mock_response.json.return_value = {"results": {"datetime": []}} # Empty list
    city = "London"
    country = "UK"
    method = "2"

    with patch('builtins.print') as mock_print:
        times = fetch_prayer_times(city, country, method)
        mock_print.assert_called_with(f"Error parsing API response: Missing 'results' or 'datetime' key in response for {city}, {country}.")
    assert times is None

def test_fetch_prayer_times_timeout(mock_requests_get):
    """Test handling of request timeout."""
    mock_requests_get.side_effect = requests.exceptions.Timeout("Timeout occurred")
    city = "London"
    country = "UK"
    method = "2"

    with patch('builtins.print') as mock_print:
        times = fetch_prayer_times(city, country, method)
        mock_print.assert_called_with(f"Error fetching prayer times for {city}, {country}: Timeout occurred")
    assert times is None

# --- Test save_prayer_times ---

def test_save_prayer_times_success(tmp_path):
    """Test successful saving of prayer times to a JSON file."""
    filepath = tmp_path / "adhan_times.json"
    prayer_times = {
        "Fajr": "05:00",
        "Dhuhr": "13:00",
        "Asr": "16:30",
        "Maghrib": "17:30",
        "Isha": "19:00"
    }

    with patch('os.makedirs', return_value=None) as mock_makedirs:
        result = save_prayer_times(str(filepath), prayer_times)

    assert result is True
    assert os.path.exists(filepath)
    with open(filepath, 'r') as f:
        saved_data = json.load(f)
    assert saved_data == prayer_times
    mock_makedirs.assert_called_once_with(os.path.dirname(str(filepath)), exist_ok=True)


def test_save_prayer_times_no_data():
    """Test saving with empty prayer_times data."""
    filepath = "dummy.json"
    prayer_times = {}

    with patch('builtins.print') as mock_print:
        result = save_prayer_times(filepath, prayer_times)
        mock_print.assert_called_with("No prayer times data to save.")
    assert result is False

def test_save_prayer_times_io_error(tmp_path):
    """Test handling of IOError during file saving."""
    # Create a directory that cannot be written to.
    # On Unix-like systems, this can be achieved by changing permissions.
    # For cross-platform compatibility and simplicity in testing,
    # we'll mock `open` to raise an IOError.
    filepath = tmp_path / "no_write_access" / "adhan_times.json"
    prayer_times = {"Fajr": "05:00"}

    # Ensure the parent directory exists so `os.makedirs` doesn't fail first,
    # then mock `open` to raise an error.
    os.makedirs(tmp_path / "no_write_access", exist_ok=True)

    with patch('builtins.open', side_effect=IOError("Permission denied")) as mock_open:
        result = save_prayer_times(str(filepath), prayer_times)
        mock_open.assert_called_once_with(str(filepath), 'w')

    assert result is False
    with patch('builtins.print') as mock_print:
        # The error message is printed by save_prayer_times itself.
        # We check it was called with the correct error.
        mock_print.assert_any_call(f"Error saving prayer times to file '{filepath}': Permission denied")


# --- Test main CLI function ---

# Define PRAYER_TIMES_API_URL here if it's not globally available for tests
# PRAYER_TIMES_API_URL = "https://api.pray.zone/v2/times/today.json"

@pytest.mark.parametrize(
    "city, country, method, output_file, api_response_data, expected_print_calls, expected_save_times",
    [
        (
            "Mecca", "Saudi Arabia", "1", "mecca_times.json",
            {
                "results": {
                    "datetime": [
                        {
                            "times": {
                                "Fajr": "04:30", "Dhuhr": "12:00", "Asr": "15:30",
                                "Maghrib": "18:30", "Isha": "20:00"
                            }
                        }
                    ]
                }
            },
            [
                "Fetching prayer times for Mecca, Saudi Arabia using method 1...",
                "Prayer times saved to mecca_times.json"
            ],
            {"Fajr": "04:30", "Dhuhr": "12:00", "Asr": "15:30", "Maghrib": "18:30", "Isha": "20:00"}
        ),
        (
            "Kuala Lumpur", "Malaysia", "5", "kl_times.json",
            {
                "results": {
                    "datetime": [
                        {
                            "times": {
                                "Fajr": "05:30", "Dhuhr": "13:00", "Asr": "16:30",
                                "Maghrib": "19:00", "Isha": "20:30"
                            }
                        }
                    ]
                }
            },
            [
                "Fetching prayer times for Kuala Lumpur, Malaysia using method 5...",
                "Prayer times saved to kl_times.json"
            ],
            {"Fajr": "05:30", "Dhuhr": "13:00", "Asr": "16:30", "Maghrib": "19:00", "Isha": "20:30"}
        ),
        (
            "Cairo", "Egypt", "3", "output.json",
            {
                "results": {
                    "datetime": [
                        {
                            "times": {
                                "Fajr": "04:00", "Dhuhr": "11:45", "Asr": "15:15",
                                "Maghrib": "18:15", "Isha": "19:45"
                            }
                        }
                    ]
                }
            },
            [
                "Fetching prayer times for Cairo, Egypt using method 3...",
                "Prayer times saved to output.json"
            ],
            {"Fajr": "04:00", "Dhuhr": "11:45", "Asr": "15:15", "Maghrib": "18:15", "Isha": "19:45"}
        )
    ]
)
@patch('requests.get')
@patch('updateAzaanTimers.save_prayer_times')
def test_main_success(
    mock_save_prayer_times,
    mock_requests_get,
    city, country, method, output_file, api_response_data, expected_print_calls, expected_save_times
):
    """Test the main CLI function when API call and save are successful."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = api_response_data
    mock_requests_get.return_value = mock_response

    with patch('builtins.print') as mock_print:
        # Simulate command line arguments
        # Need to add the script name as the first argument for sys.argv
        args = ['updateAzaanTimers.py', f'--city={city}', f'--country={country}', f'--method={method}', f'--output={output_file}']
        with patch('sys.argv', args):
            main()

        # Check if requests.get was called correctly
        mock_requests_get.assert_called_once_with(
            PRAYER_TIMES_API_URL,
            params={"city": city, "country": country, "method": method},
            timeout=10
        )

        # Check if save_prayer_times was called correctly
        mock_save_prayer_times.assert_called_once_with(output_file, expected_save_times)

        # Check if print statements were called correctly
        # We need to ensure all expected calls are present, and no unexpected ones.
        printed_calls = [call[0][0] for call in mock_print.call_args_list]
        for call_arg in expected_print_calls:
            assert call_arg in printed_calls

        # Assert that the correct number of print calls were made (optional but good practice)
        assert mock_print.call_count == len(expected_print_calls)


@patch('requests.get')
@patch('updateAzaanTimers.save_prayer_times')
def test_main_api_failure(mock_save_prayer_times, mock_requests_get):
    """Test the main CLI function when API call fails."""
    mock_requests_get.side_effect = requests.exceptions.RequestException("Network error")

    with patch('builtins.print') as mock_print:
        args = ['updateAzaanTimers.py', '--city=London', '--country=UK']
        with patch('sys.argv', args):
            main()

        mock_requests_get.assert_called_once_with(
            PRAYER_TIMES_API_URL,
            params={"city": "London", "country": "UK", "method": "2"}, # Default method
            timeout=10
        )
        mock_save_prayer_times.assert_not_called()
        
        printed_calls = [call[0][0] for call in mock_print.call_args_list]
        assert "Fetching prayer times for London, UK using method 2..." in printed_calls
        assert "Error fetching prayer times for London, UK: Network error" in printed_calls
        assert "Failed to retrieve or save prayer times." in printed_calls


@patch('requests.get')
@patch('updateAzaanTimers.save_prayer_times')
def test_main_save_failure(mock_save_prayer_times, mock_requests_get):
    """Test the main CLI function when saving fails."""
    mock_response = Mock()
    mock_response.status_code = 200
    api_times = {"Fajr": "05:00", "Dhuhr": "13:00"}
    mock_response.json.return_value = {"results": {"datetime": [{"times": api_times}]}}
    mock_requests_get.return_value = mock_response

    mock_save_prayer_times.return_value = False  # Simulate save failure

    with patch('builtins.print') as mock_print:
        args = ['updateAzaanTimers.py', '--city=London', '--country=UK', '--output=test.json']
        with patch('sys.argv', args):
            main()

        mock_requests_get.assert_called_once_with(
            PRAYER_TIMES_API_URL,
            params={"city": "London", "country": "UK", "method": "2"}, # Default method
            timeout=10
        )
        mock_save_prayer_times.assert_called_once_with("test.json", api_times)
        
        printed_calls = [call[0][0] for call in mock_print.call_args_list]
        assert "Fetching prayer times for London, UK using method 2..." in printed_calls
        # The save_prayer_times function itself prints an error if it returns False.
        # We expect that specific error message to be printed.
        assert "Error saving prayer times to file 'test.json'" in printed_calls # This error comes from save_prayer_times
        assert "Failed to retrieve or save prayer times." in printed_calls


@pytest.mark.parametrize("args_list", [
    (['updateAzaanTimers.py']), # Missing city and country
    (['updateAzaanTimers.py', '--city=London']), # Missing country
    (['updateAzaanTimers.py', '--country=UK']), # Missing city
])
@patch('requests.get')
@patch('updateAzaanTimers.save_prayer_times')
def test_main_missing_arguments(mock_save_prayer_times, mock_requests_get, args_list):
    """Test that main exits or shows error for missing required arguments."""
    with patch('builtins.print') as mock_print:
        with patch('sys.argv', args_list):
            with pytest.raises(SystemExit) as excinfo:
                main()
            # Check if argparse printed an error message before exiting
            assert excinfo.value.code == 2 # argparse typically exits with code 2 for usage errors

            # Verify that fetch and save were not called
            mock_requests_get.assert_not_called()
            mock_save_prayer_times.assert_not_called()

            # Check for argument error messages. The exact output can vary, but usually includes help.
            # The presence of SystemExit is the primary assertion.
            # We can check if anything was printed, which might be usage info.
            assert mock_print.call_count > 0

```