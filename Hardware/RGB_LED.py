#!/usr/bin/env python3
# File name   : RGB_LED.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
Dual-channel RGB LED driver based on gpiozero PWM.
"""
import time
from gpiozero import PWMOutputDevice as PWM


class DualRGBLED:
    """
    Dual RGB LED controller with independent left/right control.
    Default pin configuration matches Adeept Robot HAT (common anode).
    :param left_pins: Tuple of (R, G, B) pins for left LED
    :param right_pins: Tuple of (R, G, B) pins for right LED
    :param pwm_freq: PWM frequency in Hz, default 2000
    :param common_anode: True for common anode (default), False for common cathode
    """

    # Preset color palette
    COLORS = [
        (255, 0, 0),    # Red
        (255, 127, 0),  # Orange
        (255, 255, 0),  # Yellow
        (0, 255, 0),    # Green
        (0, 255, 255),  # Cyan
        (0, 0, 255),    # Blue
        (127, 0, 255)   # Purple
    ]

    def __init__(self, left_pins=(19, 0, 13), right_pins=(1, 5, 6), pwm_freq=2000, common_anode=True):
        self._common_anode = common_anode

        # Initialize left RGB channels
        lr, lg, lb = left_pins
        init_val = 1.0 if common_anode else 0.0
        self._left_r = PWM(pin=lr, initial_value=init_val, frequency=pwm_freq)
        self._left_g = PWM(pin=lg, initial_value=init_val, frequency=pwm_freq)
        self._left_b = PWM(pin=lb, initial_value=init_val, frequency=pwm_freq)

        # Initialize right RGB channels
        rr, rg, rb = right_pins
        self._right_r = PWM(pin=rr, initial_value=init_val, frequency=pwm_freq)
        self._right_g = PWM(pin=rg, initial_value=init_val, frequency=pwm_freq)
        self._right_b = PWM(pin=rb, initial_value=init_val, frequency=pwm_freq)

    def _to_pwm(self, value):
        """Convert 0-255 color value to PWM duty cycle"""
        value = max(0, min(255, value))
        duty = value / 255.0
        return 1.0 - duty if self._common_anode else duty

    def set_left(self, r, g, b):
        """Set color of the left RGB LED"""
        self._left_r.value = self._to_pwm(r)
        self._left_g.value = self._to_pwm(g)
        self._left_b.value = self._to_pwm(b)

    def set_right(self, r, g, b):
        """Set color of the right RGB LED"""
        self._right_r.value = self._to_pwm(r)
        self._right_g.value = self._to_pwm(g)
        self._right_b.value = self._to_pwm(b)

    def set_both(self, r, g, b):
        """Set both left and right RGB LEDs to the same color"""
        self.set_left(r, g, b)
        self.set_right(r, g, b)

    def turn_off(self):
        """Turn off all RGB LEDs"""
        self.set_both(0, 0, 0)

    def close(self):
        """Release all GPIO resources"""
        for led in [self._left_r, self._left_g, self._left_b,
                    self._right_r, self._right_g, self._right_b]:
            try:
                led.close()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


if __name__ == "__main__":
    print("Dual RGB LED test started.")
    with DualRGBLED() as leds:
        try:
            print("Cycling through preset colors on both LEDs...")
            while True:
                for r, g, b in DualRGBLED.COLORS:
                    leds.set_both(r, g, b)
                    time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nTest stopped by user.")
