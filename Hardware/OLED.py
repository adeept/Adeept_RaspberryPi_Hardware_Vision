#!/usr/bin/env python3
# File name   : OLED.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
SSD1306 OLED display driver based on luma.oled library.
128x64 I2C interface, supports centered text wrapping and custom graphics.
"""
import datetime
import time

from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from PIL import Image, ImageDraw, ImageFont


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

    _FALLBACK_FONTS = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    )

    def __init__(self, i2c_port=1, i2c_address=0x3C, width=128, height=64,
                 font_path="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 font_size=16):
        # Initialize I2C bus and OLED device
        self._serial = i2c(port=i2c_port, address=i2c_address)
        self.device = ssd1306(self._serial, width=width, height=height)
        self.width = width
        self.height = height
        self._closed = False

        self.font = self._load_font(font_path, font_size)
        self._font_path = font_path

    def _load_font(self, font_path, font_size):
        """Try the requested font first, then the fallbacks, then Pillow's builtin."""
        candidates = [font_path] if font_path else []
        candidates.extend(self._FALLBACK_FONTS)

        for path in candidates:
            try:
                return ImageFont.truetype(path, font_size)
            except Exception:
                continue

        # Pillow >= 10.1 才支持 size 参数，更老的版本要退回默认字号
        try:
            return ImageFont.load_default(size=font_size)
        except TypeError:
            return ImageFont.load_default()

    @staticmethod
    def _is_wide(char):
        """Whether the char is a wide glyph (CJK, full-width punctuation)."""
        code = ord(char)
        return (0x1100 <= code <= 0x115F or 0x2E80 <= code <= 0xA4CF
                or 0xAC00 <= code <= 0xD7A3 or 0xF900 <= code <= 0xFAFF
                or 0xFE30 <= code <= 0xFE6F or 0xFF00 <= code <= 0xFF60
                or 0xFFE0 <= code <= 0xFFE6)

    @classmethod
    def _tokenize(cls, text):
        """Split a paragraph into layout units: single CJK chars, whole ASCII words."""
        tokens, buffer = [], ""
        for char in text:
            if char.isspace():
                if buffer:
                    tokens.append(buffer)
                    buffer = ""
                continue
            if cls._is_wide(char):
                if buffer:
                    tokens.append(buffer)
                    buffer = ""
                tokens.append(char)
            else:
                buffer += char
        if buffer:
            tokens.append(buffer)
        return tokens

    @classmethod
    def _join(cls, current, token):
        """Join two units, inserting a space only between two narrow (ASCII) units."""
        if not current:
            return token
        if cls._is_wide(current[-1]) or cls._is_wide(token[0]):
            return current + token
        return current + " " + token

    def _wrap_text(self, draw, text, font, max_width):
        """
        Wrap text to max_width.
        ASCII words are kept whole; CJK has no spaces, so it wraps per character —
        otherwise a long Chinese string would never break and run off the screen.
        """
        lines = []
        for paragraph in text.splitlines() or [""]:
            current = ""
            for token in self._tokenize(paragraph):
                candidate = self._join(current, token)
                if draw.textlength(candidate, font=font) <= max_width:
                    current = candidate
                    continue

                if current:
                    lines.append(current)

                # 单个单词本身就超宽时按字符硬切
                while draw.textlength(token, font=font) > max_width and len(token) > 1:
                    cut = len(token) - 1
                    while cut > 1 and draw.textlength(token[:cut], font=font) > max_width:
                        cut -= 1
                    lines.append(token[:cut])
                    token = token[cut:]

                current = token

            lines.append(current)

        return [line for line in lines if line] or [""]

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

        ascent, descent = font.getmetrics()
        line_height = ascent + descent

        for line in self._wrap_text(draw, text, font, max_width):
            line_w = draw.textlength(line, font=font)
            x = max(0, int((self.width - line_w) // 2))
            draw.text((x, y), line, font=font, fill=fill)
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
        :param text: Text content (auto line break, explicit '\\n' is respected)
        :param y_start: Starting Y coordinate
        """
        image, draw = self.new_canvas()
        self.draw_centered_text(draw, text, y_start)
        self.display(image)

    def show_lines(self, lines, font_size=10, line_height=10, x=2, y_start=0):
        """Render fixed lines without wrapping, for compact status pages."""
        font = self._load_font(self._font_path, font_size)
        image, draw = self.new_canvas()
        for index, text in enumerate(lines):
            draw.text((x, y_start + index * line_height), text, font=font, fill=255)
        self.display(image)

    def close(self):
        """Clear screen and release display resources. Safe to call twice."""
        if self._closed:
            return
        self._closed = True

        try:
            self.clear()
        except Exception:
            pass

        # luma 的 cleanup 在不同版本上不一定存在，按可用性调用
        for obj in (self.device, self._serial):
            cleanup = getattr(obj, "cleanup", None)
            if callable(cleanup):
                try:
                    cleanup()
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
