import requests


def get_location_details():
    """Uses IP Geolocation to get coordinates."""
    try:
        response = requests.get('http://ip-api.com/json/').json()
        if response['status'] == 'success':
            return response
        else:
            raise Exception("API Lookup Failed")
    except:
        # Fallback
        return {'city': 'Unknown', 'timezone': 'UTC', 'lat': 0.0, 'lon': 0.0}