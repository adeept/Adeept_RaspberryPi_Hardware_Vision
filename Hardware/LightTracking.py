#!/usr/bin/env python3
# File name   : light_tracking.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
Single-channel light tracking module based on ADS7830 ADC.
Reads brightness value from channel A1 by default.
"""
import time
from .ads7830 import ADS7830


class LightTracking:
    """
    Single-channel photosensitive sensor controller.
    :param channel: ADC channel for light sensor, default 1 (A1)
    :param bus_num: I2C bus number, default 1
    :param address: ADS7830 I2C address, default 0x48
    :param adc_device: Optional pre-initialized ADS7830 instance for hardware sharing
    """

    def __init__(self, channel=1, bus_num=1, address=0x48, adc_device=None):
        if adc_device is not None:
            # Reuse existing ADC instance to avoid duplicate I2C initialization
            self._adc = adc_device
            self._shared_adc = True
        else:
            self._adc = ADS7830(bus_num=bus_num, address=address)
            self._shared_adc = False

        self.channel = channel

    def read(self):
        """
        Read current brightness value.
        :return: Brightness raw value, range 0-255
        """
        return self._adc.analog_read(self.channel)

    def close(self):
        """Release resources; only closes ADC if not shared"""
        if not self._shared_adc:
            try:
                self._adc.close()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


if __name__ == "__main__":
    print("Single-channel light tracking test started.")
    print("Reading from channel A1, value range: 0-255")

    with LightTracking(channel=1) as sensor:
        try:
            while True:
                value = sensor.read()
                print(f"Light Tracking Value: {value}")
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nTest stopped by user.")
