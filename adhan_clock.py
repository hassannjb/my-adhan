import json
import time
from datetime import date, datetime, timedelta
import pytz
from adhanpy.calculation.CalculationParameters import CalculationParameters
from adhanpy.calculation.CalculationMethod import CalculationMethod
from adhanpy.PrayerTimes import PrayerTimes
import pygame

# 1. Load Configuration
with open('config.json') as f:
    config = json.load(f)

# Coordinate Handling
try:
    lat = float(config['latitude'])
    lng = float(config['longitude'])
    raw_coordinates = (lat, lng)
except ValueError:
    print("Error: Latitude and Longitude in config.json must be numbers.")
    exit(1)

timezone = pytz.timezone(config['timezone'])

# 2. Setup Calculation Parameters
params = CalculationParameters(
    method=CalculationMethod.NORTH_AMERICA,
    fajr_angle=config['fajr_angle'],
    isha_angle=config['isha_angle']
)


def get_times(target_date):
    return PrayerTimes(
        raw_coordinates,
        target_date,
        calculation_parameters=params,
        time_zone=timezone
    )


def play_adhan():
    print("Playing Adhaan...")
    try:
        pygame.mixer.init()
        pygame.mixer.music.load('makkah_adhan.mp3')
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(1)
    except Exception as e:
        print(f"Error playing sound: {e}")


# --- UPDATED: Function prints schedule for specific date range ---
def print_schedule(reference_date):
    print("-" * 30)
    print(f"PRAYER SCHEDULE FOR {reference_date}")
    print("-" * 30)

    days_to_print = [
        ("YESTERDAY", reference_date - timedelta(days=1)),
        ("TODAY    ", reference_date),
        ("TOMORROW ", reference_date + timedelta(days=1))
    ]

    for label, day in days_to_print:
        pt = get_times(day)
        print(f"{label} ({day}):")
        print(f"  Fajr:    {pt.fajr.strftime('%H:%M')}")
        print(f"  Dhuhr:   {pt.dhuhr.strftime('%H:%M')}")
        print(f"  Asr:     {pt.asr.strftime('%H:%M')}")
        print(f"  Maghrib: {pt.maghrib.strftime('%H:%M')}")
        print(f"  Isha:    {pt.isha.strftime('%H:%M')}")
        print("-" * 30)


# ----------------------------------------------------------------

def main():
    # Initial print on startup
    print_schedule(date.today())
    print("Clock loop started. Press Ctrl+C to stop.")

    # Track the last date we printed to detect midnight
    last_printed_date = date.today()

    while True:
        now = datetime.now(timezone)
        today = now.date()

        # --- NEW: Check if it is a new day ---
        if today > last_printed_date:
            print_schedule(today)
            last_printed_date = today
        # -------------------------------------

        pt = get_times(today)

        prayers = [
            ("Fajr", pt.fajr),
            ("Dhuhr", pt.dhuhr),
            ("Asr", pt.asr),
            ("Maghrib", pt.maghrib),
            ("Isha", pt.isha)
        ]

        for name, p_time in prayers:
            # Check if current time is within 30 seconds of prayer time
            if abs((p_time - now).total_seconds()) < 30:
                print(f"Time for {name}!")
                play_adhan()
                time.sleep(120)
                break

        time.sleep(10)


if __name__ == "__main__":
    main()