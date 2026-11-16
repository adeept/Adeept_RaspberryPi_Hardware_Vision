#!/usr/bin/env python3
# File name   : ads7830.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
ADS7830 8-channel 8-bit ADC driver based on I2C / smbus.
General purpose analog-to-digital conversion, reusable for light tracking, voltage sensing, etc.
"""
import smbus


class ADS7830:
    """
    ADS7830 I2C analog-to-digital converter.
    :param bus_num: I2C bus number, default 1 for Raspberry Pi
    :param address: I2C device address, default 0x48
    """

    def __init__(self, bus_num=1, address=0x48):
        self._cmd = 0x84  # Single-ended input, internal reference voltage
        self._bus = smbus.SMBus(bus_num)
        self._address = address

    def analog_read(self, channel):
        """
        Read ADC value from specified channel.
        :param channel: ADC input channel 0-7
        :return: 8-bit conversion result, range 0-255
        :raise ValueError: channel is not an integer in 0-7
        """
        if not isinstance(channel, int) or isinstance(channel, bool) or not 0 <= channel <= 7:
            # 静默钳位会让接错线表现为"读到别的通道数据"，这里直接报错
            raise ValueError(f"ADC channel must be an integer in 0-7, got {channel!r}")
        reg = self._cmd | (((channel << 2 | channel >> 1) & 0x07) << 4)
        return self._bus.read_byte_data(self._address, reg)

    def analogRead(self, channel):
        return self.analog_read(channel)

    def close(self):
        """Close I2C bus and release resources"""
        try:
            self._bus.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


if __name__ == "__main__":
    import time
    print("ADS7830 single channel test (channel 1)")
    with ADS7830() as adc:
        try:
            while True:
                val = adc.analog_read(1)
                print(f"Light Tracking Value: {val}")
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nTest stopped.")
