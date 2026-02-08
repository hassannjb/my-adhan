import sys
import requests
import json  # --- IMPORTED JSON ---
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLabel,
                             QGridLayout, QGroupBox, QPushButton)
from PyQt6.QtCore import QTimer, Qt
from datetime import datetime
import pytz
# --- IMPORTING YOUR WORKING LOGIC ---
from adhan_clock import get_times
# --- IMPORTING SETTINGS DIALOG ---
from gui.settings import SettingsDialog


# ----------------------------

# --- Function to get location details from network ---
def get_location_details():
    try:
        response = requests.get('http://ip-api.com/json/').json()
        if response['status'] == 'success':
            return response['city'], response['timezone']
        else:
            return "Unknown", "UTC"
    except:
        return "Offline", "UTC"


# -----------------------------------------------------------

class AdhanClockUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Adhan Clock")
        self.setGeometry(100, 100, 350, 600)  # Increased height further
        self.config_path = 'config.json'  # Define config path
        # Clean Dark Theme
        self.setStyleSheet("background-color: #2b2b2b; color: #ffffff; font-family: sans-serif;")

        self.local_tz = None
        self.current_times = {}

        self.init_ui()

        # Timer to update the display
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_display)
        self.timer.start(1000)  # Update every second

        # Initial Location Fetch
        self.refresh_location()

    def init_ui(self):
        layout = QVBoxLayout()

        # --- UI Components ---
        self.date_label = QLabel("Loading Date...")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_label.setStyleSheet("font-size: 14px; color: #aaaaaa;")
        layout.addWidget(self.date_label)

        self.time_label = QLabel("00:00:00")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_label.setStyleSheet("font-size: 36px; font-weight: bold; color: #ffffff; padding: 10px;")
        layout.addWidget(self.time_label)

        self.location_label = QLabel("Detecting Location...")
        self.location_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.location_label.setStyleSheet("font-size: 12px; color: #888888; padding-bottom: 10px;")
        layout.addWidget(self.location_label)

        # Countdown Label
        self.countdown_label = QLabel("Next Prayer in...")
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.setStyleSheet("font-size: 16px; color: #3498db; font-weight: bold; padding: 5px;")
        layout.addWidget(self.countdown_label)

        # Prayer Times Layout
        prayer_group = QGroupBox("Today's Times")
        prayer_group.setStyleSheet("color: white; border: 1px solid #555555; border-radius: 5px; margin-top: 10px;")
        prayer_layout = QGridLayout()

        self.prayer_labels = {}
        prayers = ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]

        for i, prayer in enumerate(prayers):
            name_lbl = QLabel(prayer)
            name_lbl.setStyleSheet("font-weight: bold; color: #aaaaaa;")
            time_lbl = QLabel("--:--")
            time_lbl.setStyleSheet("font-size: 16px; color: #ffffff;")

            prayer_layout.addWidget(name_lbl, i, 0)
            prayer_layout.addWidget(time_lbl, i, 1)

            self.prayer_labels[prayer] = time_lbl

        prayer_group.setLayout(prayer_layout)
        layout.addWidget(prayer_group)

        # --- Settings Button ---
        self.settings_button = QPushButton("Edit Settings")
        self.settings_button.setStyleSheet("""
            QPushButton {
                background-color: #555555; 
                color: white; 
                padding: 8px; 
                margin-top: 10px; 
                border-radius: 4px;
            }
            QPushButton:pressed {
                background-color: #444444; 
            }
        """)
        self.settings_button.clicked.connect(self.open_settings)
        layout.addWidget(self.settings_button)
        # -----------------------

        # Refresh Button
        self.refresh_button = QPushButton("Refresh Location / Times")
        self.refresh_button.setStyleSheet("""
            QPushButton {
                background-color: #34495e; 
                color: white; 
                padding: 8px; 
                margin-top: 10px; 
                border-radius: 4px;
            }
            QPushButton:pressed {
                background-color: #2c3e50; 
            }
        """)
        self.refresh_button.clicked.connect(self.refresh_location)
        layout.addWidget(self.refresh_button)

        self.setLayout(layout)

    def open_settings(self):
        """Opens dialog to edit config.json"""
        with open(self.config_path, 'r') as f:
            current_conf = json.load(f)

        dialog = SettingsDialog(current_conf, self)
        if dialog.exec():
            with open(self.config_path, 'w') as f:
                json.dump(dialog.config, f, indent=4)
            print("Settings updated. Refreshing...")
            self.refresh_location()  # Recalculate with new settings

    def refresh_location(self):
        """Fetches new location and recalculates times"""
        self.location_label.setText("Refreshing...")
        city, timezone_str = get_location_details()
        self.local_tz = pytz.timezone(timezone_str)
        self.location_label.setText(f"{city} | {timezone_str}")
        self.update_display()  # Force immediate update

    def update_display(self):
        if not self.local_tz: return

        # Update current time and date
        now = datetime.now(self.local_tz)
        self.time_label.setText(now.strftime("%H:%M:%S"))
        self.date_label.setText(now.strftime("%A, %d %B %Y"))

        # Update today's prayers
        today = now.date()
        pt = get_times(today)

        self.current_times = {
            "Fajr": pt.fajr,
            "Dhuhr": pt.dhuhr,
            "Asr": pt.asr,
            "Maghrib": pt.maghrib,
            "Isha": pt.isha
        }

        # Update labels and find next prayer
        next_prayer = None
        for prayer, lbl in self.prayer_labels.items():
            p_time = self.current_times[prayer]
            lbl.setText(p_time.strftime("%H:%M"))

            if p_time > now and next_prayer is None:
                next_prayer = (prayer, p_time)

        # Update Countdown
        if next_prayer:
            time_left = next_prayer[1] - now
            minutes = int(time_left.total_seconds() // 60)
            seconds = int(time_left.total_seconds() % 60)
            self.countdown_label.setText(f"{next_prayer[0]} in {minutes}m {seconds}s")
        else:
            self.countdown_label.setText("All prayers done for today.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AdhanClockUI()
    window.show()
    sys.exit(app.exec())