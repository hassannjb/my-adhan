"""
PrayerService — stateless, city-aware prayer time calculator.

Unlike PrayerClock (which is tied to the local machine's IP-detected location),
PrayerService accepts any city name and any date.  This is the entry point for
the RAG chatbot, CLI tools, and any code that needs to answer questions like
"what time is Fajr in Toronto tomorrow?"
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

import pytz

from adhan.calculator import build_params, calculate
from adhan.config import load_config
from adhan.location import geocode_city, get_current_location
from adhan.models import Config, Coordinates, PrayerSchedule

logger = logging.getLogger(__name__)


def _resolve_date(date_str: str) -> date:
    """
    Convert a flexible date string to a date object.
    Accepts: 'today', 'tomorrow', 'yesterday', or ISO format 'YYYY-MM-DD'.
    """
    s = date_str.strip().lower()
    today = datetime.now().date()
    if s in ("today", ""):
        return today
    if s == "tomorrow":
        return today + timedelta(days=1)
    if s == "yesterday":
        return today - timedelta(days=1)
    return date.fromisoformat(date_str)


class PrayerService:
    """
    Stateless prayer time service.

    Usage:
        svc = PrayerService()
        schedule = svc.get_times(city="Toronto", date_str="tomorrow")
        print(schedule.as_dict())
    """

    def __init__(self, config: Optional[Config] = None) -> None:
        self._config = config or load_config()

    def get_times(
        self,
        city: Optional[str] = None,
        date_str: str = "today",
    ) -> tuple[PrayerSchedule, str]:
        """
        Calculate prayer times for a city (or the current location if None).

        Returns (PrayerSchedule, resolved_city_name).
        Raises ValueError if the city cannot be geocoded.
        """
        target_date = _resolve_date(date_str)

        if city:
            result = geocode_city(city)
            if result is None:
                raise ValueError(f"Could not geocode city: {city!r}")
            coords, tz, resolved_city = result
        else:
            coords, tz, resolved_city = get_current_location()

        params = build_params(self._config)
        schedule = calculate(target_date, coords, params, tz)
        return schedule, resolved_city

    def format_answer(
        self,
        city: Optional[str],
        date_str: str = "today",
    ) -> str:
        """
        Convenience method: returns a human-readable string with all prayer times.
        Designed for use as a tool result in the RAG chatbot.
        """
        try:
            schedule, resolved_city = self.get_times(city=city, date_str=date_str)
        except ValueError as e:
            return str(e)

        target_date = _resolve_date(date_str)
        label = f"{resolved_city} on {target_date} ({schedule.timezone_name})"
        times = schedule.as_dict()
        lines = [f"Prayer times for {label}:"] + [
            f"  {name}: {time}" for name, time in times.items()
        ]
        return "\n".join(lines)
