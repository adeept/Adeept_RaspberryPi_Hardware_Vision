#!/usr/bin/env python3
# File name   : Buzzer.py
# Website     : www.Adeept.com
# Author      : Adeept
import logging

from gpiozero import TonalBuzzer
from time import sleep

logger = logging.getLogger(__name__)


class Buzzer:
    """
    Onboard passive buzzer control class
    Supports note playback and preset tunes, compatible with Robot HAT
    """

    # Preset: Happy Birthday song 
    HAPPY_BIRTHDAY = [
        ["G4", 0.3], ["G4", 0.3], ["A4", 0.3], ["G4", 0.3], ["C5", 0.3], ["B4", 0.6],
        ["G4", 0.3], ["G4", 0.3], ["A4", 0.3], ["G4", 0.3], ["D5", 0.3], ["C5", 0.6],
        ["G4", 0.3], ["G4", 0.3], ["C5", 0.3], ["B4", 0.3], ["C5", 0.3], ["B4", 0.3], ["A4", 0.6],
        ["F5", 0.3], ["F5", 0.3], ["B4", 0.3], ["C5", 0.3], ["D5", 0.3], ["C5", 0.6]
    ]

    def __init__(self, gpio_pin=18):
        """
        Initialize buzzer
        :param gpio_pin: GPIO pin number (BCM encoding), default 18
        """
        self._buzzer = TonalBuzzer(gpio_pin)

    def play(self, tune):
        """
        Play a custom musical tune (blocking) and always silence the buzzer at the end,
        even when the caller is interrupted with Ctrl+C.
        :param tune: List of [note, duration] pairs
        """
        try:
            for note, duration in tune:
                logger.debug("%s", note)
                self._buzzer.play(note)
                sleep(float(duration))
        finally:
            self.stop()

    def stop(self):
        """Stop buzzer output immediately"""
        try:
            self._buzzer.stop()
        except Exception:
            pass

    def play_happy_birthday(self):
        self.play(self.HAPPY_BIRTHDAY)

    def close(self):
        try:
            self.stop()
            self._buzzer.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


if __name__ == "__main__":
    try:
        with Buzzer(18) as buzzer:
            buzzer.play_happy_birthday()
    except KeyboardInterrupt:
        print("Program terminated by user.")
