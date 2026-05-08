"""
AdhanClockUI — the main PyQt5 window.

GUI concerns only: layout, display updates, user events.
All business logic is delegated to adhan.PrayerClock and services.PrayerService.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QGridLayout, QGroupBox, QPushButton,
                             QSizePolicy, QLineEdit, QTextEdit, QScrollArea, QMenu)
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal

from adhan import PrayerClock
from adhan.config import save_config
from adhan.notifications import VOLUME_NORMAL, VOLUME_SUPPRESSED
from gui.settings import SettingsDialog
from utils.display_helper import format_date_display, format_countdown

_ADHAN_TRIGGER_WINDOW = 30   # seconds after prayer time to auto-play adhan

_BTN_STYLE = (
    "padding: 5px 10px; border-radius: 4px; font-size: 12px; color: white;"
)
_BTN_PLAY     = _BTN_STYLE + "background-color: #27ae60;"
_BTN_STOP     = _BTN_STYLE + "background-color: #c0392b;"
_BTN_SUPPRESS = _BTN_STYLE + "background-color: #e67e22;"
_BTN_GEAR     = (
    "padding: 5px 8px; border-radius: 4px; font-size: 14px; "
    "background-color: #444444; color: white;"
)


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

    _adhan_ended = pyqtSignal()   # emitted from watcher thread when playback stops

    def __init__(self, clock: PrayerClock | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Adhan Clock")
        self.setGeometry(100, 100, 450, 900)
        self.clock = clock or PrayerClock()
        self.setStyleSheet(
            "background-color: #2b2b2b; color: #ffffff; font-family: sans-serif;"
        )
        self.prayer_labels: dict[str, QLabel] = {}
        self.prayer_name_labels: list[QLabel] = []
        self.sunrise_label: QLabel | None = None
        self._rag_worker: _RagWorker | None = None
        self._adhan_played: set[str] = set()
        self._last_adhan_date = None
        self._adhan_ended.connect(self._on_adhan_ended)

        self._build_ui()
        self._setup_timer()
        self.refresh_location()
        self._init_rag()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # All content lives in a plain widget so it can be scrolled
        content = QWidget()
        content.setStyleSheet("background-color: #2b2b2b;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(30, 16, 30, 30)
        layout.setAlignment(Qt.AlignTop)

        # ── Top bar: adhan controls (left) + gear button (right) ──────────
        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)

        self.play_btn = QPushButton("▶ Play")
        self.play_btn.setStyleSheet(_BTN_PLAY)
        self.play_btn.clicked.connect(self._play_adhan)
        top_bar.addWidget(self.play_btn)

        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.setStyleSheet(_BTN_STOP)
        self.stop_btn.clicked.connect(self._stop_adhan)
        top_bar.addWidget(self.stop_btn)

        self.suppress_btn = QPushButton("🔉 Suppress")
        self.suppress_btn.setStyleSheet(_BTN_SUPPRESS)
        self.suppress_btn.clicked.connect(self._suppress_current)
        top_bar.addWidget(self.suppress_btn)

        top_bar.addStretch()

        self.gear_btn = QPushButton("⚙")
        self.gear_btn.setStyleSheet(_BTN_GEAR)
        self.gear_btn.clicked.connect(self._open_settings_menu)
        top_bar.addWidget(self.gear_btn)

        layout.addLayout(top_bar)
        layout.addSpacing(10)

        # ── Hijri date ─────────────────────────────────────────────────────
        self.hijri_label = QLabel("")
        self.hijri_label.setAlignment(Qt.AlignCenter)
        self.hijri_label.setStyleSheet("color: #c0a060; font-size: 16px;")
        layout.addWidget(self.hijri_label)

        # ── Gregorian date / time / location / countdown ───────────────────
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

        layout.addSpacing(16)
        layout.addWidget(self._build_prayer_grid())
        layout.addSpacing(16)

        layout.addWidget(self._build_rag_section())

        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background-color: #2b2b2b; }
            QScrollBar:vertical {
                background: #3a3a3a; width: 6px; border-radius: 3px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #666; border-radius: 3px; min-height: 20px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical { height: 0; }
        """)

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.setLayout(outer)

    def _build_prayer_grid(self) -> QGroupBox:
        group = QGroupBox("Today's Times")
        group.setStyleSheet(
            "color: white; border: 1px solid #555555; border-radius: 5px; "
            "padding: 10px; font-size: 14px;"
        )
        group.setMinimumHeight(200)
        group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Row 1: Fajr | Sunrise | Dhuhr
        # Row 2: Asr  | Maghrib | Isha
        row1 = QHBoxLayout()
        row2 = QHBoxLayout()
        all_prayers = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]

        for i, prayer in enumerate(all_prayers):
            container = QWidget()
            container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            h = QHBoxLayout()
            h.setAlignment(Qt.AlignCenter)
            h.setContentsMargins(0, 0, 0, 0)

            name_lbl = QLabel(prayer)
            name_lbl.setStyleSheet("font-weight: bold; color: #aaaaaa; font-size: 16px;")
            name_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            time_lbl = QLabel("--:--")
            time_lbl.setStyleSheet("color: #ffffff; font-size: 16px;")
            time_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            h.addWidget(name_lbl)
            h.addWidget(time_lbl)
            container.setLayout(h)

            self.prayer_name_labels.append(name_lbl)
            if prayer == "Sunrise":
                self.sunrise_label = time_lbl
            else:
                self.prayer_labels[prayer] = time_lbl

            (row1 if i < 3 else row2).addWidget(container)

        outer = QVBoxLayout()
        outer.addLayout(row1)
        outer.addLayout(row2)
        group.setLayout(outer)
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
            from rag.query import load_index, load_clients, INDEX_PATH
            from rag.chat import answer_stream_with_tools
            if not INDEX_PATH.exists():
                self.rag_answer.setPlaceholderText(
                    "RAG index not found. Run: python rag/ingest.py"
                )
                return
            self._rag_records, self._rag_matrix = load_index(INDEX_PATH)
            self._rag_voyage, self._rag_claude = load_clients()
            self._answer_stream_fn = answer_stream_with_tools
            self._rag_ready = True
            self.rag_answer.setPlaceholderText(
                f"Ready — {len(self._rag_records)} chunks indexed. "
                "Ask about prayers or a specific city."
            )
        except (Exception, SystemExit) as e:
            self.rag_answer.setPlaceholderText(f"RAG unavailable: {e}")

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _play_adhan(self) -> None:
        threading.Thread(target=lambda: self.clock.play_adhan(volume=VOLUME_NORMAL),
                         daemon=True).start()

    def _stop_adhan(self) -> None:
        self.clock.stop_adhan()

    def _suppress_current(self) -> None:
        """Drop volume 95% for the current adhan; auto-restore when it ends."""
        self.clock.set_volume(VOLUME_SUPPRESSED)
        self.suppress_btn.setEnabled(False)
        threading.Thread(target=self._watch_adhan_end, daemon=True).start()

    def _watch_adhan_end(self) -> None:
        """Background thread: wait for playback to stop, then signal the main thread."""
        import time
        try:
            import pygame
            while pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                time.sleep(0.5)
        except Exception:
            pass
        self._adhan_ended.emit()

    def _on_adhan_ended(self) -> None:
        """Called on the main thread when the watcher detects playback has stopped."""
        self.clock.set_volume(VOLUME_NORMAL)
        self.suppress_btn.setEnabled(True)

    def _open_settings_menu(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #3a3a3a; color: white; border: 1px solid #555; }"
            "QMenu::item:selected { background-color: #555555; }"
        )
        edit_action = menu.addAction("Edit Settings")
        refresh_action = menu.addAction("Refresh Location")
        action = menu.exec_(self.gear_btn.mapToGlobal(
            self.gear_btn.rect().bottomLeft()
        ))
        if action == edit_action:
            dialog = SettingsDialog(self.clock.config, self)
            if dialog.exec():
                save_config(dialog.config, self.clock.config_path)
                self.refresh_location()
        elif action == refresh_action:
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
        try:
            import hijridate
            h = hijridate.Gregorian(now.year, now.month, now.day).to_hijri()
            self.hijri_label.setText(f"{h.day} {h.month_name()} {h.year}")
        except Exception:
            self.hijri_label.setText("")

        pt = self.clock.get_prayer_times(now.date())
        if not pt:
            return

        self.sunrise_label.setText(pt.sunrise.strftime("%H:%M"))

        next_prayer = None
        for prayer, lbl in self.prayer_labels.items():
            p_time = getattr(pt, prayer.lower())
            new_text = p_time.strftime("%H:%M")
            if lbl.text() != new_text:
                lbl.setText(new_text)
                lbl.repaint()
            if p_time > now and next_prayer is None:
                next_prayer = (prayer, p_time)

        QApplication.processEvents()

        if next_prayer:
            self.countdown_label.setText(
                f"{next_prayer[0]} in {format_countdown(next_prayer[1] - now)}"
            )
        elif not hasattr(sys.modules.get("__main__", object()), "_test_clock"):
            self.countdown_label.setText("All prayers done for today.")

        self._check_adhan_trigger(now, pt)

    def _check_adhan_trigger(self, now, pt) -> None:
        """Play adhan automatically when a prayer time is reached (once per prayer per day)."""
        today = now.date()
        if today != self._last_adhan_date:
            self._adhan_played.clear()
            self._last_adhan_date = today

        for prayer in ("Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"):
            key = f"{prayer}_{today}"
            if key in self._adhan_played:
                continue
            p_time = getattr(pt, prayer.lower())
            delta = (now - p_time).total_seconds()
            if 0 <= delta <= _ADHAN_TRIGGER_WINDOW:
                self._adhan_played.add(key)
                threading.Thread(
                    target=lambda p=prayer: self.clock.play_adhan(p, VOLUME_NORMAL),
                    daemon=True,
                ).start()
                break

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
        self.hijri_label.setStyleSheet(
            f"font-size: {max(14, w // 30)}px; color: #c0a060;"
        )
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
        prayer_size = max(16, w // 34)
        for lbl in self.prayer_name_labels:
            lbl.setStyleSheet(f"font-weight: bold; font-size: {prayer_size}px; color: #aaaaaa;")
        for lbl in list(self.prayer_labels.values()) + [self.sunrise_label]:
            lbl.setStyleSheet(f"font-size: {prayer_size}px; color: #ffffff;")
        super().resizeEvent(event)
