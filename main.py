import json
import os
from datetime import datetime, timedelta

# Default path for prayer times file
PRAYER_TIMES_FILE = "adhan_times.json"

class AdhanClockApp:
    """
    Core logic for the Adhan Clock application.
    Handles loading prayer times and determining the next prayer.
    The GUI (macOS 2014+) would interact with this class.
    """
    def __init__(self, prayer_times_filepath=None):
        """
        Initializes the Adhan Clock application.
        :param prayer_times_filepath: Optional path to the prayer times JSON file.
                                      Defaults to PRAYER_TIMES_FILE.
        """
        self.prayer_times_filepath = prayer_times_filepath if prayer_times_filepath else PRAYER_TIMES_FILE
        self.prayer_times = self._load_prayer_times()

    def _load_prayer_times(self):
        """
        Loads prayer times from the specified JSON file.
        Returns a dictionary of prayer times or None if loading fails.
        """
        filepath = self.prayer_times_filepath
        if not os.path.exists(filepath):
            print(f"Warning: Prayer times file not found at {filepath}")
            return None
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)

            # Basic validation: check if expected prayer names exist
            # This list can be expanded based on exact requirements.
            expected_prayers = ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]
            if all(p in data for p in expected_prayers):
                print(f"Prayer times loaded successfully from {filepath}")
                return data
            else:
                print(f"Warning: Malformed prayer times data in {filepath} (missing expected keys).")
                return None
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error reading or parsing prayer times from {filepath}: {e}")
            return None

    def get_next_prayer_info(self, current_dt: datetime):
        """
        Determines the next upcoming prayer based on the current datetime.
        Assumes prayer times are for the current day. If all prayers for today are passed,
        it suggests Fajr for the next day.
        
        :param current_dt: The current datetime object.
        :return: Tuple (prayer_name, prayer_time_str, prayer_datetime_obj) or
                 ("No prayer times loaded", None, None) if data is missing.
        """
        if not self.prayer_times:
            return "No prayer times loaded", None, None

        current_time_str = current_dt.strftime("%H:%M")
        today_date_str = current_dt.strftime("%Y-%m-%d")

        prayer_order = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Sunset", "Maghrib", "Isha"]
        prayer_dt_objects = {}

        # Convert prayer times strings to full datetime objects for comparison
        for prayer_name, time_str in self.prayer_times.items():
            try:
                prayer_dt_objects[prayer_name] = datetime.strptime(f"{today_date_str} {time_str}", "%Y-%m-%d %H:%M")
            except ValueError:
                print(f"Warning: Invalid time format for {prayer_name}: '{time_str}'")
                continue # Skip invalid time formats

        next_prayer_name = None
        next_prayer_dt = None

        # Find the next prayer for today
        for prayer in prayer_order:
            if prayer in prayer_dt_objects and prayer_dt_objects[prayer] > current_dt:
                next_prayer_name = prayer
                next_prayer_dt = prayer_dt_objects[prayer]
                break

        # If no prayer left for today, set next prayer to Fajr of tomorrow
        if next_prayer_name is None and "Fajr" in self.prayer_times:
            next_day = current_dt + timedelta(days=1)
            next_day_date_str = next_day.strftime("%Y-%m-%d")
            next_day_fajr_time_str = self.prayer_times["Fajr"]
            try:
                next_day_fajr_dt = datetime.strptime(
                    f"{next_day_date_str} {next_day_fajr_time_str}",
                    "%Y-%m-%d %H:%M"
                )
                return "Fajr (Tomorrow)", self.prayer_times["Fajr"], next_day_fajr_dt
            except ValueError:
                print(f"Warning: Invalid Fajr time format for tomorrow: '{next_day_fajr_time_str}'")
                pass # Fallback to default message if tomorrow's Fajr is malformed

        if next_prayer_name and next_prayer_dt:
            return next_prayer_name, self.prayer_times[next_prayer_name], next_prayer_dt
        else:
            return "All prayers done for today", None, None # Fallback message

    def format_time_display(self, prayer_name, time_str):
        """
        Formats a prayer name and time for display.
        :param prayer_name: The name of the prayer (e.g., "Fajr").
        :param time_str: The time string (e.g., "05:00").
        :return: A formatted string.
        """
        if time_str:
            return f"{prayer_name}: {time_str}"
        return f"{prayer_name}: N/A"

    def run_gui(self):
        """
        This method would contain the macOS GUI application loop.
        For demonstration, we'll just print current status.
        In a real app, this would use a GUI toolkit (e.g., PyObjC, Tkinter).
        """
        print("Starting Adhan Clock GUI...")
        current_time = datetime.now()
        name, time, dt = self.get_next_prayer_info(current_time)
        print(f"Current time: {current_time.strftime('%H:%M:%S')}")
        print(f"Next Prayer: {name} at {time if time else 'N/A'}")
        # Here would be the actual GUI loop, e.g., using AppKit for macOS
        # For a simple console demo, we just show once.
        print("GUI application logic would continue here...")


if __name__ == "__main__":
    # Example of how the app would be run
    app = AdhanClockApp()
    app.run_gui()
