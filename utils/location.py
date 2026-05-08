# Backward-compatibility shim.
# The canonical implementation is now in adhan/location.py.
from adhan.location import get_current_location


def get_location_details():
    """Deprecated — use adhan.location.get_current_location()."""
    coords, tz, city = get_current_location()
    return {"city": city, "timezone": tz.zone, "lat": coords.latitude, "lon": coords.longitude}


__all__ = ["get_location_details", "get_current_location"]
