"""
Notification and audio side effects — isolated so they can be easily mocked.
All I/O in the application that isn't network or file config lives here.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def send_notification(title: str, subtitle: str) -> None:
    try:
        from mac_notifications import client
        client.create_notification(title=title, subtitle=subtitle, sound="default")
    except Exception as e:
        logger.warning("Notification failed: %s", e)


def play_adhan(audio_path: Path) -> None:
    logger.info("Playing adhan from %s", audio_path)
    try:
        import pygame
        pygame.mixer.init()
        pygame.mixer.music.load(str(audio_path))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(1)
    except Exception as e:
        logger.warning("Audio playback failed: %s", e)
