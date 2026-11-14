#!/usr/bin/env python3
import subprocess
from gpiozero import LED


class OnBoardLED:
    """
    Robot HAT V3.4 uses LED pins 9, 25, 11; V3.5 and later versions use 16, 25, 26.
    """
    _LED_PIN_CONFIG = {
        1: [9, 16],
        2: [25],
        3: [11, 26]
    }

    def __init__(self):
        self._leds = {}
        self._setup()

    def _gpioinfo_line(self, gpio):
        """Get gpioinfo output line for specified GPIO"""
        try:
            result = subprocess.run(["gpioinfo"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=2)
            if result.returncode != 0:
                return None

            gpio_name = f'"GPIO{gpio}"'
            for line in result.stdout.splitlines():
                if gpio_name in line:
                    return line.strip()
        except Exception:
            pass
        return None

    def _gpio_kernel_busy(self, gpio):
        """Check if GPIO is occupied by kernel/spi driver"""
        line = self._gpioinfo_line(gpio)
        if line is None:
            return False
        return 'consumer="kernel"' in line or 'consumer="spi' in line

    def _create_led(self, gpio):
        """Create single LED instance, return None on failure"""
        if self._gpio_kernel_busy(gpio):
            return None
        try:
            led = LED(gpio)
            print(f"GPIO{gpio} LED init OK")
            return led
        except Exception:
            return None

    def _setup(self):
        """Initialize all LEDs with pin fallback logic"""
        for port, pins in self._LED_PIN_CONFIG.items():
            led_obj = None
            for pin in pins:
                led_obj = self._create_led(pin)
                if led_obj is not None:
                    break
            self._leds[port] = led_obj

    def set_led(self, port, status):
        """
        Control single LED
        :param port: LED port number (1 / 2 / 3)
        :param status: 1 = ON, 0 = OFF
        """
        led = self._leds.get(port)
        if led is None:
            return

        if status == 1:
            led.on()
        elif status == 0:
            led.off()

    def turn_all_off(self):
        """Turn off all LEDs"""
        for port in self._leds:
            self.set_led(port, 0)

    def is_available(self, port):
        """Check if specified LED port is initialized successfully"""
        return self._leds.get(port) is not None

    def close(self):
        """Release all LED resources"""
        for port, led in self._leds.items():
            if led is not None:
                try:
                    led.close()
                except Exception:
                    pass
        self._leds.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


if __name__ == "__main__":
    import time

    with OnBoardLED() as led_board:
        try:
            while True:
                led_board.set_led(1, 1)
                time.sleep(1)

                led_board.set_led(2, 1)
                time.sleep(1)

                led_board.set_led(3, 1)
                time.sleep(1)

                led_board.turn_all_off()
                time.sleep(1)

        except KeyboardInterrupt:
            pass
