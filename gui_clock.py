import sys
import json
import requests
from pathlib import Path
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QGridLayout, QGroupBox, QPushButton,
                             QSizePolicy, QLineEdit, QTextEdit)
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal
from prayer_engine import PrayerClock
from gui.settings import SettingsDialog
from utils.display_helper import format_date_display, format_countdown


def get_location_details():
    try:
        response = requests.get('http://ip-api.com/json/').json()
        if response.get('status') == 'success':
            return response.get('city', 'Unknown'), response.get('timezone', 'UTC')
        else:
            return "Unknown", "UTC"
    except:
        return "Offline", "UTC"


# ── RAG background worker ─────────────────────────────────────────────────────
#
# WHY A SEPARATE THREAD?
#   Qt runs everything on the "main thread" — the same thread that draws the UI
#   and processes mouse/keyboard events.  If you do a network call there, the
#   entire window freezes until it completes.  QThread moves the work off the
#   main thread.  The UI stays responsive while Claude streams tokens in the
#   background.
#
# WHY SIGNALS?
#   Threads can't safely touch UI widgets directly — Qt's rendering isn't
#   thread-safe.  Signals are the safe bridge: emit from the worker thread,
#   Qt queues the call, the main thread executes the slot.  This is the
#   Qt signal/slot pattern — the same mechanism used for button clicks.

class _RagWorker(QThread):
    token = pyqtSignal(str)    # fired for each streamed text token
    finished = pyqtSignal()    # fired when the full answer has been streamed
    error = pyqtSignal(str)    # fired if anything goes wrong

    def __init__(self, question, answer_stream_fn, records, matrix, voyage, claude):
        super().__init__()
        self._question = question
        self._fn = answer_stream_fn
        self._records = records
        self._matrix = matrix
        self._voyage = voyage
        self._claude = claude

    def run(self):
        try:
            stream, _ = self._fn(
                self._question, self._records, self._matrix,
                self._voyage, self._claude
            )
            for tok in stream:
                self.token.emit(tok)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


# ── Main UI ───────────────────────────────────────────────────────────────────

class AdhanClockUI(QWidget):
    def __init__(self, clock=None):
        super().__init__()
        self.setWindowTitle("Adhan Clock")
        self.setGeometry(100, 100, 450, 900)
        self.clock = clock or PrayerClock()
        self.setStyleSheet("background-color: #2b2b2b; color: #ffffff; font-family: sans-serif;")
        self.prayer_labels = {}
        self.sunrise_label = None
        self._rag_worker = None
        self.init_ui()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_display)
        self.timer.start(1000)
        self.refresh_location()
        self._init_rag()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(50, 50, 50, 50)
        layout.setAlignment(Qt.AlignCenter)
        self.date_label = QLabel("Loading Date...")
        self.date_label.setAlignment(Qt.AlignCenter)
        self.date_label.setStyleSheet("color: #aaaaaa; font-size: 18px;")
        layout.addWidget(self.date_label)
        self.time_label = QLabel("00:00:00")
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setStyleSheet("font-weight: bold; color: #ffffff; font-size: 48px;")
        layout.addWidget(self.time_label)
        self.location_label = QLabel("Detecting Location...")
        self.location_label.setAlignment(Qt.AlignCenter)
        self.location_label.setStyleSheet("color: #888888; font-size: 16px;")
        layout.addWidget(self.location_label)
        self.countdown_label = QLabel("Next Prayer in...")
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.setStyleSheet("color: #3498db; font-weight: bold; font-size: 20px; padding: 10px;")
        layout.addWidget(self.countdown_label)
        layout.addStretch(1)
        prayer_group = QGroupBox("Today's Times")
        prayer_group.setStyleSheet("color: white; border: 1px solid #555555; border-radius: 5px; padding: 10px; font-size: 14px;")
        prayer_group.setMinimumHeight(250)
        prayer_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        prayer_layout = QGridLayout()
        prayer_layout.setAlignment(Qt.AlignCenter)
        prayer_layout.setSpacing(10)
        prayers = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]
        for i, prayer in enumerate(prayers):
            name_lbl = QLabel(prayer)
            name_lbl.setStyleSheet("font-weight: bold; color: #aaaaaa; font-size: 16px;")
            name_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            time_lbl = QLabel("--:--")
            time_lbl.setStyleSheet("color: #ffffff; font-size: 16px;")
            time_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            prayer_layout.addWidget(name_lbl, i, 0)
            prayer_layout.addWidget(time_lbl, i, 1)
            if prayer == "Sunrise":
                self.sunrise_label = time_lbl
            else:
                self.prayer_labels[prayer] = time_lbl
        prayer_group.setLayout(prayer_layout)
        layout.addWidget(prayer_group)
        layout.addStretch(1)
        self.settings_button = QPushButton("Edit Settings")
        self.settings_button.setStyleSheet("background-color: #555555; color: white; padding: 10px; border-radius: 5px; font-size: 16px;")
        self.settings_button.clicked.connect(self.open_settings)
        layout.addWidget(self.settings_button)
        self.refresh_button = QPushButton("Refresh Location / Times")
        self.refresh_button.setStyleSheet("background-color: #34495e; color: white; padding: 10px; border-radius: 5px; font-size: 16px;")
        self.refresh_button.clicked.connect(self.refresh_location)
        layout.addWidget(self.refresh_button)

        # ── Ask a Question (RAG) ──────────────────────────────────────────────
        rag_group = QGroupBox("Ask a Question")
        rag_group.setStyleSheet("color: white; border: 1px solid #3d5a80; border-radius: 5px; padding: 10px; font-size: 14px;")
        rag_layout = QVBoxLayout()
        rag_layout.setSpacing(8)

        input_row = QHBoxLayout()
        self.rag_input = QLineEdit()
        self.rag_input.setPlaceholderText("e.g. What time does Fajr start?")
        self.rag_input.setStyleSheet("background-color: #3a3a3a; color: white; border: 1px solid #555; border-radius: 4px; padding: 6px; font-size: 14px;")
        self.rag_input.returnPressed.connect(self._ask_question)
        input_row.addWidget(self.rag_input)

        self.rag_ask_btn = QPushButton("Ask")
        self.rag_ask_btn.setStyleSheet("background-color: #3d5a80; color: white; padding: 6px 14px; border-radius: 4px; font-size: 14px;")
        self.rag_ask_btn.clicked.connect(self._ask_question)
        input_row.addWidget(self.rag_ask_btn)
        rag_layout.addLayout(input_row)

        self.rag_answer = QTextEdit()
        self.rag_answer.setReadOnly(True)
        self.rag_answer.setPlaceholderText("Answer will appear here...")
        self.rag_answer.setStyleSheet("background-color: #1e1e1e; color: #cccccc; border: 1px solid #444; border-radius: 4px; padding: 6px; font-size: 13px;")
        self.rag_answer.setMinimumHeight(100)
        self.rag_answer.setMaximumHeight(160)
        rag_layout.addWidget(self.rag_answer)

        rag_group.setLayout(rag_layout)
        layout.addWidget(rag_group)
        # ─────────────────────────────────────────────────────────────────────

        self.setLayout(layout)

    def _init_rag(self):
        """Lazily load the RAG index and API clients. Fails silently if not configured."""
        self._rag_ready = False
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from rag.query import answer_stream, load_index, load_clients, INDEX_PATH
            if not INDEX_PATH.exists():
                self.rag_answer.setPlaceholderText(
                    "RAG index not found. Run: python rag/ingest.py"
                )
                return
            self._rag_records, self._rag_matrix = load_index(INDEX_PATH)
            self._rag_voyage, self._rag_claude = load_clients()
            self._answer_stream_fn = answer_stream
            self._rag_ready = True
            self.rag_answer.setPlaceholderText(
                f"Ready — {len(self._rag_records)} chunks indexed. Ask anything."
            )
        except (Exception, SystemExit) as e:
            self.rag_answer.setPlaceholderText(f"RAG unavailable: {e}")

    def _ask_question(self):
        if not self._rag_ready:
            self.rag_answer.setPlainText(self.rag_answer.placeholderText())
            return
        question = self.rag_input.text().strip()
        if not question:
            return
        if self._rag_worker and self._rag_worker.isRunning():
            return

        self.rag_answer.setPlainText("")
        self.rag_ask_btn.setEnabled(False)
        self.rag_input.setEnabled(False)

        self._rag_worker = _RagWorker(
            question, self._answer_stream_fn,
            self._rag_records, self._rag_matrix,
            self._rag_voyage, self._rag_claude,
        )
        self._rag_worker.token.connect(self._on_rag_token)
        self._rag_worker.finished.connect(self._on_rag_done)
        self._rag_worker.error.connect(self._on_rag_error)
        self._rag_worker.start()

    def _on_rag_token(self, token: str):
        self.rag_answer.insertPlainText(token)
        self.rag_answer.ensureCursorVisible()

    def _on_rag_done(self):
        self.rag_ask_btn.setEnabled(True)
        self.rag_input.setEnabled(True)
        self.rag_input.clear()

    def _on_rag_error(self, msg: str):
        self.rag_answer.setPlainText(f"Error: {msg}")
        self.rag_ask_btn.setEnabled(True)
        self.rag_input.setEnabled(True)

    def open_settings(self):
        with open(self.clock.config_path, 'r') as f:
            current_conf = json.load(f)
        dialog = SettingsDialog(current_conf, self)
        if dialog.exec():
            with open(self.clock.config_path, 'w') as f:
                json.dump(dialog.config, f, indent=4)
            self.refresh_location()

    def refresh_location(self):
        self.location_label.setText("Refreshing...")
        self.clock.refresh_settings()
        self.location_label.setText(f"{self.clock.config.get('city', 'Unknown')} | {self.clock.timezone}")
        self.update_display()

    def update_display(self):
        now = self.clock.get_current_time()
        self.time_label.setText(now.strftime("%H:%M:%S"))
        self.date_label.setText(format_date_display(now.date()))
        pt = self.clock.get_prayer_times(now.date())
        if not pt: return
        times = {
            "Fajr": pt.fajr.astimezone(self.clock.timezone),
            "Sunrise": pt.sunrise.astimezone(self.clock.timezone),
            "Dhuhr": pt.dhuhr.astimezone(self.clock.timezone),
            "Asr": pt.asr.astimezone(self.clock.timezone),
            "Maghrib": pt.maghrib.astimezone(self.clock.timezone),
            "Isha": pt.isha.astimezone(self.clock.timezone)
        }
        next_prayer = None
        self.sunrise_label.setText(times["Sunrise"].strftime("%H:%M"))
        for prayer, lbl in self.prayer_labels.items():
            p_time = times[prayer]
            lbl.setText(p_time.strftime("%H:%M"))
            if p_time > now and next_prayer is None:
                next_prayer = (prayer, p_time)
        if next_prayer:
            self.countdown_label.setText(f"{next_prayer[0]} in {format_countdown(next_prayer[1] - now)}")
        elif not hasattr(sys.modules['__main__'], '_test_clock'):
            self.countdown_label.setText("All prayers done for today.")

    def resizeEvent(self, event):
        new_width = self.width()
        self.date_label.setStyleSheet(f"font-size: {max(16, new_width // 25)}px; color: #aaaaaa;")
        self.time_label.setStyleSheet(f"font-size: {max(30, new_width // 10)}px; font-weight: bold; color: #ffffff;")
        self.location_label.setStyleSheet(f"font-size: {max(12, new_width // 35)}px; color: #888888;")
        self.countdown_label.setStyleSheet(f"font-size: {max(18, new_width // 20)}px; color: #3498db; font-weight: bold; padding: 5px;")
        for lbl in list(self.prayer_labels.values()) + [self.sunrise_label]:
            lbl.setStyleSheet(f"font-size: {max(10, new_width // 55)}px; color: #ffffff;")
        super().resizeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AdhanClockUI()
    window.show()
    sys.exit(app.exec())
