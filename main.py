#!/usr/bin/env python3
"""
Main entry point for Adhan Clock application.
Runs both the adhan notification loop and GUI in a single process.
"""

import sys
import threading
from adhan_clock import main as adhan_main
from gui_clock import QApplication, AdhanClockUI
from mac_notifications import client


def run_adhan_loop():
    """Run the adhan clock notification loop in a separate thread."""
    try:
        adhan_main()
    except KeyboardInterrupt:
        print("\nAdhan clock stopped.", flush=True)


if __name__ == "__main__":
    # Initialize notification manager in main thread to register signal handlers
    # This prevents "ValueError: signal only works in main thread"
    client.get_notification_manager()

    # Start adhan clock in background thread
    adhan_thread = threading.Thread(target=run_adhan_loop, daemon=True)
    adhan_thread.start()

    # Run GUI in main thread
    app = QApplication(sys.argv)
    window = AdhanClockUI()
    window.show()
    sys.exit(app.exec_())
