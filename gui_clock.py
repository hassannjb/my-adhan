# Backward-compatibility shim.
# The canonical implementation is now in gui/clock_window.py.
from gui.clock_window import AdhanClockUI
from adhan.location import get_current_location as _get_loc


def get_location_details():
    """Deprecated — use adhan.location.get_current_location()."""
    coords, tz, city = _get_loc()
    return city, tz.zone


__all__ = ["AdhanClockUI", "get_location_details"]

if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = AdhanClockUI()
    window.show()
    sys.exit(app.exec())
