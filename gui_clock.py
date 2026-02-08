import sys
import requests
import json
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLabel,
                             QGridLayout, QGroupBox, QPushButton, QSizePolicy)
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
        self.setGeometry(100, 100, 450, 700)
        self.config_path = 'config.json'
        self.setStyleSheet("background-color: #2b2b2b; color: #ffffff; font-family: sans-serif;")

        self.local_tz = None
        # --- FIX: Initialize prayer_labels here to ensure it exists ---
        self.prayer_labels = {}

        self.init_ui()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_display)
        self.timer.start(1000)

        self.refresh_location()

    def init_ui(self):
        layout = QVBoxLayout()
        # Adjusted margins to keep things centered but not too far apart
        layout.setContentsMargins(50, 50, 50, 50)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # UI Components
        self.date_label = QLabel("Loading Date...")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_label.setStyleSheet("color: #aaaaaa; font-size: 18px;")
        layout.addWidget(self.date_label)

        self.time_label = QLabel("00:00:00")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_label.setStyleSheet("font-weight: bold; color: #ffffff; font-size: 48px;")
        layout.addWidget(self.time_label)

        self.location_label = QLabel("Detecting Location...")
        self.location_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.location_label.setStyleSheet("color: #888888; font-size: 16px;")
        layout.addWidget(self.location_label)

        # Countdown Label
        self.countdown_label = QLabel("Next Prayer in...")
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.setStyleSheet("color: #3498db; font-weight: bold; font-size: 20px; padding: 10px;")
        layout.addWidget(self.countdown_label)

        layout.addStretch(1)

        # Prayer Times Layout
        prayer_group = QGroupBox("Today's Times")
        prayer_group.setStyleSheet(
            "color: white; border: 1px solid #555555; border-radius: 5px; padding: 10px; font-size: 14px;")

        # --- FIX: Ensure the box has a minimum size ---
        prayer_group.setMinimumHeight(200)
        prayer_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        prayer_layout = QGridLayout()
        prayer_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prayer_layout.setSpacing(10)

        self.prayer_labels = {}
        prayers = ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]

        for i, prayer in enumerate(prayers):
            name_lbl = QLabel(prayer)
            name_lbl.setStyleSheet("font-weight: bold; color: #aaaaaa; font-size: 16px;")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            time_lbl = QLabel("--:--")
            time_lbl.setStyleSheet("color: #ffffff; font-size: 16px;")
            time_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

            prayer_layout.addWidget(name_lbl, i, 0)
            prayer_layout.addWidget(time_lbl, i, 1)

            self.prayer_labels[prayer] = time_lbl

        prayer_group.setLayout(prayer_layout)
        layout.addWidget(prayer_group)

        layout.addStretch(1)

        # Settings Button
        self.settings_button = QPushButton("Edit Settings")
        self.settings_button.setStyleSheet(
            "background-color: #555555; color: white; padding: 10px; border-radius: 5px; font-size: 16px;")
        self.settings_button.clicked.connect(self.open_settings)
        layout.addWidget(self.settings_button)

        # Refresh Button
        self.refresh_button = QPushButton("Refresh Location / Times")
        self.refresh_button.setStyleSheet(
            "background-color: #34495e; color: white; padding: 10px; border-radius: 5px; font-size: 16px;")
        self.refresh_button.clicked.connect(self.refresh_location)
        layout.addWidget(self.refresh_button)

        self.setLayout(layout)

    def open_settings(self):
        with open(self.config_path, 'r') as f:
            current_conf = json.load(f)
        dialog = SettingsDialog(current_conf, self)
        if dialog.exec():
            with open(self.config_path, 'w') as f:
                json.dump(dialog.config, f, indent=4)
            self.refresh_location()

    def refresh_location(self):
        self.location_label.setText("Refreshing...")
        city, timezone_str = get_location_details()
        self.local_tz = pytz.timezone(timezone_str)
        self.location_label.setText(f"{city} | {timezone_str}")
        self.update_display()

    def update_display(self):
        if not self.local_tz: return

        # 1. Update current time and date
        now = datetime.now(self.local_tz)
        self.time_label.setText(now.strftime("%H:%M:%S"))
        self.date_label.setText(now.strftime("%A, %d %B %Y"))

        # 2. Get times
        today = now.date()
        pt = get_times(today)

        if not pt: return

        # 3. Ensure all times are in the correct timezone
        times = {
            "Fajr": pt.fajr.astimezone(self.local_tz),
            "Dhuhr": pt.dhuhr.astimezone(self.local_tz),
            "Asr": pt.asr.astimezone(self.local_tz),
            "Maghrib": pt.maghrib.astimezone(self.local_tz),
            "Isha": pt.isha.astimezone(self.local_tz)
        }

        # 4. Update labels and find next prayer
        next_prayer = None
        for prayer, lbl in self.prayer_labels.items():
            p_time = times[prayer]
            new_text = p_time.strftime("%H:%M")

            # --- FIX: Only update if text has changed to prevent flicker ---
            if lbl.text() != new_text:
                lbl.setText(new_text)
                lbl.repaint()  # --- FIX: Force repaint of label ---

            if p_time > now and next_prayer is None:
                next_prayer = (prayer, p_time)

        # --- FIX: Force application to process events ---
        QApplication.processEvents()

        # 5. Update Countdown
        if next_prayer:
            time_left = next_prayer[1] - now
            total_seconds = int(time_left.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60

            if hours > 0:
                self.countdown_label.setText(f"{next_prayer[0]} in {hours}h {minutes}m {seconds}s")
            else:
                self.countdown_label.setText(f"{next_prayer[0]} in {minutes}m {seconds}s")
        else:
            self.countdown_label.setText("All prayers done for today.")

    def resizeEvent(self, event):
        """Scales fonts based on window size"""
        new_width = self.width()

        # Calculate font sizes based on window width
        # Main text (Date)
        main_font_size = max(16, new_width // 25)
        # Large clock
        time_font_size = max(30, new_width // 10)
        # Smallest text (Location)
        small_font_size = max(12, new_width // 35)
        # Next prayer countdown
        countdown_font_size = max(18, new_width // 20)

        # --- FIX: Divisor increased from 45 to 55 to make text smaller ---
        prayer_font_size = max(10, new_width // 55)

        # Update Stylesheets
        self.date_label.setStyleSheet(f"font-size: {main_font_size}px; color: #aaaaaa;")
        self.time_label.setStyleSheet(f"font-size: {time_font_size}px; font-weight: bold; color: #ffffff;")
        self.location_label.setStyleSheet(f"font-size: {small_font_size}px; color: #888888;")
        self.countdown_label.setStyleSheet(
            f"font-size: {countdown_font_size}px; color: #3498db; font-weight: bold; padding: 5px;")

        # Update prayer list fonts inside the dictionary
        for lbl in self.prayer_labels.values():
            lbl.setStyleSheet(f"font-size: {prayer_font_size}px; color: #ffffff;")

        super().resizeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AdhanClockUI()
    window.show()
    sys.exit(app.exec())