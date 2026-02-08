import json
import time
from datetime import date, datetime, timedelta

from mac_notifications import client
import pygame
import pytz
from adhanpy.PrayerTimes import PrayerTimes
from adhanpy.calculation.CalculationMethod import CalculationMethod
from adhanpy.calculation.CalculationParameters import CalculationParameters

# 1. Load Configuration
with open('config.json') as f:
    config = json.load(f)


# --- UPDATED: Dynamic Location Logic (No hardcoded values) ---
# --- UPDATED: Dynamic Location Logic (Requires sudo) ---
import requests  # NEW IMPORT


# --- UPDATED: Dynamic Location Logic (Network Based) ---
def get_location_from_system():
    """Uses IP Geolocation to get coordinates."""
    print("Detecting location from network...", flush=True)
    try:
        # Query free IP API
        response = requests.get('http://ip-api.com/json/').json()

        if response['status'] == 'success':
            lat = response['lat']
            lng = response['lon']
            timezone_str = response['timezone']

            print(f"Detected Timezone: {timezone_str}", flush=True)
            print(f"Detected Coordinates: {lat}, {lng}", flush=True)

            return (lat, lng), pytz.timezone(timezone_str)
        else:
            raise Exception("IP API lookup failed")

    except Exception as e:
        print(f"Error detecting location: {e}", flush=True)
        # Fallback to configured in file
        return (float(config['latitude']), float(config['longitude'])), pytz.timezone(config['timezone'])


# -------------------------------------------------------------

# Determine coordinates and timezone dynamically
raw_coordinates, timezone = get_location_from_system()
# -------------------------------------------------------------

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
    # UPDATED: Added flush=True
    print("Playing Adhaan", flush=True)
    client.create_notification(
        title="Adhaan Clock",
        subtitle="Time for Prayer",
        sound="default"
    )
    try:
        pygame.mixer.init()
        pygame.mixer.music.load('makkah_adhan.mp3')
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(1)
    except Exception as e:
        # UPDATED: Added flush=True
        print(f"Error playing sound: {e}", flush=True)


# --- UPDATED: Function prints schedule for specific date range ---
def print_schedule(reference_date):
    # UPDATED: Added flush=True
    print("-" * 30, flush=True)
    print(f"PRAYER SCHEDULE FOR {reference_date}", flush=True)
    print("-" * 30, flush=True)

    days_to_print = [
        ("YESTERDAY", reference_date - timedelta(days=1)),
        ("TODAY    ", reference_date),
        ("TOMORROW ", reference_date + timedelta(days=1))
    ]

    for label, day in days_to_print:
        pt = get_times(day)
        # UPDATED: Added flush=True
        print(f"{label} ({day}):", flush=True)
        print(f"  Fajr:    {pt.fajr.strftime('%H:%M')}", flush=True)
        print(f"  Dhuhr:   {pt.dhuhr.strftime('%H:%M')}", flush=True)
        print(f"  Asr:     {pt.asr.strftime('%H:%M')}", flush=True)
        print(f"  Maghrib: {pt.maghrib.strftime('%H:%M')}", flush=True)
        print(f"  Isha:    {pt.isha.strftime('%H:%M')}", flush=True)
        print("-" * 30, flush=True)


# ----------------------------------------------------------------

def main():
    # Initial print on startup
    print_schedule(date.today())
    # UPDATED: Added flush=True
    client.create_notification(
        title="Adhaan Clock Started",
        subtitle="Prayer times loaded successfully.",
        sound="default"
    )
    print("Clock loop started. Press Ctrl+C to stop.", flush=True)

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
                # UPDATED: Added flush=True
                print(f"Time for {name}!", flush=True)
                play_adhan()
                time.sleep(120)
                break

        time.sleep(10)


if __name__ == "__main__":
    main()
