import requests
import pytz

def check_location():
    print("Checking location based on IP...")
    try:
        response = requests.get('http://ip-api.com/json/').json()
        if response['status'] == 'success':
            print(f"Detected IP: {response['query']}")
            print(f"Coordinates: {response['lat']}, {response['lon']}")
            print(f"Timezone: {response['timezone']}")
            print(f"City: {response['city']}, {response['country']}")
        else:
            print("Failed to detect location.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_location()