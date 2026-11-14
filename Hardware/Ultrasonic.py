#!/usr/bin/env python3
# File name   : Ultrasonic.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
Ultrasonic distance sensor driver based on gpiozero.
Compatible with HC-SR04 and similar modules.
"""
from gpiozero import DistanceSensor
from time import sleep


class Ultrasonic:
    """
    Ultrasonic distance sensor controller.
    Returns distance in centimeters by default.
    :param trigger_pin: Trigger GPIO pin (BCM encoding), default 23
    :param echo_pin: Echo GPIO pin (BCM encoding), default 24
    :param max_distance: Maximum detection distance in meters, default 2
    """

    def __init__(self, trigger_pin=23, echo_pin=24, max_distance=2):
        self._sensor = DistanceSensor(echo=echo_pin,trigger=trigger_pin,max_distance=max_distance)

    def get_distance(self):
        """
        Get current distance measurement.
        :return: Distance value, unit: centimeter (cm)
        """
        return self._sensor.distance * 100

    def close(self):
        """Release GPIO resources"""
        try:
            self._sensor.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


if __name__ == "__main__":
    sensor = Ultrasonic()
    try:
        print("Ultrasonic distance measurement start.")
        while True:
            distance = sensor.get_distance()
            print(f"Distance: {distance:.2f} cm")
            sleep(0.5)
    except KeyboardInterrupt:
        print("\nMeasurement stopped by user.")
    finally:
        sensor.close()
        print("GPIO resources released.")
