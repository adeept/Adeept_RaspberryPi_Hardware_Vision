#!/usr/bin/env python3
# File name   : ws2812.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
WS2812 addressable LED driver based on SPI bus.
Compatible with Raspberry Pi 3/4/5.
"""
import time
import sys
import subprocess
import threading
import spidev
import numpy as np

# ===================== Preset Color =====================
BASE_COLORS = [
    (0, 255, 255),
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (255, 255, 0),
    (255, 0, 255),
    (0, 128, 255),
    (192, 192, 192),
    (192, 192, 0),
    (128, 128, 128),
    (128, 0, 0),
    (128, 128, 0),
    (0, 128, 0),
    (0, 128, 128)
]

def generate_color_sequences():
    """Generate cyclic color shift sequences for marquee effect"""
    return [BASE_COLORS[i:] + BASE_COLORS[:i] for i in range(len(BASE_COLORS))]

# ===================== WS2812 Driver Class =====================
class WS2812(threading.Thread):
    """
    SPI-driven WS2812 LED controller.
    :param count: Number of LED pixels
    :param bright: Global brightness, 0-255
    :param sequence: Color order, default GRB (standard for WS2812)
    :param bus: SPI bus number, default 0
    :param device: SPI chip select number, default 0
    """

    def __init__(self, count=8, bright=255, sequence='GRB', bus=0, device=0):
        super().__init__(daemon=True)

        self.led_count = count
        self.led_brightness = bright
        self.light_mode = "none"

        # Breath effect parameters
        self._breath_r = self._breath_g = self._breath_b = 0
        self.breath_steps = 10

        # Color order parsing
        self._parse_color_order(sequence)
        # Initialize color buffer
        self._reset_color_buffer()
        # Initialize SPI hardware
        self._spi_init(bus, device)

        # Thread control event
        self._event = threading.Event()
        self._event.clear()

        # Turn off all LEDs on init
        self.set_all_color(0, 0, 0)

    def _parse_color_order(self, rgb_type):
        """Map color order string to channel offsets"""
        mapping = {
            "RGB": 0x06, "RBG": 0x09,
            "GRB": 0x12, "GBR": 0x21,
            "BRG": 0x18, "BGR": 0x24
        }
        val = mapping.get(rgb_type, 0x12)
        self._red_offset = (val >> 4) & 0x03
        self._green_offset = (val >> 2) & 0x03
        self._blue_offset = val & 0x03

    def _reset_color_buffer(self):
        """Initialize color buffer arrays"""
        self._color_buf = [0, 0, 0] * self.led_count
        self._original_color = [0, 0, 0] * self.led_count

    def _spi_init(self, bus, device):
        """Initialize SPI peripheral"""
        self._bus = bus
        self._device = device
        self.spi = None
        self.init_ok = 0

        try:
            self.spi = spidev.SpiDev()
            self.spi.open(bus, device)
            self.spi.mode = 0
            self.init_ok = 1
        except OSError:
            print("SPI init failed. Check /boot/firmware/config.txt")
            if bus == 0:
                print("Enable SPI: raspi-config or add dtparam=spi=on")
            else:
                print(f"Add dtoverlay=spi{bus}-2cs then reboot")

    def is_ready(self):
        """Check if SPI and LEDs are initialized successfully"""
        return self.init_ok == 1

    def set_brightness(self, bright):
        """Dynamically adjust global brightness and refresh immediately"""
        bright = max(0, min(255, bright))
        self.led_brightness = bright
        # Re-apply all colors with new brightness
        for i in range(self.led_count):
            base_idx = i * 3
            r = self._original_color[base_idx + self._red_offset]
            g = self._original_color[base_idx + self._green_offset]
            b = self._original_color[base_idx + self._blue_offset]
            self.set_pixel(i, r, g, b)
        self.show()

    def set_pixel(self, index, r, g, b):
        """Set single pixel color to buffer (no refresh)"""
        if index < 0 or index >= self.led_count:
            return

        pixel = [0, 0, 0]
        pixel[self._red_offset] = round(r * self.led_brightness / 255)
        pixel[self._green_offset] = round(g * self.led_brightness / 255)
        pixel[self._blue_offset] = round(b * self.led_brightness / 255)

        # Save original color (before brightness scaling)
        base_idx = index * 3
        self._original_color[base_idx + self._red_offset] = r
        self._original_color[base_idx + self._green_offset] = g
        self._original_color[base_idx + self._blue_offset] = b
        # Update display buffer
        self._color_buf[base_idx:base_idx + 3] = pixel

    def set_pixel_color(self, index, r, g, b):
        """Set single pixel color and refresh immediately"""
        self.set_pixel(index, r, g, b)
        self.show()

    def set_all_color(self, r, g, b):
        """Set all pixels to the same color and refresh"""
        for i in range(self.led_count):
            self.set_pixel(i, r, g, b)
        self.show()

    def set_multi_colors(self, colors):
        """
        Set multiple pixels to different colors and refresh.
        :param colors: List of (R, G, B) tuples
        """
        for i, color in enumerate(colors[:self.led_count]):
            self.set_pixel(i, *color)
        self.show()

    def show(self, mode=1):
        """Refresh LED display via SPI"""
        if not self.init_ok:
            return

        data = np.array(self._color_buf).ravel()

        if mode == 1:
            # 8-bit timing encoding
            tx = np.zeros(len(data) * 8, dtype=np.uint8)
            for ibit in range(8):
                tx[7 - ibit::8] = ((data >> ibit) & 1) * 0x78 + 0x80
            speed = int(8 / 1.25e-6) if self._bus == 0 else int(8 / 1.0e-6)
        else:
            # 4-bit timing encoding
            tx = np.zeros(len(data) * 4, dtype=np.uint8)
            for ibit in range(4):
                tx[3 - ibit::4] = (
                    ((data >> (2 * ibit + 1)) & 1) * 0x60
                    + ((data >> (2 * ibit + 0)) & 1) * 0x06
                    + 0x88
                )
            speed = int(4 / 1.25e-6) if self._bus == 0 else int(4 / 1.0e-6)

        self.spi.xfer(tx.tolist(), speed)

    # ===================== Animation Control =====================
    def start_breath(self, r, g, b):
        """Start breathing light animation (background thread)"""
        self.light_mode = "breath"
        self._breath_r, self._breath_g, self._breath_b = r, g, b
        self._event.set()

    def start_police(self):
        """Start police flash animation (background thread)"""
        self.light_mode = "police"
        self._event.set()

    def stop_animation(self):
        """Stop animation, keep current color"""
        self.light_mode = "none"
        self._event.clear()

    def pause(self):
        """Stop animation and turn off all LEDs"""
        self.light_mode = "none"
        self.set_all_color(0, 0, 0)
        self._event.clear()

    # ===================== Animation Tasks =====================
    def _breath_task(self):
        while self.light_mode == "breath":
            # Fade in
            for i in range(self.breath_steps):
                ratio = i / self.breath_steps
                self.set_all_color(
                    self._breath_r * ratio,
                    self._breath_g * ratio,
                    self._breath_b * ratio
                )
                time.sleep(0.03)
            # Fade out
            for i in range(self.breath_steps):
                ratio = 1.0 - i / self.breath_steps
                self.set_all_color(
                    self._breath_r * ratio,
                    self._breath_g * ratio,
                    self._breath_b * ratio
                )
                time.sleep(0.03)

    def _police_task(self):
        while self.light_mode == "police":
            # Blue flash
            for _ in range(3):
                self.set_all_color(0, 0, 255)
                time.sleep(0.05)
                self.set_all_color(0, 0, 0)
                time.sleep(0.05)
            time.sleep(0.1)
            # Red flash
            for _ in range(3):
                self.set_all_color(255, 0, 0)
                time.sleep(0.05)
                self.set_all_color(0, 0, 0)
                time.sleep(0.05)
            time.sleep(0.1)

    def run(self):
        """Thread main loop"""
        while True:
            self._event.wait()
            if self.light_mode == "breath":
                self._breath_task()
            elif self.light_mode == "police":
                self._police_task()

    def close(self):
        """Turn off all LEDs and release SPI resources"""
        try:
            self.pause()
            if self.spi:
                self.spi.close()
        except Exception as e:
            print(f"WS2812 close error: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


if __name__ == '__main__':
    LED_COUNT = 14
    DEFAULT_BRIGHTNESS = 50
    color_sequences = generate_color_sequences()

    led_strip = WS2812(count=LED_COUNT, bright=DEFAULT_BRIGHTNESS)
    led_strip.start()

    try:
        if not led_strip.is_ready():
            print("WS2812 init failed, exit.")
            sys.exit(1)

        print("=== Test 1: Static white color ===")
        led_strip.set_all_color(255, 255, 255)
        time.sleep(2)

        print("=== Test 2: Blue breathing effect ===")
        led_strip.start_breath(0, 0, 255)
        time.sleep(4)
        led_strip.stop_animation()

        print("=== Test 3: Police flash effect ===")
        led_strip.start_police()
        time.sleep(4)
        led_strip.stop_animation()

        print("=== Test 4: Cyclic color marquee ===")
        while True:
            for seq in color_sequences:
                led_strip.set_multi_colors(seq)
                time.sleep(0.3)

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        led_strip.close()
        print("WS2812 resources released.")
        sys.exit(0)
