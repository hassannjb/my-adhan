"""
Notification and audio side effects — isolated so they can be easily mocked.
All I/O in the application that isn't network or file config lives here.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

VOLUME_NORMAL     = 1.0
VOLUME_SUPPRESSED = 0.2   # 80% reduction


def send_notification(title: str, subtitle: str) -> None:
    try:
        from mac_notifications import client
        client.create_notification(title=title, subtitle=subtitle, sound="default")
    except Exception as e:
        logger.warning("Notification failed: %s", e)


def _init_mixer() -> bool:
    try:
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        return True
    except Exception as e:
        logger.warning("Audio init failed: %s", e)
        return False


def play_adhan(audio_path: Path, volume: float = VOLUME_NORMAL) -> None:
    """Start adhan playback (non-blocking). Volume is applied before play starts."""
    logger.info("Playing adhan from %s", audio_path)
    if not _init_mixer():
        return
    try:
        import pygame
        pygame.mixer.music.load(str(audio_path))
        pygame.mixer.music.set_volume(max(0.0, min(1.0, volume)))
        pygame.mixer.music.play()
    except Exception as e:
        logger.warning("Audio playback failed: %s", e)


def stop_adhan() -> None:
    """Stop any currently playing adhan immediately."""
    try:
        import pygame
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
    except Exception as e:
        logger.warning("Failed to stop adhan: %s", e)


def set_adhan_volume(level: float) -> None:
    """Set playback volume (0.0–1.0) on the currently playing track."""
    try:
        import pygame
        if pygame.mixer.get_init():
            pygame.mixer.music.set_volume(max(0.0, min(1.0, level)))
    except Exception as e:
        logger.warning("Failed to set volume: %s", e)
