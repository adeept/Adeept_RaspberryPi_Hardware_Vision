#!/usr/bin/env python3
# File name   : LineTracking.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
3-channel line tracking sensor driver based on gpiozero.
Designed for line-following robot applications.
"""
import time
from gpiozero import InputDevice


class LineTracking:
    """
    3-channel line tracking sensor controller.
    Typical output logic: 1 = white reflective surface, 0 = black line.
    :param left_pin: BCM GPIO pin for left sensor, default 22
    :param middle_pin: BCM GPIO pin for middle sensor, default 27
    :param right_pin: BCM GPIO pin for right sensor, default 17
    """

    def __init__(self, left_pin=22, middle_pin=27, right_pin=17):
        self._left = InputDevice(pin=left_pin)
        self._middle = InputDevice(pin=middle_pin)
        self._right = InputDevice(pin=right_pin)

    def read(self):
        """
        Read status of all three sensors at once.
        :return: Tuple (left_status, middle_status, right_status), each value is 0 or 1
        """
        left_status = self._left.value
        middle_status = self._middle.value
        right_status = self._right.value
        return (left_status, middle_status, right_status)

    def close(self):
        """Release GPIO resources for all three sensors"""
        for sensor in [self._left, self._middle, self._right]:
            try:
                sensor.close()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


if __name__ == "__main__":
    tracker = LineTracking()
    try:
        print("Line tracking sensor test started.")
        print(" Left | Middle | Right ")
        print("------------------------")
        while True:
            left, mid, right = tracker.read()
            print(f"   {left}  |   {mid}    |   {right}")
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\nTest stopped by user.")
    finally:
        tracker.close()
        print("GPIO resources released.")
