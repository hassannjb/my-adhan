"""
Entry point for the headless Adhan Clock daemon.

    python adhan_clock.py

Runs continuously, printing the prayer schedule and playing adhan
at each prayer time.  No GUI required.
"""
import logging
import time
from datetime import date, timedelta

from adhan import PrayerClock
from utils.display_helper import format_prayer_times

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_ADHAN_COOLDOWN = 120   # seconds to sleep after playing adhan
_POLL_INTERVAL = 10     # seconds between prayer-time checks
_TRIGGER_WINDOW = 30    # seconds: fire adhan if within this window of prayer time


def _print_schedule(clock: PrayerClock, reference_date: date) -> None:
    print("-" * 30, flush=True)
    print(f"PRAYER SCHEDULE FOR {reference_date}", flush=True)
    print("-" * 30, flush=True)
    for label, delta in [("YESTERDAY", -1), ("TODAY    ", 0), ("TOMORROW ", 1)]:
        day = reference_date + timedelta(days=delta)
        pt = clock.get_prayer_times(day)
        print(f"{label} ({day}):", flush=True)
        for name, time_str in format_prayer_times(pt).items():
            print(f"  {name:<7}: {time_str}", flush=True)
        print("-" * 30, flush=True)


def run() -> None:
    clock = PrayerClock()
    _print_schedule(clock, date.today())
    clock.play_adhan()   # startup notification

    last_printed_date = date.today()
    logger.info("Clock loop started. Press Ctrl+C to stop.")

    while True:
        now = clock.get_current_time()
        today = now.date()

        if today > last_printed_date:
            _print_schedule(clock, today)
            last_printed_date = today

        pt = clock.get_prayer_times(today)
        for name in ("Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"):
            p_time = getattr(pt, name.lower())
            delta = abs((p_time.replace(tzinfo=None) - now.replace(tzinfo=None)).total_seconds())
            if delta < _TRIGGER_WINDOW:
                logger.info("Time for %s!", name)
                clock.play_adhan(name)
                time.sleep(_ADHAN_COOLDOWN)
                break

        time.sleep(_POLL_INTERVAL)


if __name__ == "__main__":
    run()
