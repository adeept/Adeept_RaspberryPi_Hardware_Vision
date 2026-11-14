#!/usr/bin/env python3
# File name   : OLED.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
SSD1306 OLED display driver based on luma.oled library.
128x64 I2C interface, supports centered text wrapping and custom graphics.
"""
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from PIL import Image, ImageDraw, ImageFont
import datetime
import time


class OLED:
    """
    SSD1306 OLED display controller.
    :param i2c_port: I2C bus number, default 1
    :param i2c_address: I2C device address, default 0x3C
    :param width: Screen width in pixels, default 128
    :param height: Screen height in pixels, default 64
    :param font_path: Path to TTF font file
    :param font_size: Font size in pixels, default 16
    """

    def __init__(self, i2c_port=1, i2c_address=0x3C, width=128, height=64,
                 font_path="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 font_size=16):
        # Initialize I2C bus and OLED device
        serial = i2c(port=i2c_port, address=i2c_address)
        self.device = ssd1306(serial, width=width, height=height)
        self.width = width
        self.height = height

        try:
            self.font = ImageFont.truetype(font_path, font_size)
        except Exception:
            self.font = ImageFont.load_default(size=font_size)

    def draw_centered_text(self, draw, text, y, fill=255, max_width=None, font=None):
        """
        Draw word-wrapped text horizontally centered on the canvas.
        :param draw: PIL ImageDraw object
        :param text: Text content to draw
        :param y: Starting Y coordinate
        :param fill: Pixel fill value, default 255 (white on 1-bit screen)
        :param max_width: Maximum text width, default screen width - 4
        :param font: Font to use, default class global font
        :return: Y coordinate after the last line
        """
        if font is None:
            font = self.font
        if max_width is None:
            max_width = self.width - 4

        lines = []
        current_line = ""
        for word in text.split():
            test_line = current_line + word + " "
            test_width = draw.textlength(test_line, font=font)
            if test_width <= max_width:
                current_line = test_line
            else:
                lines.append(current_line.rstrip())
                current_line = word + " "
        if current_line:
            lines.append(current_line.rstrip())

        for line in lines:
            line_w = draw.textlength(line, font=font)
            x = (self.width - line_w) // 2
            draw.text((x, y), line, font=font, fill=fill)
            _, _, _, line_height = font.getbbox(line)
            y += line_height
        return y

    def new_canvas(self):
        """Create a blank 1-bit image and matching draw object for custom graphics"""
        image = Image.new('1', (self.width, self.height))
        draw = ImageDraw.Draw(image)
        return image, draw

    def display(self, image):
        """Render a PIL image to the OLED screen"""
        self.device.display(image)

    def clear(self):
        """Clear the entire screen"""
        self.device.clear()

    def show_text(self, text, y_start=8):
        """
        Quick method: directly display centered wrapped text on screen.
        :param text: Text content (auto line break by word)
        :param y_start: Starting Y coordinate
        """
        image, draw = self.new_canvas()
        self.draw_centered_text(draw, text, y_start)
        self.display(image)

    def close(self):
        """Clear screen and release display resources"""
        try:
            self.clear()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


if __name__ == "__main__":
    print("OLED display test started.")
    with OLED() as oled:
        try:
            # Test 1: Static centered text
            print("Test 1: Static text display")
            oled.show_text("Adeept Robot\nOLED Demo")
            time.sleep(3)

            # Test 2: Real-time clock (same behavior as original code)
            print("Test 2: Real-time clock")
            while True:
                image, draw = oled.new_canvas()
                now = datetime.datetime.now()
                date_text = now.strftime("%Y-%m-%d")
                time_text = now.strftime("%H:%M:%S")

                oled.draw_centered_text(draw, date_text, 8)
                oled.draw_centered_text(draw, time_text, 32)
                oled.display(image)
                time.sleep(1)

        except KeyboardInterrupt:
            print("\nTest stopped by user.")
