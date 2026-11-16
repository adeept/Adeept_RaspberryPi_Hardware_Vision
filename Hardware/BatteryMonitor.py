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
from collections import namedtuple

from .ads7830 import ADS7830


# 一次采样得到的完整快照，避免多次读 ADC 导致三个读数来自不同时刻
BatteryState = namedtuple("BatteryState", ["raw", "voltage", "percent", "is_low"])


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
    :param ocv_table: Optional ((voltage, percent), ...) table for the pack, descending
    """

    # 2 节锂电池静置电压 -> 剩余电量（分段线性）。
    # 线性插值会把 7.6V（约 55%）显示成 20% 左右，所以按放电曲线查表。
    DEFAULT_OCV_TABLE = (
        (8.40, 100.0),
        (8.10, 90.0),
        (7.90, 75.0),
        (7.70, 60.0),
        (7.50, 45.0),
        (7.30, 30.0),
        (7.10, 15.0),
        (6.90, 5.0),
        (6.60, 0.0),
    )

    def __init__(self, channel=0, bus_num=1, address=0x48, adc_device=None, adc_vref=5.25,
                 full_voltage=8.4, warning_threshold=6.8, r_upper=10, r_lower=10, ocv_table=None):
        if adc_device is not None:
            # Reuse existing ADC instance to avoid duplicate I2C initialization
            self._adc = adc_device
            self._shared_adc = True
        else:
            self._adc = ADS7830(bus_num=bus_num, address=address)
            self._shared_adc = False

        if r_upper + r_lower <= 0:
            raise ValueError("r_upper + r_lower must be greater than zero")

        self.channel = channel
        self.adc_vref = adc_vref
        self.full_voltage = full_voltage
        self.warning_threshold = warning_threshold

        # Calculate voltage divider ratio
        self._division_ratio = r_lower / (r_upper + r_lower)
        self._ocv_table = tuple(ocv_table) if ocv_table is not None else self.DEFAULT_OCV_TABLE

    def read_raw(self):
        """Read raw ADC value, range 0-255"""
        return self._adc.analog_read(self.channel)

    def _raw_to_voltage(self, raw):
        """换算单个 ADC 采样对应的电池电压"""
        adc_voltage = (raw / 255.0) * self.adc_vref
        return adc_voltage / self._division_ratio

    def _percent_from_voltage(self, voltage):
        """按放电曲线换算电量百分比；超出表范围时钳到 0 / 100"""
        table = self._ocv_table
        if voltage >= table[0][0]:
            return 100.0
        if voltage <= table[-1][0]:
            return 0.0
        for (v_high, p_high), (v_low, p_low) in zip(table, table[1:]):
            if v_low <= voltage <= v_high:
                ratio = (voltage - v_low) / (v_high - v_low)
                return p_low + ratio * (p_high - p_low)
        return 0.0

    def read(self):
        """
        Read one ADC sample and return a consistent snapshot.

        :return: BatteryState(raw, voltage, percent, is_low)
        """
        raw = self.read_raw()
        voltage = self._raw_to_voltage(raw)
        percent = self._percent_from_voltage(voltage)
        return BatteryState(raw, voltage, percent, voltage < self.warning_threshold)

    def read_voltage(self):
        """
        Calculate actual battery voltage.
        :return: Battery voltage in volts (V)
        """
        return self._raw_to_voltage(self.read_raw())

    def read_percentage(self):
        """
        Calculate battery state of charge.
        :return: Battery level percentage, range 0-100
        """
        return self._percent_from_voltage(self.read_voltage())

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
                # 单次采样，raw / voltage / percent 来自同一时刻
                state = battery.read()

                print(f"ADC raw value: {state.raw}")
                print(f"Battery Voltage: {state.voltage:.2f} V")
                print(f"Battery Level: {state.percent:.2f} %")

                if state.is_low:
                    print("Warning! Low battery. Please charge in time!")
                print("-" * 40)
                time.sleep(0.5)

        except KeyboardInterrupt:
            print("\nTest stopped by user.")
