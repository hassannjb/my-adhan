
import argparse
import requests
import json
from datetime import datetime, timedelta
import os
import sys

# External API endpoint for prayer times (example: pray.zone)
# This URL might need to be updated or configured based on the chosen API.
PRAYER_TIMES_API_URL = "https://api.pray.zone/v2/times/today.json"

def fetch_prayer_times(city, country, method="2"):
    """
    Fetches prayer times from an external API for a given city and country.
    :param city: City name (e.g., "London").
    :param country: Country name (e.g., "UK").
    :param method: Calculation method ID (e.g., "2" for Muslim World League).
    :return: A dictionary of prayer times or None on failure.
    """
    params = {
        "city": city,
        "country": country,
        "method": method
    }
    try:
        response = requests.get(PRAYER_TIMES_API_URL, params=params, timeout=10)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        data = response.json()
        
        # Adjust based on actual API response structure
        # Example: data['results']['datetime'][0]['times']
        if 'results' in data and 'datetime' in data['results'] and data['results']['datetime']:
            return data['results']['datetime'][0]['times']
        else:
            print(f"Error parsing API response: Missing 'results' or 'datetime' key in response for {city}, {country}.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching prayer times for {city}, {country}: {e}")
        return None
    except (KeyError, IndexError) as e:
        print(f"Error parsing API response structure for {city}, {country}: {e}")
        return None

def save_prayer_times(filepath, prayer_times):
    """
    Saves prayer times to a JSON file.
    :param filepath: Path to the output JSON file.
    :param prayer_times: Dictionary of prayer times.
    :return: True on success, False on failure.
    """
    if not prayer_times:
        print("No prayer times data to save.")
        return False
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(prayer_times, f, indent=4)
        print(f"Prayer times saved to {filepath}")
        return True
    except IOError as e:
        print(f"Error saving prayer times to file '{filepath}': {e}")
        return False

def main():
    """
    Main function for the CLI script to fetch and update Adhan prayer times.
    """
    parser = argparse.ArgumentParser(description="Update Adhan prayer times for a specific location.")
    parser.add_argument("--city", required=True, help="City name (e.g., 'London')")
    parser.add_argument("--country", required=True, help="Country name (e.g., 'UK')")
    parser.add_argument("--method", default="2", help="Calculation method ID (e.g., '2' for MWL). See API docs.")
    parser.add_argument("--output", default="adhan_times.json", help="Output JSON file path. Default: adhan_times.json")

    args = parser.parse_args()

    print(f"Fetching prayer times for {args.city}, {args.country} using method {args.method}...")
    times = fetch_prayer_times(args.city, args.country, args.method)

    if times:
        save_prayer_times(args.output, times)
    else:
        print("Failed to retrieve or save prayer times.")

if __name__ == "__main__":
    main()

