"""
Domain models — pure Python dataclasses, no I/O, no external deps.
These are the nouns of the application.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass(frozen=True)
class Coordinates:
    latitude: float
    longitude: float

    def __str__(self) -> str:
        return f"{self.latitude:.4f}, {self.longitude:.4f}"


@dataclass
class Config:
    """Mutable settings read from config.json."""
    fajr_angle: float = 15.0
    isha_angle: float = 15.0
    method: str = "NORTH_AMERICA"
    city: str = "Unknown"
    latitude: float = 0.0
    longitude: float = 0.0
    timezone: str = "UTC"

    def to_dict(self) -> dict:
        return {
            "fajr_angle": self.fajr_angle,
            "isha_angle": self.isha_angle,
            "method": self.method,
            "city": self.city,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timezone": self.timezone,
        }


@dataclass(frozen=True)
class PrayerSchedule:
    """
    All prayer times for a single day, already converted to the local timezone.

    All datetime attributes are timezone-aware and ready to display — no
    .astimezone() calls needed by consumers.
    """
    date: date
    fajr: datetime
    sunrise: datetime
    dhuhr: datetime
    asr: datetime
    maghrib: datetime
    isha: datetime
    timezone_name: str

    def next_after(self, now: datetime) -> Optional[tuple[str, datetime]]:
        """Return (prayer_name, time) for the next prayer after `now`, or None."""
        for name, dt in [
            ("Fajr", self.fajr),
            ("Dhuhr", self.dhuhr),
            ("Asr", self.asr),
            ("Maghrib", self.maghrib),
            ("Isha", self.isha),
        ]:
            if dt > now:
                return name, dt
        return None

    def as_dict(self) -> dict[str, str]:
        """Return prayer times as HH:MM strings keyed by prayer name."""
        return {
            "Fajr": self.fajr.strftime("%H:%M"),
            "Sunrise": self.sunrise.strftime("%H:%M"),
            "Dhuhr": self.dhuhr.strftime("%H:%M"),
            "Asr": self.asr.strftime("%H:%M"),
            "Maghrib": self.maghrib.strftime("%H:%M"),
            "Isha": self.isha.strftime("%H:%M"),
        }
