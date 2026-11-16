#!/usr/bin/env python3
# File name   : pca9685.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
Universal PCA9685 16-channel 12-bit PWM chip driver based on python3-smbus.
Suitable for servos, DC motors, LED dimming and other PWM scenarios.
"""
import time
from smbus import SMBus


class PCA9685:
    """PCA9685 16-channel 12-bit PWM driver."""
    _MODE1 = 0x00
    _MODE2 = 0x01
    _PRESCALE = 0xFE
    _LED0_ON_L = 0x06

    _RESOLUTION = 4096
    _FULL_RANGE = 0x0FFF          # 12-bit full scale count
    _OSC_CLOCK = 25000000

    # 位 12 在 LEDn_ON_H / LEDn_OFF_H 中分别表示 "full on" / "full off"
    _FULL_ON = 0x1000
    _FULL_OFF = 0x1000

    def __init__(self, bus_num=1, address=0x5f, freq=50):
        self.bus = SMBus(bus_num)
        self.addr = address
        self._frequency = None
        self._closed = False
        # channel -> owner object，用于发现舵机/电机抢同一通道
        self._channel_owners = {}

        # Reset MODE1 and configure output driver.
        self._write_reg(self._MODE1, 0x00)
        self._write_reg(self._MODE2, 0x04)
        self.frequency = freq

    def _write_reg(self, reg, value):
        self.bus.write_byte_data(self.addr, reg, value & 0xFF)

    def _read_reg(self, reg):
        return self.bus.read_byte_data(self.addr, reg)

    def _check_open(self):
        if self._closed:
            raise RuntimeError("PCA9685 is closed")

    @property
    def resolution(self):
        """PWM steps per period (4096 for the 12-bit PCA9685)."""
        return self._RESOLUTION

    @property
    def frequency(self):
        """Return the actual PWM frequency."""
        prescale = self._read_reg(self._PRESCALE)
        self._frequency = (
            self._OSC_CLOCK / (self._RESOLUTION * (prescale + 1))
        )
        return self._frequency

    @frequency.setter
    def frequency(self, freq):
        self.set_frequency(freq)

    def set_frequency(self, freq):
        """Set PWM frequency for all 16 channels."""
        self._check_open()

        if freq <= 0:
            raise ValueError("Frequency must be greater than zero")

        prescale = int(
            round(self._OSC_CLOCK / (self._RESOLUTION * freq)) - 1
        )

        if not 3 <= prescale <= 255:
            raise ValueError("Frequency is outside PCA9685 range")

        old_mode = self._read_reg(self._MODE1)

        # Enter sleep mode before changing prescaler.
        sleep_mode = (old_mode & 0x7F) | 0x10
        self._write_reg(self._MODE1, sleep_mode)
        self._write_reg(self._PRESCALE, prescale)

        # Wake up and enable register auto-increment.
        new_mode = (old_mode & 0x7F) | 0x20
        self._write_reg(self._MODE1, new_mode)

        time.sleep(0.005)

        # Restart PWM.
        self._write_reg(self._MODE1, new_mode | 0x80)

        self._frequency = (
            self._OSC_CLOCK / (self._RESOLUTION * (prescale + 1))
        )

    def claim_channel(self, channel, owner):
        """
        Register the owner of a PWM channel.
        :raise ValueError: the channel is already claimed by another object
        """
        if not 0 <= channel <= 15:
            raise ValueError("Channel must be between 0 and 15")

        current = self._channel_owners.get(channel)
        if current is not None and current is not owner:
            raise ValueError(
                f"PCA9685 channel {channel} is already claimed by "
                f"{type(current).__name__}"
            )
        self._channel_owners[channel] = owner

    def release_channel(self, channel, owner):
        """Release a channel previously claimed by owner."""
        if self._channel_owners.get(channel) is owner:
            del self._channel_owners[channel]

    def channel_owner(self, channel):
        """Return the owner object of a channel, or None."""
        return self._channel_owners.get(channel)

    def set_pwm(self, channel, on_count, off_count):
        """Set PWM ON/OFF counter values for one channel."""
        self._check_open()

        if not 0 <= channel <= 15:
            raise ValueError("Channel must be between 0 and 15")

        # 允许 12 位计数，或恰好等于 full on/off 控制位
        for name, value in (("ON", on_count), ("OFF", off_count)):
            if not (0 <= value <= self._FULL_RANGE or value == self._FULL_ON):
                raise ValueError(f"Invalid {name} count {value}")

        base = self._LED0_ON_L + 4 * channel

        # 4 个连续寄存器一次写完（原来 4 次 I2C 事务，16 通道全刷慢 4 倍）
        self.bus.write_i2c_block_data(self.addr, base, [
            on_count & 0xFF,
            (on_count >> 8) & 0x1F,
            off_count & 0xFF,
            (off_count >> 8) & 0x1F,
        ])

    def set_duty_cycle(self, channel, value):
        """Set channel duty cycle using Adafruit-compatible 16-bit input."""
        self._check_open()

        if not 0 <= channel <= 15:
            raise ValueError("Channel must be between 0 and 15")

        if not 0 <= value <= 0xFFFF:
            raise ValueError("Duty cycle must be between 0 and 65535")

        if value == 0xFFFF:
            # FULL_ON
            self.set_pwm(channel, self._FULL_ON, 0)

        elif value < 0x0010:
            # FULL_OFF
            self.set_pwm(channel, 0, self._FULL_OFF)

        else:
            # Convert 16-bit duty cycle to 12-bit PWM count.
            pwm_value = value >> 4
            self.set_pwm(channel, 0, pwm_value)

    def deinit(self):
        """Turn off all PWM outputs and close I2C. Safe to call twice."""
        if self._closed:
            return

        for ch in range(16):
            self.set_pwm(ch, 0, self._FULL_OFF)

        self._closed = True
        self._channel_owners.clear()
        self.bus.close()

    def close(self):
        """Alias of deinit(), keeps the lifecycle naming consistent."""
        self.deinit()
