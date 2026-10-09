"""
Pull a place name out of a question ("... in Toronto", "for Makkah") and
geocode it with Nominatim (OpenStreetMap). The timezone comes from
timezonefinder, offline.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from functools import lru_cache

import requests
from timezonefinder import TimezoneFinder

logger = logging.getLogger(__name__)

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_HEADERS = {"User-Agent": "adhan-clock/1.0 (https://adhan.searchthehadith.fyi)"}
_tf = TimezoneFinder()
# Nominatim's usage policy: at most one request per second from the whole app.
_MIN_GAP = 1.0
_gap_lock = threading.Lock()
_last_call = 0.0

_PLACE_RE = re.compile(r"\b(?:in|for|at|near)\s+([^\W\d][\w .'\-]*?)\s*(?:[?.!,;]|$)", re.UNICODE)
_TRAILING = re.compile(
    r"\s+(?:today|tonight|tomorrow|please|now|prayer|prayers|salah|salat|namaz|times?|timings?|"
    r"on|this|next|last|time|is|will|be|according|to|the|by|with|using)$",
    re.IGNORECASE,
)
_LEADING = re.compile(r"^(?:in|for|at|near)\s+", re.IGNORECASE)
# Things that follow "in/for/at" without being places.
_NOT_PLACES = re.compile(
    r"^(?:the\s+)?(?:morning|evening|afternoon|night|day|daytime|summer|winter|spring|autumn|fall|"
    r"ramadan|ramadhan|congregation|jamaat|jamaah|jama'ah|mosque|masjid|home|work|school|"
    r"my\s+\w+|our\s+\w+|me|us|here|there|this\s+\w+|that\s+\w+|hanafi|shafi'?i|maliki|hanbali|"
    r"standard|madhab|madhhab|islam|sunnah|quran|hadith|time|least|most|all|once|total|between|"
    r"order|a\s+row|advance|jannah|paradise|travel|journey|sunrise|sunset|midnight|zawal|"
    r"fajr|dhuhr|zuhr|asr|maghrib|isha|witr|tahajjud|duha|winter\s+\w+|summer\s+\w+)\b",
    re.IGNORECASE,
)


def extract_place(text: str) -> str | None:
    """Return the place name mentioned in `text`, or None."""
    for m in _PLACE_RE.finditer(text):
        name = m.group(1).strip()
        prev = None
        while prev != name:
            prev = name
            name = _TRAILING.sub("", name).strip()
            name = _LEADING.sub("", name).strip()
        if not name or _NOT_PLACES.match(name):
            continue
        return name
    return None


@lru_cache(maxsize=512)
def geocode(name: str) -> dict | None:
    """Resolve a place name to {name, lat, lng, tz}, or None if not found."""
    global _last_call
    try:
        with _gap_lock:
            time.sleep(max(0.0, _last_call + _MIN_GAP - time.monotonic()))
            _last_call = time.monotonic()
        r = requests.get(
            _NOMINATIM_URL,
            params={"q": name, "format": "json", "limit": 1, "addressdetails": 1,
                    "accept-language": "en"},
            headers=_HEADERS,
            timeout=6,
        )
        r.raise_for_status()
        results = r.json()
    except Exception as e:
        logger.warning("geocoding %r failed: %s", name, e)
        raise LookupError("The place lookup service isn't responding right now.") from e
    if not results:
        return None
    hit = results[0]
    lat, lng = float(hit["lat"]), float(hit["lon"])
    addr = hit.get("address", {})
    place = (addr.get("city") or addr.get("town") or addr.get("village")
             or addr.get("state") or hit.get("name") or name)
    country = addr.get("country")
    label = f"{place}, {country}" if country and country != place else place
    return {"name": label, "lat": lat, "lng": lng,
            "tz": _tf.timezone_at(lat=lat, lng=lng) or "UTC"}
