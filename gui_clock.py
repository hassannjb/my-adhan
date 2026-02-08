import sys
import json
import requests
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QGridLayout, QGroupBox
from PyQt6.QtCore import QTimer, Qt
from datetime import datetime
import pytz
# --- IMPORTING YOUR BACKEND LOGIC ---
from adhan_clock import get_times, config


# ----------------------------

# --- NEW: Function to get location details from network ---
def get_location_details():
    try:
        response = requests.get('http://ip-api.com/json/').json()
        if response['status'] == 'success':
            return response['city'], response['timezone'], response['lat'], response['lon']
        else:
            return "Unknown", "UTC", 0.0, 0.0
    except:
        return "Offline", "UTC", 0.0, 0.0


# -----------------------------------------------------------

class AdhanClockUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Adhan Clock Dashboard")
        self.setGeometry(100, 100, 400, 480)

        layout = QVBoxLayout()

        # 1. Header Information (Date, Location, Timezone)
        header_group = QGroupBox("Information")
        header_layout = QVBoxLayout()

        self.date_label = QLabel(self)
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.date_label)

        # --- UPDATED: Display City instead of coordinates ---
        self.city_label = QLabel("Loc: Detecting...")
        self.city_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.city_label)

        self.tz_label = QLabel("TZ: Detecting...")
        self.tz_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.tz_label)
        # ----------------------------------------------------

        header_group.setLayout(header_layout)
        layout.addWidget(header_group)

        # 2. Current Time
        self.time_label = QLabel(self)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(self.time_label)

        # 3. Today's Prayers Table
        prayer_group = QGroupBox("Today's Schedule")
        prayer_layout = QGridLayout()

        self.prayer_times = {}
        prayers = ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]

        for i, prayer in enumerate(prayers):
            name_lbl = QLabel(prayer)
            time_lbl = QLabel("--:--")
            time_lbl.setStyleSheet("font-weight: bold;")

            prayer_layout.addWidget(name_lbl, i, 0)
            prayer_layout.addWidget(time_lbl, i, 1)

            self.prayer_times[prayer] = time_lbl

        prayer_group.setLayout(prayer_layout)
        layout.addWidget(prayer_group)

        self.setLayout(layout)

        # --- NEW: Fetch location once on startup ---
        self.city, self.timezone_str, self.lat, self.lng = get_location_details()
        self.city_label.setText(f"City: {self.city}")
        self.tz_label.setText(f"TZ: {self.timezone_str}")
        self.local_tz = pytz.timezone(self.timezone_str)
        # -------------------------------------------

        # Timer to update the display
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_display)
        self.timer.start(1000)  # Update every second

        self.update_display()

    def update_display(self):
        # Update current time and date
        now = datetime.now(self.local_tz)
        self.time_label.setText(now.strftime("%H:%M:%S"))
        self.date_label.setText(now.strftime("%A, %B %d, %Y"))

        # Update today's prayers using detected coordinates
        today = now.date()
        # Note: You might need to adjust adhan_clock.py to accept
        # coordinates directly in get_times() for this to work fully dynamically
        pt = get_times(today)

        times = {
            "Fajr": pt.fajr,
            "Dhuhr": pt.dhuhr,
            "Asr": pt.asr,
            "Maghrib": pt.maghrib,
            "Isha": pt.isha
        }

        for prayer, lbl in self.prayer_times.items():
            lbl.setText(times[prayer].strftime("%H:%M"))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AdhanClockUI()
    window.show()
    sys.exit(app.exec())