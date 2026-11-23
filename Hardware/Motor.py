#!/usr/bin/env python3
# File name   : Motor.py
# Website     : www.Adeept.com
# Author      : Adeept

"""
DC motor driver based on PCA9685 H-bridge control.
"""

from .pca9685 import PCA9685


class MotorBank:
    """Four-wheel driver: pins and polarity stay here, callers pass speed, direction and motor number."""
    DEFAULT_PINS = {1: (15, 14), 2: (12, 13), 3: (11, 10), 4: (8, 9)}
    DEFAULT_DIRECTION = {1: -1, 2: -1, 3: -1, 4: -1}

    def __init__(self, pca, motors=None, pins=None, directions=None):
        available = pins or self.DEFAULT_PINS
        numbers = tuple(available) if motors is None else tuple(motors)
        missing = [number for number in numbers if number not in available]
        if missing:
            raise ValueError("unknown motor number(s): %s" % (missing,))
        self._motors = {number: DCMotor(pca, *available[number]) for number in numbers}
        directions = directions or {}
        self._directions = {number: int(directions.get(number, self.DEFAULT_DIRECTION.get(number, 1)))
                            for number in numbers}

    def drive(self, speed, direction, motor_no=None):
        """speed 0..100, direction >0 forward / <0 backward / 0 stop; motor_no None means all."""
        speed = max(0.0, min(100.0, float(speed)))
        sign = 1 if direction > 0 else -1 if direction < 0 else 0
        if motor_no is not None and motor_no not in self._motors:
            raise ValueError("motor number must be one of %s" % (tuple(self._motors),))
        targets = self._motors if motor_no is None else (motor_no,)
        for number in targets:
            self._motors[number].throttle = self._directions[number] * sign * speed / 100.0

    def close(self):
        for motor in self._motors.values():
            motor.close()


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

        pca_device.claim_channel(channel_pos, self)
        try:
            pca_device.claim_channel(channel_neg, self)
        except Exception:
            # 第二个通道被占用时，回滚第一个通道的认领
            pca_device.release_channel(channel_pos, self)
            raise

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
        try:
            self._pca.release_channel(self._ch_pos, self)
            self._pca.release_channel(self._ch_neg, self)
        except Exception:
            pass


if __name__ == "__main__":
    import time

    pca = PCA9685(bus_num=1, address=0x5f, freq=50)
    motors = MotorBank(pca)
    test_speed, test_cycles = 50, 3

    try:
        print("DC motor test start.")
        for i in range(test_cycles):
            print(f"Cycle {i + 1}/{test_cycles}: Forward")
            motors.drive(test_speed, 1)
            time.sleep(2)
            motors.drive(0, 0)
            time.sleep(0.1)
            print(f"Cycle {i + 1}/{test_cycles}: Backward")
            motors.drive(test_speed, -1)
            time.sleep(2)
            motors.drive(0, 0)
            time.sleep(0.1)
        print("Test completed.")
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        motors.close()
        pca.deinit()
        print("Resources released.")
