# Backward-compatibility shim.
# The canonical implementations are now in adhan/config.py and adhan/location.py.
from adhan.config import load_config
from adhan.location import get_current_location
from adhan.calculator import build_params


def get_location_from_system(config):
    """Deprecated — use adhan.location.get_current_location()."""
    coords, tz, _city = get_current_location()
    return (coords.latitude, coords.longitude), tz


def get_calculation_params(config):
    """Deprecated — use adhan.calculator.build_params()."""
    from adhan.models import Config
    c = Config(
        method=config.get("method", "NORTH_AMERICA"),
        fajr_angle=config.get("fajr_angle", 15.0),
        isha_angle=config.get("isha_angle", 15.0),
    )
    return build_params(c)


__all__ = ["load_config", "get_location_from_system", "get_calculation_params"]
