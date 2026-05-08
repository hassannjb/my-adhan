"""
Pure prayer-time calculation — no side effects, no I/O, no state.

Takes inputs, returns a PrayerSchedule.  Can be called with any city's
coordinates, making it usable from the GUI, the daemon, and the chatbot.
"""
from __future__ import annotations

from datetime import date

import pytz
from adhanpy.PrayerTimes import PrayerTimes
from adhanpy.calculation.CalculationMethod import CalculationMethod
from adhanpy.calculation.CalculationParameters import CalculationParameters

from adhan.models import Config, Coordinates, PrayerSchedule


def build_params(config: Config) -> CalculationParameters:
    method = getattr(CalculationMethod, config.method, CalculationMethod.NORTH_AMERICA)
    return CalculationParameters(
        method=method,
        fajr_angle=config.fajr_angle,
        isha_angle=config.isha_angle,
    )


def calculate(
    target_date: date,
    coords: Coordinates,
    params: CalculationParameters,
    tz: pytz.BaseTzInfo,
) -> PrayerSchedule:
    """
    Calculate prayer times for a given date, location, and parameters.
    All times in the returned PrayerSchedule are in the given timezone.
    """
    pt = PrayerTimes(
        (coords.latitude, coords.longitude),
        target_date,
        calculation_parameters=params,
        time_zone=tz,
    )

    def _local(t) -> date:
        return t.astimezone(tz)

    return PrayerSchedule(
        date=target_date,
        fajr=_local(pt.fajr),
        sunrise=_local(pt.sunrise),
        dhuhr=_local(pt.dhuhr),
        asr=_local(pt.asr),
        maghrib=_local(pt.maghrib),
        isha=_local(pt.isha),
        timezone_name=tz.zone,
    )
