"""
PrayerClock — stateful orchestrator for the local machine's prayer schedule.

Knows YOUR location (via IP detection) and YOUR config.  For calculating
prayer times for arbitrary cities, use services.prayer_service.PrayerService.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

import pytz

from adhan.calculator import build_params, calculate
from adhan.config import DEFAULT_CONFIG_PATH, load_config, save_config
from adhan.location import get_current_location
from adhan.models import Config, Coordinates, PrayerSchedule
from adhan.notifications import play_adhan, send_notification

logger = logging.getLogger(__name__)

_LIB = Path(__file__).parent.parent / "lib"
_FAJR_AUDIO  = _LIB / "fajr.mp3"
_ADHAN_AUDIO = _LIB / "makkah_adhan.mp3"


class PrayerClock:
    """
    Stateful service that owns the current location + config and vends
    PrayerSchedule objects for any date.

    Lifecycle:
        clock = PrayerClock()           # loads config, detects location
        clock.refresh_settings()        # reload config + re-detect location
        schedule = clock.get_prayer_times(date.today())
        clock.play_adhan()
    """

    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH) -> None:
        self.config_path = config_path
        self._config: Config = Config()
        self._coords: Coordinates = Coordinates(0.0, 0.0)
        self._tz: pytz.BaseTzInfo = pytz.UTC
        self.refresh_settings()

    # ── Public properties ─────────────────────────────────────────────────────

    @property
    def config(self) -> Config:
        return self._config

    @property
    def timezone(self) -> pytz.BaseTzInfo:
        return self._tz

    # ── Core methods ──────────────────────────────────────────────────────────

    def refresh_settings(self) -> None:
        """Reload config from disk and re-detect location via IP geolocation."""
        self._config = load_config(self.config_path)
        coords, tz, city = get_current_location()
        self._coords = coords
        self._tz = tz
        self._config.city = city
        self._config.latitude = coords.latitude
        self._config.longitude = coords.longitude
        self._config.timezone = tz.zone
        logger.debug("Settings refreshed: city=%s tz=%s", city, tz.zone)

    def get_current_time(self) -> datetime:
        return datetime.now(self._tz)

    def get_prayer_times(self, target_date: date) -> PrayerSchedule:
        params = build_params(self._config)
        return calculate(target_date, self._coords, params, self._tz)

    def play_adhan(self, prayer_name: str = "") -> None:
        send_notification("Adhaan Clock", "Time for Prayer")
        audio = _FAJR_AUDIO if prayer_name.lower() == "fajr" else _ADHAN_AUDIO
        play_adhan(audio)
