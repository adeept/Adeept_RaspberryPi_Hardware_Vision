#!/usr/bin/env python3
# File name   : servo.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
180° servo driver based on PCA9685.
"""
import time
from .pca9685 import PCA9685

class Servo:
    """
    Single servo controller driven by PCA9685.
    :param pca_device: Initialized PCA9685 instance 
    :param channel: PWM channel number 0-15
    :param min_pulse: Pulse width at 0°, in microseconds, default 500
    :param max_pulse: Pulse width at max angle, in microseconds, default 2400
    :param actuation_range: Full angle range, default 180 degrees
    """

    def __init__(self, pca_device, channel, min_pulse=500, max_pulse=2400, actuation_range=180):
        self._pca = pca_device
        self._channel = channel
        self._min_pulse = min_pulse
        self._max_pulse = max_pulse
        self._angle_range = actuation_range
        self._current_angle = 90.0

    @property
    def angle(self):
        """Current servo angle, range: 0 ~ actuation_range"""
        return self._current_angle

    @angle.setter
    def angle(self, value):
        # Clamp angle within valid range
        value = max(0.0, min(float(self._angle_range), value))
        self._current_angle = value
        # Convert angle to pulse width (microseconds)
        pulse = self._min_pulse + (self._max_pulse - self._min_pulse) * value / self._angle_range
        # Convert pulse width to PCA9685 tick count (50 Hz = 20000 µs period)
        off_count = int(pulse / 20000 * PCA9685._RESOLUTION)
        self._pca.set_pwm(self._channel, 0, off_count)

    def close(self):
        """Clear PWM output on this channel (do not close shared PCA9685 bus)"""
        try:
            self._pca.set_pwm(self._channel, 0, 0)
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


if __name__ == "__main__":
    # Hardware configuration (consistent with Adeept Robot HAT)
    PCA_ADDR = 0x5F
    SERVO_FREQ = 50
    SERVO_COUNT = 16
    DEFAULT_MIN_PULSE = 500
    DEFAULT_MAX_PULSE = 2400
    DEFAULT_ANGLE_RANGE = 180

    # Initialize shared PCA9685 device
    pca = PCA9685(bus_num=1, address=PCA_ADDR, freq=SERVO_FREQ)

    # Initialize all 16 servos
    servos = []
    for ch in range(SERVO_COUNT):
        s = Servo(
            pca, ch,
            min_pulse=DEFAULT_MIN_PULSE,
            max_pulse=DEFAULT_MAX_PULSE,
            actuation_range=DEFAULT_ANGLE_RANGE
        )
        servos.append(s)

    def test_all_servos():
        """Sweep all 16 servos from 0° to 180° and back synchronously"""
        for angle in range(0, DEFAULT_ANGLE_RANGE + 1, 10):
            for s in servos:
                s.angle = angle
            time.sleep(0.01)
        time.sleep(0.5)

        for angle in range(DEFAULT_ANGLE_RANGE, -1, -10):
            for s in servos:
                s.angle = angle
            time.sleep(0.01)
        time.sleep(0.5)

    try:
        print("All 16 servos start to rotate 0-180 back and forth synchronously.")
        while True:
            test_all_servos()

    except KeyboardInterrupt:
        print("\nCtrl + C detected. Setting all servos to 90 degrees.")
        for s in servos:
            s.angle = 90
    finally:
        # Release all channels and close PCA9685
        for s in servos:
            s.close()
        pca.deinit()
        print("Resources released.")
