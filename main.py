"""
Entry point for the Adhan Clock GUI application.

    python main.py
"""
import sys

from PyQt5.QtWidgets import QApplication

from gui.clock_window import AdhanClockUI


def main() -> None:
    app = QApplication(sys.argv)
    window = AdhanClockUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
