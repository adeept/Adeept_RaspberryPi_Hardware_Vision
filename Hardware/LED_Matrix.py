#!/usr/bin/env python3
# File name   : LED_Matrix.py
# Website     : www.Adeept.com
# Author      : Adeept

import time
from smbus2 import SMBus


class HT16K33Matrix:
    """
    Reusable driver class for HT16K33-based 8x8 LED matrix.
    Can be imported and called from external projects.
    """
    # Built-in pattern: smiley face
    PATTERN_SMILE = bytes([
        0x00, 0x00, 0x04, 0x02, 0x02, 0x24, 0x40, 0x40,
        0x40, 0x40, 0x24, 0x02, 0x02, 0x04, 0x00, 0x00,
    ])

    def __init__(self, i2c_bus: int = 1, address: int = 0x70, brightness: int = 15):
        """
        Initialize the LED matrix module.
        :param i2c_bus:    I2C bus number, default 1 for Raspberry Pi
        :param address:    I2C device address, default 0x70
        :param brightness: Display brightness, range 0 ~ 15, default 15 (max)
        """
        self.bus = SMBus(i2c_bus)
        self.addr = address
        self._chip_init(brightness)
        self.clear()

    def _chip_init(self, brightness: int):
        """Internal HT16K33 chip initialization"""
        # Turn on internal oscillator
        self.bus.write_byte(self.addr, 0x21)
        # Enable display, disable blinking
        self.bus.write_byte(self.addr, 0x81)
        self.set_brightness(brightness)

    def set_brightness(self, brightness: int):
        """Set display brightness, range 0 ~ 15"""
        brightness = max(0, min(15, int(brightness)))
        # 0xE0 ~ 0xEF corresponds to level 0 ~ 15
        self.bus.write_byte(self.addr, 0xE0 | brightness)

    def clear(self):
        """Clear all pixels on the matrix"""
        self.bus.write_i2c_block_data(self.addr, 0x00, [0] * 16)

    def display_pattern(self, pattern: bytes):
        """
        Display a custom 8x8 bitmap pattern.
        :param pattern: 16-byte bitmap data for 8x8 matrix
        """
        if len(pattern) != 16:
            raise ValueError("Pattern data must be exactly 16 bytes for 8x8 matrix")

        # Reorganize data into HT16K33 memory layout
        display_data = []
        for i in range(8):
            display_data.append(pattern[i])
            display_data.append(pattern[i + 8])
        self.bus.write_i2c_block_data(self.addr, 0x00, display_data)

    def close(self):
        """Release resources: blank the display, stop the oscillator, close I2C"""
        try:
            self.clear()
            # 关振荡器顺手熄灭显示，避免断开后残留点亮
            self.bus.write_byte(self.addr, 0x20)
        finally:
            self.bus.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


if __name__ == "__main__":
    # Example 1: Basic usage -- show smiley pattern
    print("Displaying smiley pattern...")
    matrix = HT16K33Matrix()
    matrix.display_pattern(HT16K33Matrix.PATTERN_SMILE)
    time.sleep(2)
    matrix.clear()
    time.sleep(0.5)

    # Example 2: Loop display with graceful Ctrl+C exit
    print("Running loop. Press Ctrl+C to stop.")
    try:
        while True:
            matrix.display_pattern(HT16K33Matrix.PATTERN_SMILE)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
    finally:
        matrix.close()
        print("LED matrix stopped safely.")

    # Example 3: Recommended -- use 'with' for auto cleanup
    # with HT16K33Matrix(brightness=10) as mat:
    #     mat.display_pattern(HT16K33Matrix.PATTERN_SMILE)
    #     time.sleep(2)
    # # Resources are released automatically when exiting the block
