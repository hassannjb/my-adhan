"""
adhan — core domain package for the Adhan Clock application.

Public API:
    PrayerClock     stateful service for the local machine's prayer schedule
    PrayerSchedule  value object: prayer times for one day
    Config          application settings
    Coordinates     latitude/longitude pair
"""
from adhan.clock import PrayerClock
from adhan.models import Config, Coordinates, PrayerSchedule

__all__ = ["PrayerClock", "PrayerSchedule", "Config", "Coordinates"]
