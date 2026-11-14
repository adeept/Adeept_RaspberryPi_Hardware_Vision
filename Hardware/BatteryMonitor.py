#!/usr/bin/env python3
# File name   : BatteryMonitor.py
# Website     : www.Adeept.com
# Author      : Adeept
# Description : Battery voltage and level monitoring based on ADS7830 ADC
"""
Battery voltage and level monitor based on ADS7830 ADC.
Reuses the common ads7830 driver, supports shared ADC hardware.
"""
import time
from .ads7830 import ADS7830


class BatteryMonitor:
    """
    Battery voltage and state of charge monitor.
    Default parameters match Adeept Robot HAT V3.5 voltage divider circuit.

    :param channel: ADC channel for battery sensing, default 0 (A0)
    :param bus_num: I2C bus number, default 1
    :param address: ADS7830 I2C address, default 0x48
    :param adc_device: Optional pre-initialized ADS7830 instance for hardware sharing
    :param adc_vref: ADC reference voltage in volts, default 5.25
    :param full_voltage: Fully charged battery voltage, default 8.4
    :param warning_threshold: Low battery warning threshold in volts, default 6.8
    :param r_upper: Upper resistor of voltage divider (kΩ), default 10
    :param r_lower: Lower resistor of voltage divider (kΩ), default 10
    """

    def __init__(self, channel=0, bus_num=1, address=0x48, adc_device=None, adc_vref=5.25, full_voltage=8.4, warning_threshold=6.8, r_upper=10, r_lower=10):
        if adc_device is not None:
            # Reuse existing ADC instance to avoid duplicate I2C initialization
            self._adc = adc_device
            self._shared_adc = True
        else:
            self._adc = ADS7830(bus_num=bus_num, address=address)
            self._shared_adc = False

        self.channel = channel
        self.adc_vref = adc_vref
        self.full_voltage = full_voltage
        self.warning_threshold = warning_threshold

        # Calculate voltage divider ratio
        self._division_ratio = r_lower / (r_upper + r_lower)

    def read_raw(self):
        """Read raw ADC value, range 0-255"""
        return self._adc.analog_read(self.channel)

    def read_voltage(self):
        """
        Calculate actual battery voltage.
        :return: Battery voltage in volts (V)
        """
        adc_value = self.read_raw()
        adc_voltage = (adc_value / 255.0) * self.adc_vref
        return adc_voltage / self._division_ratio

    def read_percentage(self):
        """
        Calculate battery state of charge.
        :return: Battery level percentage, range 0-100
        """
        voltage = self.read_voltage()
        percentage = (voltage - self.warning_threshold) / (self.full_voltage - self.warning_threshold) * 100
        return max(0.0, min(100.0, percentage))

    def is_low(self, threshold=None):
        """
        Check if battery is below warning threshold.
        :param threshold: Custom threshold in volts, uses default if None
        :return: True if low battery
        """
        if threshold is None:
            threshold = self.warning_threshold
        return self.read_voltage() < threshold

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
    print("Battery level monitoring test started.")
    print("-" * 40)

    with BatteryMonitor() as battery:
        try:
            while True:
                raw = battery.read_raw()
                voltage = battery.read_voltage()
                level = battery.read_percentage()

                print(f"ADC raw value: {raw}")
                print(f"Battery Voltage: {voltage:.2f} V")
                print(f"Battery Level: {level:.2f} %")

                if battery.is_low():
                    print("Warning! Low battery. Please charge in time!")
                print("-" * 40)
                time.sleep(0.5)

        except KeyboardInterrupt:
            print("\nTest stopped by user.")
