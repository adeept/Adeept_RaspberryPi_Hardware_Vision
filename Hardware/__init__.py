# Hardware/__init__.py
"""
Adeept Robot HAT hardware interface layer.

Public classes are exported lazily via PEP 562 (module level ``__getattr__``) so that
``import Hardware`` does not eagerly pull in optional dependencies such as smbus,
gpiozero, spidev, numpy, luma.oled or mpu6050. A missing optional dependency is
reported only when the corresponding class is actually accessed.

Demos are run as modules. Execute from the directory that CONTAINS this package::

    cd ~/robot                 # the folder holding Hardware/
    python3 -m Hardware.Motor
    python3 -m Hardware.Servo
    python3 -m Hardware.BatteryMonitor
    python3 -m Hardware.LightTracking
"""
import importlib

__all__ = [
    # PWM / motion
    "PCA9685",
    "Servo",
    "DCMotor",
    # ADC / power
    "ADS7830",
    "LightTracking",
    "BatteryMonitor",
    # Discrete I/O
    "Buzzer",
    "IRReceiver",
    "OnBoardLED",
    "LineTracking",
    "Ultrasonic",
    # Displays and addressable / RGB LED
    "HT16K33Matrix",
    "OLED",
    "DualRGBLED",
    "WS2812",
    # Sensors and filters
    "MPU6050",
    "Kalman_filter",
    # System information
    "SystemInfo",
    "SystemState",
]

# Public name -> owning submodule (relative to this package).
_SUBMODULES = {
    "PCA9685": ".pca9685",
    "Servo": ".Servo",
    "DCMotor": ".Motor",
    "ADS7830": ".ads7830",
    "LightTracking": ".LightTracking",
    "BatteryMonitor": ".BatteryMonitor",
    "Buzzer": ".Buzzer",
    "IRReceiver": ".IRReceiver",
    "OnBoardLED": ".LED",
    "LineTracking": ".LineTracking",
    "Ultrasonic": ".Ultrasonic",
    "HT16K33Matrix": ".LED_Matrix",
    "OLED": ".OLED",
    "DualRGBLED": ".RGB_LED",
    "WS2812": ".WS2812",
    "MPU6050": ".MPU6050",
    "Kalman_filter": ".Kalman_Filter",
    "SystemInfo": ".SystemInfo",
    "SystemState": ".SystemInfo",
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
