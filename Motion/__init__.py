# Motion/__init__.py
"""
Adeept robot motion layer.

``Hardware.Servo`` answers "put the horn at angle X right now".  This package
answers the question above it: "get there smoothly, and let sixteen joints share
a single clock".  Nothing here owns a thread or a timer -- the caller drives
``update(dt)`` from the robot's own loop.

Demos are run as modules.  Execute from the directory that CONTAINS this package::

    cd ~/robot                 # the folder holding Hardware/ and Motion/
    python3 -m Motion                 # motion demo
    python3 -m Motion.calibrate       # keyboard calibration, writes a JSON table
"""
import importlib

__all__ = [
    "Profile",
    "Joint",
    "ServoBank",
    "ServoCalibration",
    "ServoCalibrator",
]

# Public name -> owning submodule (relative to this package).
_SUBMODULES = {
    "Profile": ".profile",
    "Joint": ".joint",
    "ServoBank": ".servo_bank",
    "ServoCalibration": ".calibration",
    "ServoCalibrator": ".calibrate",
}


def __getattr__(name):
    """Import the owning submodule on first access, then cache the attribute."""
    submodule = _SUBMODULES.get(name)
    if submodule is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    value = getattr(importlib.import_module(submodule, __name__), name)
    globals()[name] = value
    return value


def __dir__():
    """Expose public names to dir() / IDE completion without importing anything."""
    return sorted(set(globals()) | set(__all__))
