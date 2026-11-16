#!/usr/bin/env python3
# File name   : IRReceiver.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
NEC protocol IR receiver driver based on gpiozero.
Supports polling read and callback mode, with built-in key mapping.
"""
import threading
import time
from gpiozero import DigitalInputDevice


class IRReceiver:
    """
    IR remote control receiver with NEC protocol decoding.
    :param pin: GPIO pin number (BCM), default 12
    :param key_map: Custom key code to name mapping dict, use default if None
    :param tolerance: Timing tolerance ratio, default 0.5
    :param min_normal_pulses: Minimum pulse count for a valid frame
    :param repeat_pulses: Pulse count for repeat code

    Attributes:
        last_frame: (address, data) of the most recently decoded frame. Since every
            read consumes the pulse buffer, use this to get the raw code after read_key()
            for the same key press; repeated presses update it again.
    """

    REPEAT = "repeat"

    DEFAULT_KEY_MAP = {
        0xA2: "A",
        0x62: "B",
        0xE2: "C",
        0x22: "D",
        0x02: "UP",
        0xC2: "E",
        0xE0: "LEFT",
        0xA8: "OK",
        0x90: "RIGHT",
        0x68: "0",
        0x98: "DOWN",
        0xB0: "F",
        0x30: "1",
        0x18: "2",
        0x7A: "3",
        0x10: "4",
        0x38: "5",
        0x5A: "6",
        0x42: "7",
        0x4A: "8",
        0x52: "9"
    }

    def __init__(self, pin=12, key_map=None, tolerance=0.5, min_normal_pulses=20, repeat_pulses=25):
        self._pin = pin
        self.tolerance = tolerance
        self.min_normal_pulses = min_normal_pulses
        self.repeat_pulses = repeat_pulses
        self.key_map = key_map if key_map is not None else self.DEFAULT_KEY_MAP

        # Pulse timestamp buffer (level, timestamp_us)
        self._pulse_timestamps = []
        self._lock = threading.Lock()
        self.last_frame = None
        # Optional callback function for key press event
        self.on_key_press = None

        # Initialize IR receiver hardware
        self._device = DigitalInputDevice(
            pin=pin,
            pull_up=True,
            bounce_time=0.0003
        )
        # Attach edge interrupt callbacks
        self._device.when_activated = lambda: self._pulse_callback(1)
        self._device.when_deactivated = lambda: self._pulse_callback(0)

    def _pulse_callback(self, level):
        """Interrupt callback: record pulse edge timestamp in microseconds"""
        timestamp = time.time_ns() // 1000
        with self._lock:
            self._pulse_timestamps.append((level, timestamp))
            if len(self._pulse_timestamps) > 200:
                self._pulse_timestamps.pop(0)

    @staticmethod
    def _calculate_time_diff(t1, t2):
        """Calculate time difference between two edges (microseconds)"""
        return t2 - t1

    def _is_within_tolerance(self, measured, expected):
        """Check if measured timing is within tolerance range"""
        min_val = expected * (1 - self.tolerance)
        max_val = expected * (1 + self.tolerance)
        return min_val <= measured <= max_val

    def _decode_nec(self):
        """
        Decode NEC protocol from pulse buffer.
        :return: Tuple (address, data), or REPEAT constant, or None
        """
        if len(self._pulse_timestamps) < 4:
            return None

        with self._lock:
            pulses = self._pulse_timestamps.copy()
            self._pulse_timestamps.clear()
        pulse_count = len(pulses)

        if pulse_count == 4:
            return None
        if pulse_count < self.min_normal_pulses:
            return None
        if pulse_count <= self.repeat_pulses:
            return self.REPEAT

        t0, t1, t2 = [p[1] for p in pulses[:3]]
        hdr_mark = self._calculate_time_diff(t0, t1)
        hdr_space = self._calculate_time_diff(t1, t2)
        if not (self._is_within_tolerance(hdr_mark, 9000)
                and self._is_within_tolerance(hdr_space, 4500)):
            return None

        data_bits = []
        for i in range(2, pulse_count - 2, 2):
            t_prev = pulses[i][1]
            t_curr = pulses[i + 1][1]
            t_next = pulses[i + 2][1]

            bit_mark = self._calculate_time_diff(t_prev, t_curr)
            if not self._is_within_tolerance(bit_mark, 560):
                continue

            bit_space = self._calculate_time_diff(t_curr, t_next)
            if self._is_within_tolerance(bit_space, 1690):
                data_bits.append(1)
            elif self._is_within_tolerance(bit_space, 560):
                data_bits.append(0)

        if len(data_bits) < 32:
            return None

        address = int(''.join(map(str, data_bits[0:8])), 2)
        address_inv = int(''.join(map(str, data_bits[8:16])), 2)
        data = int(''.join(map(str, data_bits[16:24])), 2)
        data_inv = int(''.join(map(str, data_bits[24:32])), 2)

        if (address ^ address_inv) == 0xFF and (data ^ data_inv) == 0xFF:
            return (address, data)
        return None

    def read_raw(self):
        """
        Read raw decoded result.
        :return: (address, data) tuple, REPEAT constant, or None if no new frame
        """
        result = self._decode_nec()
        if isinstance(result, tuple):
            self.last_frame = result
        if result is not None and callable(self.on_key_press):
            # Trigger callback if set
            self.on_key_press(result)
        return result

    def read_key(self):
        """
        Read mapped key name.
        :return: Key name string, REPEAT constant, or None
        """
        raw = self.read_raw()
        if raw is None:
            return None
        if raw == self.REPEAT:
            return self.REPEAT
        _, data = raw
        return self.key_map.get(data, f"UNKNOWN_0x{data:02X}")

    def close(self):
        """Release GPIO resources and clear buffer"""
        try:
            self._device.close()
        except Exception:
            pass
        self._pulse_timestamps.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


if __name__ == "__main__":
    print("IR NEC receiver test started.")
    print("Press any key on the remote control.")
    print("Press Ctrl+C to exit.\n")

    # def on_key(result):
    #     if result == IRReceiver.REPEAT:
    #         print("[REPEAT]")
    #         return
    #     addr, data = result
    #     print(f"收到按键: addr=0x{addr:02X}, data=0x{data:02X}")

    # # 设置回调函数，有按键时自动触发
    # ir = IRReceiver()
    # ir.on_key_press = on_key

    with IRReceiver(pin=12) as ir:
        try:
            while True:
                time.sleep(0.3)
                key = ir.read_key()
                if key is None:
                    continue
                if key == IRReceiver.REPEAT:
                    print("[REPEAT]")
                    continue

                raw = ir.last_frame
                if isinstance(raw, tuple):
                    addr, dat = raw
                    print(f"ADDR: 0x{addr:02X} | DATA: 0x{dat:02X} | KEY: {key}")
                else:
                    print(f"KEY: {key}")

        except KeyboardInterrupt:
            print("\nTest stopped by user.")
