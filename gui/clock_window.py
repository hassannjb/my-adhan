"""
AdhanClockUI — the main PyQt5 window.

GUI concerns only: layout, display updates, user events.
All business logic is delegated to adhan.PrayerClock and services.PrayerService.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QGridLayout, QGroupBox, QPushButton,
                             QSizePolicy, QLineEdit, QTextEdit)
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal

from adhan import PrayerClock
from adhan.config import save_config
from gui.settings import SettingsDialog
from utils.display_helper import format_date_display, format_countdown


# ── RAG background worker ─────────────────────────────────────────────────────

class _RagWorker(QThread):
    """
    Runs the RAG pipeline on a background thread, emitting tokens as they arrive.

    Network calls must never happen on the Qt main thread — it freezes the UI.
    QThread moves the work off the main thread; signals are the thread-safe
    bridge back to the UI.
    """
    token = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, question, answer_fn, records, matrix, voyage, claude) -> None:
        super().__init__()
        self._question = question
        self._fn = answer_fn
        self._records = records
        self._matrix = matrix
        self._voyage = voyage
        self._claude = claude

    def run(self) -> None:
        try:
            stream, _ = self._fn(
                self._question, self._records, self._matrix,
                self._voyage, self._claude,
            )
            for tok in stream:
                self.token.emit(tok)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


# ── Main window ───────────────────────────────────────────────────────────────

class AdhanClockUI(QWidget):

    def __init__(self, clock: PrayerClock | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Adhan Clock")
        self.setGeometry(100, 100, 450, 900)
        self.clock = clock or PrayerClock()
        self.setStyleSheet(
            "background-color: #2b2b2b; color: #ffffff; font-family: sans-serif;"
        )
        self.prayer_labels: dict[str, QLabel] = {}
        self.sunrise_label: QLabel | None = None
        self._rag_worker: _RagWorker | None = None

        self._build_ui()
        self._setup_timer()
        self.refresh_location()
        self._init_rag()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(50, 50, 50, 50)
        layout.setAlignment(Qt.AlignCenter)

        self.date_label = QLabel("Loading Date...")
        self.date_label.setAlignment(Qt.AlignCenter)
        self.date_label.setStyleSheet("color: #aaaaaa; font-size: 18px;")
        layout.addWidget(self.date_label)

        self.time_label = QLabel("00:00:00")
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setStyleSheet(
            "font-weight: bold; color: #ffffff; font-size: 48px;"
        )
        layout.addWidget(self.time_label)

        self.location_label = QLabel("Detecting Location...")
        self.location_label.setAlignment(Qt.AlignCenter)
        self.location_label.setStyleSheet("color: #888888; font-size: 16px;")
        layout.addWidget(self.location_label)

        self.countdown_label = QLabel("Next Prayer in...")
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.setStyleSheet(
            "color: #3498db; font-weight: bold; font-size: 20px; padding: 10px;"
        )
        layout.addWidget(self.countdown_label)

        layout.addStretch(1)
        layout.addWidget(self._build_prayer_grid())
        layout.addStretch(1)

        self.settings_button = QPushButton("Edit Settings")
        self.settings_button.setStyleSheet(
            "background-color: #555555; color: white; padding: 10px; "
            "border-radius: 5px; font-size: 16px;"
        )
        self.settings_button.clicked.connect(self._open_settings)
        layout.addWidget(self.settings_button)

        self.refresh_button = QPushButton("Refresh Location / Times")
        self.refresh_button.setStyleSheet(
            "background-color: #34495e; color: white; padding: 10px; "
            "border-radius: 5px; font-size: 16px;"
        )
        self.refresh_button.clicked.connect(self.refresh_location)
        layout.addWidget(self.refresh_button)

        layout.addWidget(self._build_rag_section())
        self.setLayout(layout)

    def _build_prayer_grid(self) -> QGroupBox:
        group = QGroupBox("Today's Times")
        group.setStyleSheet(
            "color: white; border: 1px solid #555555; border-radius: 5px; "
            "padding: 10px; font-size: 14px;"
        )
        group.setMinimumHeight(250)
        group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        grid = QGridLayout()
        grid.setAlignment(Qt.AlignCenter)
        grid.setSpacing(10)

        for i, prayer in enumerate(["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]):
            name_lbl = QLabel(prayer)
            name_lbl.setStyleSheet(
                "font-weight: bold; color: #aaaaaa; font-size: 16px;"
            )
            name_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            time_lbl = QLabel("--:--")
            time_lbl.setStyleSheet("color: #ffffff; font-size: 16px;")
            time_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            grid.addWidget(name_lbl, i, 0)
            grid.addWidget(time_lbl, i, 1)

            if prayer == "Sunrise":
                self.sunrise_label = time_lbl
            else:
                self.prayer_labels[prayer] = time_lbl

        group.setLayout(grid)
        return group

    def _build_rag_section(self) -> QGroupBox:
        group = QGroupBox("Ask a Question")
        group.setStyleSheet(
            "color: white; border: 1px solid #3d5a80; border-radius: 5px; "
            "padding: 10px; font-size: 14px;"
        )
        inner = QVBoxLayout()
        inner.setSpacing(8)

        input_row = QHBoxLayout()
        self.rag_input = QLineEdit()
        self.rag_input.setPlaceholderText(
            "e.g. When is Fajr in Toronto tomorrow?"
        )
        self.rag_input.setStyleSheet(
            "background-color: #3a3a3a; color: white; border: 1px solid #555; "
            "border-radius: 4px; padding: 6px; font-size: 14px;"
        )
        self.rag_input.returnPressed.connect(self._ask_question)
        input_row.addWidget(self.rag_input)

        self.rag_ask_btn = QPushButton("Ask")
        self.rag_ask_btn.setStyleSheet(
            "background-color: #3d5a80; color: white; padding: 6px 14px; "
            "border-radius: 4px; font-size: 14px;"
        )
        self.rag_ask_btn.clicked.connect(self._ask_question)
        input_row.addWidget(self.rag_ask_btn)
        inner.addLayout(input_row)

        self.rag_answer = QTextEdit()
        self.rag_answer.setReadOnly(True)
        self.rag_answer.setPlaceholderText("Answer will appear here...")
        self.rag_answer.setStyleSheet(
            "background-color: #1e1e1e; color: #cccccc; border: 1px solid #444; "
            "border-radius: 4px; padding: 6px; font-size: 13px;"
        )
        self.rag_answer.setMinimumHeight(100)
        self.rag_answer.setMaximumHeight(160)
        inner.addWidget(self.rag_answer)

        group.setLayout(inner)
        return group

    def _setup_timer(self) -> None:
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_display)
        self.timer.start(1000)

    # ── RAG initialisation ────────────────────────────────────────────────────

    def _init_rag(self) -> None:
        self._rag_ready = False
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent))
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
                f"Ready — {len(self._rag_records)} chunks indexed. "
                "Ask about prayers or a specific city."
            )
        except (Exception, SystemExit) as e:
            self.rag_answer.setPlaceholderText(f"RAG unavailable: {e}")

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.clock.config, self)
        if dialog.exec():
            save_config(dialog.config, self.clock.config_path)
            self.refresh_location()

    def refresh_location(self) -> None:
        self.location_label.setText("Refreshing...")
        self.clock.refresh_settings()
        self.location_label.setText(
            f"{self.clock.config.city} | {self.clock.timezone}"
        )
        self.update_display()

    def update_display(self) -> None:
        now = self.clock.get_current_time()
        self.time_label.setText(now.strftime("%H:%M:%S"))
        self.date_label.setText(format_date_display(now.date()))

        pt = self.clock.get_prayer_times(now.date())
        if not pt:
            return

        self.sunrise_label.setText(pt.sunrise.strftime("%H:%M"))

        next_prayer = None
        for prayer, lbl in self.prayer_labels.items():
            p_time = getattr(pt, prayer.lower())
            lbl.setText(p_time.strftime("%H:%M"))
            if p_time > now and next_prayer is None:
                next_prayer = (prayer, p_time)

        if next_prayer:
            self.countdown_label.setText(
                f"{next_prayer[0]} in {format_countdown(next_prayer[1] - now)}"
            )
        elif not hasattr(sys.modules.get("__main__", object()), "_test_clock"):
            self.countdown_label.setText("All prayers done for today.")

    def _ask_question(self) -> None:
        if not self._rag_ready:
            self.rag_answer.setPlainText(self.rag_answer.placeholderText())
            return
        question = self.rag_input.text().strip()
        if not question or (self._rag_worker and self._rag_worker.isRunning()):
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

    def _on_rag_token(self, token: str) -> None:
        self.rag_answer.insertPlainText(token)
        self.rag_answer.ensureCursorVisible()

    def _on_rag_done(self) -> None:
        self.rag_ask_btn.setEnabled(True)
        self.rag_input.setEnabled(True)
        self.rag_input.clear()

    def _on_rag_error(self, msg: str) -> None:
        self.rag_answer.setPlainText(f"Error: {msg}")
        self.rag_ask_btn.setEnabled(True)
        self.rag_input.setEnabled(True)

    # ── Resize ────────────────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        w = self.width()
        self.date_label.setStyleSheet(
            f"font-size: {max(16, w // 25)}px; color: #aaaaaa;"
        )
        self.time_label.setStyleSheet(
            f"font-size: {max(30, w // 10)}px; font-weight: bold; color: #ffffff;"
        )
        self.location_label.setStyleSheet(
            f"font-size: {max(12, w // 35)}px; color: #888888;"
        )
        self.countdown_label.setStyleSheet(
            f"font-size: {max(18, w // 20)}px; color: #3498db; "
            "font-weight: bold; padding: 5px;"
        )
        for lbl in list(self.prayer_labels.values()) + [self.sunrise_label]:
            lbl.setStyleSheet(
                f"font-size: {max(10, w // 55)}px; color: #ffffff;"
            )
        super().resizeEvent(event)
