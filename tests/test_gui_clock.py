import sys
from datetime import datetime as _RealDatetime, timedelta
from types import SimpleNamespace
import pytz
import pytest
from unittest.mock import MagicMock

# ── Import real domain models BEFORE any sys.modules stubs are set ─────────────
# adhan.models is a pure-dataclass module — no Qt, no network.
# We import it now so Config is available as a real class in tests.
from adhan.models import Config

# ── Stub PyQt5 and heavy deps before gui.clock_window is imported ──────────────

class _W:
    def __init__(self, *a, **kw): pass
    def setWindowTitle(self, *a): pass
    def setGeometry(self, *a): pass
    def setStyleSheet(self, s=""): self._style = s
    def setLayout(self, *a): pass
    def width(self): return 450
    def resizeEvent(self, e): pass


class _Label(_W):
    def __init__(self, text="", *a, **kw):
        self._text = text
        self._style = ""

    def setAlignment(self, *a): pass
    def setText(self, t): self._text = t
    def text(self): return self._text
    def repaint(self): pass


class _Timer:
    timeout = MagicMock()
    def start(self, *a): pass


class _Layout:
    def __init__(self, *a, **kw): pass
    def setContentsMargins(self, *a): pass
    def setAlignment(self, *a): pass
    def addWidget(self, *a): pass
    def addStretch(self, *a): pass
    def setSpacing(self, *a): pass
    def addLayout(self, *a): pass


class _GroupBox(_W):
    def setMinimumHeight(self, *a): pass
    def setSizePolicy(self, *a): pass
    def setLayout(self, *a): pass


class _Button(_W):
    clicked = MagicMock()


class _LineEdit(_W):
    def __init__(self, *a, **kw):
        self._text = ""
        self._style = ""
        self.returnPressed = MagicMock()
    def setPlaceholderText(self, *a): pass
    def text(self): return self._text
    def setText(self, t): self._text = t
    def setEnabled(self, *a): pass
    def clear(self): self._text = ""


class _TextEdit(_W):
    def __init__(self, *a, **kw):
        self._text = ""
        self._style = ""
        self._placeholder = ""
    def setReadOnly(self, *a): pass
    def setPlaceholderText(self, t): self._placeholder = t
    def placeholderText(self): return self._placeholder
    def setMinimumHeight(self, *a): pass
    def setMaximumHeight(self, *a): pass
    def setPlainText(self, t): self._text = t
    def insertPlainText(self, t): self._text += t
    def ensureCursorVisible(self): pass
    def text(self): return self._text


class _SizePolicy:
    Preferred = 0
    Minimum = 0


class _Qt:
    AlignCenter = 4
    AlignRight = 2
    AlignLeft = 1
    AlignVCenter = 32


class _Thread:
    def __init__(self, *a, **kw): pass
    def start(self, *a): pass
    def isRunning(self): return False


def _pyqtSignal(*a, **kw): return MagicMock()


_widgets_mod = MagicMock()
_widgets_mod.QWidget = _W
_widgets_mod.QLabel = _Label
_widgets_mod.QVBoxLayout = _Layout
_widgets_mod.QHBoxLayout = _Layout
_widgets_mod.QGridLayout = _Layout
_widgets_mod.QGroupBox = _GroupBox
_widgets_mod.QPushButton = _Button
_widgets_mod.QLineEdit = _LineEdit
_widgets_mod.QTextEdit = _TextEdit
_widgets_mod.QSizePolicy = _SizePolicy
_widgets_mod.QApplication = MagicMock()

_core_mod = MagicMock()
_core_mod.QTimer = _Timer
_core_mod.Qt = _Qt
_core_mod.QThread = _Thread
_core_mod.pyqtSignal = _pyqtSignal

# Stub modules that have heavy deps or require GUI / network at import time.
# adhan.models was imported above (real), so adhan + adhan.config stubs prevent
# the rest of the package (adhan.clock → notifications → pygame) from loading.
for _name, _stub in [
    ("PyQt5", MagicMock()),
    ("adhan", MagicMock()),
    ("adhan.config", MagicMock()),
    ("gui.settings", MagicMock()),
    ("hijridate", MagicMock()),
]:
    sys.modules.setdefault(_name, _stub)

sys.modules["PyQt5.QtWidgets"] = _widgets_mod
sys.modules["PyQt5.QtCore"] = _core_mod

from gui.clock_window import AdhanClockUI  # noqa: E402

UTC = pytz.UTC


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_pt(now: _RealDatetime, fajr_h, dhuhr_h, asr_h, maghrib_h, isha_h):
    """
    Build a simple prayer-times namespace.
    PrayerSchedule attrs are plain datetimes — no .astimezone() wrapper needed.
    """
    return SimpleNamespace(
        fajr=now + timedelta(hours=fajr_h),
        sunrise=now + timedelta(hours=fajr_h + 1),
        dhuhr=now + timedelta(hours=dhuhr_h),
        asr=now + timedelta(hours=asr_h),
        maghrib=now + timedelta(hours=maghrib_h),
        isha=now + timedelta(hours=isha_h),
    )


def _make_clock(now: _RealDatetime = None, prayer_times=None):
    clock = MagicMock()
    clock.timezone = UTC
    clock.config = Config(city="TestCity")
    clock.get_current_time.return_value = (
        now or _RealDatetime(2023, 10, 27, 10, 0, 0, tzinfo=UTC)
    )
    clock.get_prayer_times.return_value = prayer_times
    return clock


# ── AdhanClockUI fixture ──────────────────────────────────────────────────────

@pytest.fixture
def widget():
    return AdhanClockUI(clock=_make_clock())


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_creates_five_prayer_labels(widget):
    assert set(widget.prayer_labels) == {"Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"}


def test_prayer_labels_start_with_placeholder(widget):
    for lbl in widget.prayer_labels.values():
        assert lbl.text() == "--:--"


def test_sunrise_label_exists_and_starts_with_placeholder(widget):
    assert widget.sunrise_label is not None
    assert widget.sunrise_label.text() == "--:--"


# ── update_display ────────────────────────────────────────────────────────────

def test_update_display_no_crash_when_get_times_returns_none(widget):
    widget.clock.get_prayer_times.return_value = None
    widget.update_display()
    assert widget.countdown_label._text == "Next Prayer in..."


def test_update_display_countdown_includes_hours(widget):
    now = _RealDatetime(2023, 10, 27, 10, 0, 0, tzinfo=UTC)
    pt = _make_pt(now, -5, -3, 2, 4, 6)
    widget.clock.get_current_time.return_value = now
    widget.clock.get_prayer_times.return_value = pt
    widget.update_display()
    assert widget.countdown_label._text == "Asr in 2h 0m 0s"


def test_update_display_countdown_omits_hours_when_zero(widget):
    now = _RealDatetime(2023, 10, 27, 10, 0, 0, tzinfo=UTC)
    pt = _make_pt(now, -5, -3, -1, 0.5, 6)
    widget.clock.get_current_time.return_value = now
    widget.clock.get_prayer_times.return_value = pt
    widget.update_display()
    assert widget.countdown_label._text == "Maghrib in 30m 0s"


def test_update_display_all_prayers_done(widget):
    now = _RealDatetime(2023, 10, 27, 23, 0, 0, tzinfo=UTC)
    pt = _make_pt(now, -18, -10, -7, -4, -2)
    widget.clock.get_current_time.return_value = now
    widget.clock.get_prayer_times.return_value = pt
    widget.update_display()
    assert widget.countdown_label._text == "All prayers done for today."


def test_update_display_prayer_labels_show_formatted_times(widget):
    now = _RealDatetime(2023, 10, 27, 10, 0, 0, tzinfo=UTC)
    pt = _make_pt(now, -5, 3, 6, 8, 10)
    widget.clock.get_current_time.return_value = now
    widget.clock.get_prayer_times.return_value = pt
    widget.update_display()
    assert widget.prayer_labels["Fajr"].text() == "05:00"
    assert widget.prayer_labels["Dhuhr"].text() == "13:00"


def test_update_display_sunrise_label_updated(widget):
    now = _RealDatetime(2023, 10, 27, 10, 0, 0, tzinfo=UTC)
    pt = _make_pt(now, -5, 3, 6, 8, 10)
    widget.clock.get_current_time.return_value = now
    widget.clock.get_prayer_times.return_value = pt
    widget.update_display()
    assert widget.sunrise_label.text() == "06:00"


# ── refresh_location ──────────────────────────────────────────────────────────

def test_refresh_location_updates_location_label(widget):
    widget.clock.config = Config(city="Cairo")
    widget.clock.timezone = pytz.timezone("Africa/Cairo")
    widget.refresh_location()
    assert "Cairo" in widget.location_label._text
    assert "Africa/Cairo" in widget.location_label._text


# ── resizeEvent ───────────────────────────────────────────────────────────────

def test_resize_event_applies_correct_font_sizes(widget):
    widget.resizeEvent(MagicMock())
    width = widget.width()
    expected_time_size = max(30, width // 10)
    expected_date_size = max(16, width // 25)
    assert f"font-size: {expected_time_size}px" in widget.time_label._style
    assert f"font-size: {expected_date_size}px" in widget.date_label._style
