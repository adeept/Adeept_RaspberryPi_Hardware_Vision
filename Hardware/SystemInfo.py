#!/usr/bin/env python3
# File name   : SystemInfo.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
Raspberry Pi hardware / system information reader.
Dependencies: psutil (``sudo apt install python3-psutil``).
"""
import os
import re
import shutil
import subprocess
import time
from collections import namedtuple

__all__ = ["SystemInfo", "SystemState"]

THERMAL_FILE = "/sys/class/thermal/thermal_zone{zone}/temp"

VCGENCMD_CANDIDATES = ("vcgencmd", "/usr/bin/vcgencmd", "/opt/vc/bin/vcgencmd")

_TEMP_PATTERN = re.compile(r"temp=(\d+(?:\.\d+)?)")

SystemState = namedtuple(
    "SystemState",
    ["cpu_temp", "gpu_temp", "cpu_usage", "ram_usage", "swap_usage",
     "disk_usage", "uptime", "load_average"],
)


class SystemInfo:
    """
    Read Raspberry Pi hardware and operating system metrics.

    :param thermal_zone: Thermal zone index for the CPU temperature, default 0
    :param vcgencmd_path: Explicit vcgencmd path, auto-detected when None
    :param cpu_sample_interval: Blocking sample window in seconds used for the
                                very first CPU reading, 0 disables priming
    """

    # vcgencmd get_throttled 
    THROTTLE_FLAGS = {
        0: "under_voltage",
        1: "frequency_capped",
        2: "throttled",
        3: "soft_temp_limit",
        16: "under_voltage_occurred",
        17: "frequency_capped_occurred",
        18: "throttled_occurred",
        19: "soft_temp_limit_occurred",
    }

    def __init__(self, thermal_zone=0, vcgencmd_path=None, cpu_sample_interval=0.1):
        if thermal_zone < 0:
            raise ValueError("thermal_zone must be greater than or equal to zero")

        self.thermal_zone = thermal_zone
        self.vcgencmd_path = vcgencmd_path or self._find_vcgencmd()
        self.cpu_sample_interval = max(cpu_sample_interval, 0.0)
        self._cpu_primed = False

    @staticmethod
    def _find_vcgencmd():
        for candidate in VCGENCMD_CANDIDATES:
            path = shutil.which(candidate)
            if path:
                return path
        return None

    @property
    def psutil(self):
        try:
            import psutil
        except ImportError as error:
            raise RuntimeError(
                "psutil is required for usage metrics, "
                "install it with: sudo apt install python3-psutil"
            ) from error
        return psutil

    @staticmethod
    def model():
        """
        Board model as reported by the device tree.
        :return: e.g. "Raspberry Pi 4 Model B Rev 1.4", or None off a Pi
        """
        try:
            with open("/proc/device-tree/model", "r", encoding="utf-8", errors="ignore") as f:
                return f.read().strip("\x00\n ")
        except OSError:
            return None

    def cpu_temperature(self):
        """
        CPU temperature read from the thermal zone.
        :return: Temperature in degrees Celsius, or None when unavailable
        """
        path = THERMAL_FILE.format(zone=self.thermal_zone)
        try:
            with open(path, "r", encoding="utf-8") as f:
                value = float(f.read().strip())
        except (OSError, ValueError):
            return None

        if value > 1000:
            value /= 1000.0
        return round(value, 1)

    def gpu_temperature(self):
        """
        GPU temperature from ``vcgencmd measure_temp``.
        """
        if not self.vcgencmd_path:
            return None

        try:
            result = subprocess.run(
                [self.vcgencmd_path, "measure_temp"],
                capture_output=True, text=True, timeout=2, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        match = _TEMP_PATTERN.search(result.stdout)
        return round(float(match.group(1)), 1) if match else None

    def throttled(self):
        """
        Decode the throttling / under-voltage state from ``vcgencmd get_throttled``.
        :return: dict of flag name -> bool plus the raw value, or None when unavailable
        """
        if not self.vcgencmd_path:
            return None

        try:
            result = subprocess.run(
                [self.vcgencmd_path, "get_throttled"],
                capture_output=True, text=True, timeout=2, check=False,
            )
            raw = int(result.stdout.strip().split("=")[-1], 16)
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            return None

        state = {name: bool(raw & (1 << bit)) for bit, name in self.THROTTLE_FLAGS.items()}
        state["raw"] = raw
        return state

    def cpu_usage(self, interval=None):
        """
        CPU utilisation, all cores combined.
        :param interval: Blocking sample window in seconds, None reads the delta
                         since the previous call
        :return: Usage percentage, 0-100
        """
        if interval is None and not self._cpu_primed:
            interval = self.cpu_sample_interval

        percent = self.psutil.cpu_percent(interval=interval)
        self._cpu_primed = True
        return round(percent, 1)

    def ram_usage(self):
        """
        Physical memory utilisation.
        :return: Usage percentage, 0-100
        """
        return round(self.psutil.virtual_memory().percent, 1)

    def swap_usage(self):
        """
        Swap utilisation.
        :return: Usage percentage, 0-100
        """
        return round(self.psutil.swap_memory().percent, 1)

    def disk_usage(self, path="/"):
        """
        Filesystem utilisation of the partition holding ``path``.
        :param path: Mount point or any file inside the partition, default "/"
        :return: Usage percentage, 0-100
        """
        return round(self.psutil.disk_usage(path).percent, 1)

    def uptime(self):
        """
        Time since boot.
        :return: Uptime in seconds
        """
        return round(time.time() - self.psutil.boot_time())

    def load_average(self):
        """
        1 minute load average.
        :return: Load average, or None when the kernel does not report it
        """
        try:
            return round(os.getloadavg()[0], 2)
        except (OSError, AttributeError):
            return None

    def read(self):
        """
        Collect every metric into one snapshot.
        :return: SystemState(cpu_temp, gpu_temp, cpu_usage, ram_usage,
                 swap_usage, disk_usage, uptime, load_average)
        """
        return SystemState(
            cpu_temp=self.cpu_temperature(),
            gpu_temp=self.gpu_temperature(),
            cpu_usage=self.cpu_usage(),
            ram_usage=self.ram_usage(),
            swap_usage=self.swap_usage(),
            disk_usage=self.disk_usage(),
            uptime=self.uptime(),
            load_average=self.load_average(),
        )

    def as_dict(self):
        """
        Snapshot as a plain mapping, ready for JSON responses.
        :return: dict with the SystemState field names as keys
        """
        return self.read()._asdict()

    def __str__(self):
        state = self.read()
        return (
            f"CPU {state.cpu_temp} C | GPU {state.gpu_temp} C | "
            f"CPU {state.cpu_usage} % | RAM {state.ram_usage} % | "
            f"SWAP {state.swap_usage} % | DISK {state.disk_usage} %"
        )


def _print_state(info):
    state = info.read()

    print(f"CPU temperature: {state.cpu_temp} C")
    print(f"GPU temperature: {state.gpu_temp} C")
    print(f"CPU usage      : {state.cpu_usage} %")
    print(f"RAM usage      : {state.ram_usage} %")
    print(f"Swap usage     : {state.swap_usage} %")
    print(f"Disk usage     : {state.disk_usage} %")
    print(f"Uptime         : {state.uptime} s")
    print(f"Load average   : {state.load_average}")

    throttled = info.throttled()
    if throttled and throttled["under_voltage"]:
        print("Warning! Under-voltage detected. Please check the power supply!")
    print("-" * 40)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Raspberry Pi system information test")
    parser.add_argument("--once", action="store_true", help="print one snapshot and exit")
    parser.add_argument("--interval", type=float, default=1.0, help="refresh interval in seconds, default 1")
    args = parser.parse_args()

    print("System information test started.")
    print("-" * 40)

    info = SystemInfo()
    print(f"Board: {info.model()}")
    print("-" * 40)

    try:
        if args.once:
            _print_state(info)
        else:
            while True:
                # 单次采样，所有读数来自同一时刻
                _print_state(info)
                time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\nTest stopped by user.")
