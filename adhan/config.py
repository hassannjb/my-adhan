"""Config file I/O — the only place that reads or writes config.json."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from adhan.models import Config

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path("config.json")


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.info("Config file not found at %s, using defaults", path)
        return Config()
    except json.JSONDecodeError as e:
        logger.warning("Config file malformed: %s — using defaults", e)
        return Config()
    return Config(
        fajr_angle=float(data.get("fajr_angle", 15.0)),
        isha_angle=float(data.get("isha_angle", 15.0)),
        method=data.get("method", "NORTH_AMERICA"),
        city=data.get("city", "Unknown"),
        latitude=float(data.get("latitude", 0.0)),
        longitude=float(data.get("longitude", 0.0)),
        timezone=data.get("timezone", "UTC"),
    )


def save_config(config: Config, path: Path = DEFAULT_CONFIG_PATH) -> None:
    with open(path, "w") as f:
        json.dump(config.to_dict(), f, indent=4)
    logger.debug("Config saved to %s", path)
