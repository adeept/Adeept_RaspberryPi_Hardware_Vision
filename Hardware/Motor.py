
#!/usr/bin/env python3
# File name   : Motor.py
# Website     : www.Adeept.com
# Author      : Adeept

"""
DC motor driver based on PCA9685 H-bridge control.
"""

from .pca9685 import PCA9685


class DCMotor:
    """DC motor driver compatible with adafruit_motor DCMotor."""

    FAST_DECAY = 0
    SLOW_DECAY = 1

    def __init__(self, pca_device, channel_pos, channel_neg):
        if not 0 <= channel_pos <= 15:
            raise ValueError("Invalid positive channel")

        if not 0 <= channel_neg <= 15:
            raise ValueError("Invalid negative channel")

        if channel_pos == channel_neg:
            raise ValueError("Motor channels must be different")

        self._pca = pca_device
        self._ch_pos = channel_pos
        self._ch_neg = channel_neg
        self._decay_mode = self.SLOW_DECAY
        self._throttle = None

    @property
    def throttle(self):
        return self._throttle

    @throttle.setter
    def throttle(self, value):
        if value is not None and not -1.0 <= value <= 1.0:
            raise ValueError("Throttle must be between -1.0 and +1.0")

        self._throttle = value

        if value is None:
            self._pca.set_duty_cycle(self._ch_pos, 0)
            self._pca.set_duty_cycle(self._ch_neg, 0)
            return

        if value == 0:
            if self._decay_mode == self.SLOW_DECAY:
                self._pca.set_duty_cycle(self._ch_pos, 0xFFFF)
                self._pca.set_duty_cycle(self._ch_neg, 0xFFFF)
            else:
                self._pca.set_duty_cycle(self._ch_pos, 0)
                self._pca.set_duty_cycle(self._ch_neg, 0)
            return

        duty_cycle = int(0xFFFF * abs(value))

        if self._decay_mode == self.SLOW_DECAY:
            if value < 0:
                self._pca.set_duty_cycle(
                    self._ch_pos, 0xFFFF - duty_cycle
                )
                self._pca.set_duty_cycle(
                    self._ch_neg, 0xFFFF
                )
            else:
                self._pca.set_duty_cycle(
                    self._ch_pos, 0xFFFF
                )
                self._pca.set_duty_cycle(
                    self._ch_neg, 0xFFFF - duty_cycle
                )

        elif value < 0:
            self._pca.set_duty_cycle(self._ch_pos, 0)
            self._pca.set_duty_cycle(self._ch_neg, duty_cycle)

        else:
            self._pca.set_duty_cycle(self._ch_pos, duty_cycle)
            self._pca.set_duty_cycle(self._ch_neg, 0)

    @property
    def decay_mode(self):
        return self._decay_mode

    @decay_mode.setter
    def decay_mode(self, mode):
        if mode not in (self.FAST_DECAY, self.SLOW_DECAY):
            raise ValueError("Invalid decay mode")

        self._decay_mode = mode

        if self._throttle is not None:
            self.throttle = self._throttle

    def stop(self):
        """Stop motor using the selected decay mode."""
        self.throttle = 0.0

    def coast(self):
        """Disable both H-bridge inputs."""
        self.throttle = None

    def close(self):
        """Disable this motor without closing the shared PCA9685."""
        self.coast()


if __name__ == "__main__":
    import time

    MOTOR_PINS = [
        (15, 14),   # M1
        (12, 13),   # M2
        (11, 10),   # M3
        (8, 9)      # M4
    ]

    pca = PCA9685(bus_num=1, address=0x5f, freq=50)

    motors = [
        DCMotor(pca, pos, neg)
        for pos, neg in MOTOR_PINS
    ]

    for motor in motors:
        motor.decay_mode = DCMotor.SLOW_DECAY

    test_speed = 0.5
    test_cycles = 3

    try:
        print("DC motor test start.")

        for i in range(test_cycles):
            print(f"Cycle {i + 1}/{test_cycles}: Forward")

            for motor in motors:
                motor.throttle = test_speed

            time.sleep(2)

            # Coast briefly before reversing direction.
            for motor in motors:
                motor.coast()

            time.sleep(0.1)

            print(f"Cycle {i + 1}/{test_cycles}: Backward")

            for motor in motors:
                motor.throttle = -test_speed

            time.sleep(2)

            for motor in motors:
                motor.coast()

            time.sleep(0.1)

        print("Test completed.")

    except KeyboardInterrupt:
        print("\nInterrupted by user.")

    finally:
        for motor in motors:
            motor.close()

        pca.deinit()
        print("Resources released.")
