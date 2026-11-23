#!/usr/bin/env python3
import logging
import subprocess
from gpiozero import LED

logger = logging.getLogger(__name__)


class OnBoardLED:
    """
    Robot HAT V3.4 uses LED pins 9, 25, 11; V3.5 and later versions use 16, 25, 26.

    :param pin_config: Optional {port: [candidate pins]} mapping, default uses the
        built-in V3.4/V3.5 candidates. Each port takes the first pin that is usable.
    """

    _LED_PIN_CONFIG = {
        1: [9, 16],
        2: [25],
        3: [11, 26]
    }

    def __init__(self, pin_config=None):
        self._leds = {}
        self._warned_ports = set()
        self._pin_config = pin_config if pin_config is not None else self._LED_PIN_CONFIG
        self._gpio_table = self._read_gpioinfo()
        self._setup()

    @staticmethod
    def _read_gpioinfo():
        """Read the whole gpioinfo table once: {gpio number: line text}"""
        try:
            result = subprocess.run(
                ["gpioinfo"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=2
            )
            if result.returncode != 0:
                logger.warning("gpioinfo returned %s, GPIO occupation check skipped",
                               result.returncode)
                return {}
        except Exception as exc:
            logger.warning("gpioinfo unavailable (%s), GPIO occupation check skipped", exc)
            return {}

        table = {}
        for line in result.stdout.splitlines():
            for token in line.split():
                if token.startswith('"GPIO') and token.endswith('"'):
                    try:
                        table[int(token[5:-1])] = line
                    except ValueError:
                        pass
                    break
        return table

    def _gpio_kernel_busy(self, gpio):
        """Check if GPIO is occupied by kernel/spi driver"""
        line = self._gpio_table.get(gpio)
        if line is None:
            return False
        return 'consumer="kernel"' in line or 'consumer="spi' in line

    def _create_led(self, gpio):
        """Create single LED instance, return None on failure"""
        if self._gpio_kernel_busy(gpio):
            logger.info("GPIO%s is used by kernel driver, skipped", gpio)
            return None
        try:
            led = LED(gpio)
        except Exception as exc:
            logger.warning("GPIO%s LED init failed: %s", gpio, exc)
            return None
        logger.info("GPIO%s LED init OK", gpio)
        return led

    def _setup(self):
        """Initialize all LEDs with pin fallback logic"""
        for port, pins in self._pin_config.items():
            led_obj = None
            for pin in pins:
                led_obj = self._create_led(pin)
                if led_obj is not None:
                    break
            self._leds[port] = led_obj
            if led_obj is None:
                logger.warning("LED port %s is not available on this board", port)

    def set_led(self, port, status):
        """
        Control single LED
        :param port: LED port number (1 / 2 / 3)
        :param status: 1 = ON, 0 = OFF (bool is accepted as well)
        """
        led = self._leds.get(port)
        if led is None:
            if port not in self._warned_ports:
                self._warned_ports.add(port)
                logger.warning("set_led(port=%s) ignored: port not available", port)
            return

        if status in (1, True):
            led.on()
        elif status in (0, False):
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

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

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
