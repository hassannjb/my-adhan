"""
Real-Qt check that a key press suppresses a playing adhan before the focused
button sees it. Runs in a subprocess: test_gui_clock.py replaces PyQt5 in
sys.modules with stubs, so real Qt can't share the pytest process.
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("PyQt5.QtWidgets")

_ROOT = Path(__file__).parent.parent

_SCRIPT = textwrap.dedent("""
    from datetime import datetime
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication
    import gui.clock_window as cw

    cw.threading.Thread = MagicMock()   # no end-watcher thread
    cw.AdhanClockUI._init_rag = lambda self: None
    app = QApplication([])
    clock = MagicMock()
    clock.config = SimpleNamespace(city="TestCity")
    clock.timezone = "UTC"
    clock.get_current_time.return_value = datetime(2023, 10, 27, 10, 0, 0)
    clock.get_prayer_times.return_value = None
    clock.is_adhan_playing.return_value = True
    w = cw.AdhanClockUI(clock=clock)
    w.show()
    w.stop_btn.setFocus()
    QApplication.processEvents()

    stopped = []
    w.stop_btn.clicked.connect(lambda: stopped.append(1))
    QTest.keyClick(w.stop_btn, Qt.Key_Space)
    assert stopped == [], "space reached the focused Stop button"
    clock.set_volume.assert_called_once_with(cw.VOLUME_SUPPRESSED)
    assert not w.suppress_btn.isEnabled()

    # Already suppressed: the key goes to the button as normal
    QTest.keyClick(w.stop_btn, Qt.Key_Space)
    assert stopped == [1], "space should click Stop once suppressed"
    print("OK")
""")


def test_space_on_focused_stop_button_suppresses_instead_of_stopping():
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(_ROOT))
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT], cwd=_ROOT, env=env,
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("OK")
