import sys
from datetime import datetime as _RealDatetime, timedelta
import pytz
import pytest
from unittest.mock import MagicMock, patch


# ── Stub PyQt5 and optional deps before gui_clock is imported ─────────────────

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


class _GroupBox(_W):
    def setMinimumHeight(self, *a): pass
    def setSizePolicy(self, *a): pass


class _Button(_W):
    clicked = MagicMock()


class _SizePolicy:
    Preferred = 0
    Minimum = 0


class _Qt:
    AlignCenter = 4
    AlignRight = 2
    AlignLeft = 1
    AlignVCenter = 32


_widgets_mod = MagicMock()
_widgets_mod.QWidget = _W
_widgets_mod.QLabel = _Label
_widgets_mod.QVBoxLayout = _Layout
_widgets_mod.QGridLayout = _Layout
_widgets_mod.QGroupBox = _GroupBox
_widgets_mod.QPushButton = _Button
_widgets_mod.QSizePolicy = _SizePolicy
_widgets_mod.QApplication = MagicMock()

_core_mod = MagicMock()
_core_mod.QTimer = _Timer
_core_mod.Qt = _Qt

for _name, _stub in [
    ("PyQt5", MagicMock()),
    ("adhan_clock", MagicMock()),
    ("gui", MagicMock()),
    ("gui.settings", MagicMock()),
    ("hijridate", MagicMock()),
]:
    sys.modules.setdefault(_name, _stub)
sys.modules["PyQt5.QtWidgets"] = _widgets_mod
sys.modules["PyQt5.QtCore"] = _core_mod

from gui_clock import get_location_details, AdhanClockUI  # noqa: E402

UTC = pytz.UTC


# ── Helpers ───────────────────────────────────────────────────────────────────

class _FakeDt:
    """Wraps a real datetime and exposes .astimezone() that returns itself."""
    def __init__(self, dt: _RealDatetime):
        self._dt = dt

    def astimezone(self, tz):
        return self._dt


def _make_pt(now: _RealDatetime, *offsets):
    """Return a mock prayer_times with five real-datetime attributes.

    offsets: (fajr_h, dhuhr_h, asr_h, maghrib_h, isha_h) relative to `now`.
    """
    pt = MagicMock()
    for name, off in zip(("fajr", "dhuhr", "asr", "maghrib", "isha"), offsets):
        setattr(pt, name, _FakeDt(now + timedelta(hours=off)))
    return pt


class _FixedDatetime:
    """Drop-in replacement for the `datetime` class with a pinned .now()."""
    def __init__(self, fixed: _RealDatetime):
        self._fixed = fixed

    def now(self, tz=None):
        return self._fixed


# ── get_location_details ──────────────────────────────────────────────────────

def test_get_location_success(monkeypatch):
    def _get(url):
        r = MagicMock()
        r.json.return_value = {"status": "success", "city": "London", "timezone": "Europe/London"}
        return r

    monkeypatch.setattr("requests.get", _get)
    city, tz = get_location_details()
    assert city == "London"
    assert tz == "Europe/London"


def test_get_location_api_failure(monkeypatch):
    def _get(url):
        r = MagicMock()
        r.json.return_value = {"status": "fail"}
        return r

    monkeypatch.setattr("requests.get", _get)
    city, tz = get_location_details()
    assert city == "Unknown"
    assert tz == "UTC"


def test_get_location_network_error(monkeypatch):
    def _get(url):
        raise Exception("connection refused")

    monkeypatch.setattr("requests.get", _get)
    city, tz = get_location_details()
    assert city == "Offline"
    assert tz == "UTC"


# ── AdhanClockUI fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def widget():
    with patch("gui_clock.get_location_details", return_value=("TestCity", "UTC")), \
         patch("gui_clock.get_times", return_value=None):
        return AdhanClockUI()


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_creates_five_prayer_labels(widget):
    assert set(widget.prayer_labels) == {"Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"}


def test_prayer_labels_start_with_placeholder(widget):
    for lbl in widget.prayer_labels.values():
        assert lbl.text() == "--:--"


# ── update_display ────────────────────────────────────────────────────────────

def test_update_display_returns_early_without_local_tz(widget):
    widget.local_tz = None
    widget.update_display()  # must not raise


def test_update_display_returns_early_when_get_times_is_none(widget):
    now = _RealDatetime(2023, 10, 27, 10, 0, 0, tzinfo=UTC)
    with patch("gui_clock.datetime", _FixedDatetime(now)), \
         patch("gui_clock.get_times", return_value=None):
        widget.local_tz = UTC
        widget.update_display()  # must not raise
    assert widget.countdown_label._text == "Next Prayer in..."  # unchanged


def test_update_display_countdown_includes_hours(widget):
    now = _RealDatetime(2023, 10, 27, 10, 0, 0, tzinfo=UTC)
    # Asr is 2 h in the future; Fajr and Dhuhr already passed
    pt = _make_pt(now, -5, -3, 2, 4, 6)
    with patch("gui_clock.datetime", _FixedDatetime(now)), \
         patch("gui_clock.get_times", return_value=pt):
        widget.local_tz = UTC
        widget.update_display()
    assert widget.countdown_label._text == "Asr in 2h 0m 0s"


def test_update_display_countdown_omits_hours_when_zero(widget):
    now = _RealDatetime(2023, 10, 27, 10, 0, 0, tzinfo=UTC)
    # Maghrib is 30 min away; everything before it has passed
    pt = _make_pt(now, -5, -3, -1, 0.5, 6)
    with patch("gui_clock.datetime", _FixedDatetime(now)), \
         patch("gui_clock.get_times", return_value=pt):
        widget.local_tz = UTC
        widget.update_display()
    assert widget.countdown_label._text == "Maghrib in 30m 0s"


def test_update_display_all_prayers_done(widget):
    now = _RealDatetime(2023, 10, 27, 23, 0, 0, tzinfo=UTC)
    pt = _make_pt(now, -18, -10, -7, -4, -2)  # every prayer in the past
    with patch("gui_clock.datetime", _FixedDatetime(now)), \
         patch("gui_clock.get_times", return_value=pt):
        widget.local_tz = UTC
        widget.update_display()
    assert widget.countdown_label._text == "All prayers done for today."


def test_update_display_prayer_labels_show_formatted_times(widget):
    now = _RealDatetime(2023, 10, 27, 10, 0, 0, tzinfo=UTC)
    # Fajr at 05:00, Dhuhr at 13:00 (relative to now at 10:00)
    pt = _make_pt(now, -5, 3, 6, 8, 10)
    with patch("gui_clock.datetime", _FixedDatetime(now)), \
         patch("gui_clock.get_times", return_value=pt):
        widget.local_tz = UTC
        widget.update_display()
    assert widget.prayer_labels["Fajr"].text() == "05:00"
    assert widget.prayer_labels["Dhuhr"].text() == "13:00"


# ── refresh_location ──────────────────────────────────────────────────────────

def test_refresh_location_updates_location_label(widget):
    with patch("gui_clock.get_location_details", return_value=("Cairo", "Africa/Cairo")), \
         patch("gui_clock.get_times", return_value=None):
        widget.refresh_location()
    assert "Cairo" in widget.location_label._text
    assert "Africa/Cairo" in widget.location_label._text


# ── resizeEvent ───────────────────────────────────────────────────────────────

def test_resize_event_applies_correct_font_sizes(widget):
    widget.resizeEvent(MagicMock())
    width = widget.width()  # 450
    expected_time_size = max(30, width // 10)   # 45
    expected_date_size = max(16, width // 25)   # 18
    assert f"font-size: {expected_time_size}px" in widget.time_label._style
    assert f"font-size: {expected_date_size}px" in widget.date_label._style
