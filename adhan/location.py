"""
Location services — the single source of truth for all geocoding/IP lookups.

Previously duplicated across utils/location.py, utils/prayer_helper.py,
and gui_clock.py. Now in one place.
"""
from __future__ import annotations

import logging
from typing import Optional

import pytz
import requests
from timezonefinder import TimezoneFinder

from adhan.models import Coordinates

logger = logging.getLogger(__name__)

_IP_API_URL = "http://ip-api.com/json/"
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_REQUEST_TIMEOUT = 5

_tf = TimezoneFinder()


def get_current_location() -> tuple[Coordinates, pytz.BaseTzInfo, str]:
    """
    Detect the current location via IP geolocation.
    Returns (coordinates, timezone, city_name).
    Falls back to (0, 0), UTC, "Offline" on any failure.
    """
    try:
        data = requests.get(_IP_API_URL, timeout=_REQUEST_TIMEOUT).json()
        if data.get("status") == "success":
            return (
                Coordinates(latitude=data["lat"], longitude=data["lon"]),
                pytz.timezone(data["timezone"]),
                data.get("city", "Unknown"),
            )
        logger.warning("IP geolocation returned status=%s", data.get("status"))
    except Exception as e:
        logger.warning("IP geolocation failed: %s", e)
    return Coordinates(0.0, 0.0), pytz.UTC, "Offline"


def geocode_city(city: str) -> Optional[tuple[Coordinates, pytz.BaseTzInfo, str]]:
    """
    Resolve a free-text city name to (coordinates, timezone, resolved_city_name).
    Returns None if the city cannot be geocoded.

    Uses Nominatim (OpenStreetMap) for lat/lon and BigDataCloud for timezone
    — both are free with no API key required.
    """
    try:
        results = requests.get(
            _NOMINATIM_URL,
            params={"q": city, "format": "json", "limit": 1},
            headers={"User-Agent": "adhan-clock/1.0"},
            timeout=_REQUEST_TIMEOUT,
        ).json()

        if not results:
            logger.info("Nominatim returned no results for %r", city)
            return None

        lat = float(results[0]["lat"])
        lon = float(results[0]["lon"])
        coords = Coordinates(latitude=lat, longitude=lon)

        tz_name = _tf.timezone_at(lat=lat, lng=lon) or "UTC"
        resolved_city = results[0].get("display_name", city).split(",")[0].strip()
        return coords, pytz.timezone(tz_name), resolved_city

    except Exception as e:
        logger.warning("Geocoding failed for %r: %s", city, e)
        return None
