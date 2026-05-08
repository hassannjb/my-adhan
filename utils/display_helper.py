from datetime import datetime, date
from hijridate import Gregorian

def format_prayer_times(pt):
    return {
        "Fajr": pt.fajr.strftime('%H:%M'),
        "Dhuhr": pt.dhuhr.strftime('%H:%M'),
        "Asr": pt.asr.strftime('%H:%M'),
        "Maghrib": pt.maghrib.strftime('%H:%M'),
        "Isha": pt.isha.strftime('%H:%M')
    }

def format_date_display(d: date):
    hdate = Gregorian(d.year, d.month, d.day)
    return f"{d.strftime('%A, %d %B %Y')} | {hdate.day} {hdate.month_name()} {hdate.year} AH"

def format_countdown(time_left):
    total_seconds = int(time_left.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    return f"{minutes}m {seconds}s"
