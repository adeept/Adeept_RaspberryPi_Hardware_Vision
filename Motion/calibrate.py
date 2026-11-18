#!/usr/bin/env python3
# File name   : calibrate.py
# Website     : www.Adeept.com
# Author      : Adeept
"""Interactive keyboard calibration for a servo bank.

Run it on the robot, with the legs off the ground:

    python3 -m Motion.calibrate

The tool talks to the servos directly, so it must run *instead of* the robot
program: one PCA9685 channel cannot be claimed twice.  Calibrate first, then
start the robot -- it picks the saved table up by itself.
"""
import contextlib
import os
import shutil
import sys
import time

from .calibration import DEFAULT_PATH, ServoCalibration
from .servo_bank import ServoBank

PANEL_WIDTH = 64
NOTICE_ROWS = 3


def _wrap(text, width):
    """Split a line into chunks of at most ``width`` characters.

    Breaks prefer a word gap, then a path separator, and keep that separator on
    the chunk it belongs to; a word gap is consumed.  A cut closer than eight
    characters to the start is ignored, so a prefix like ``"-> "`` never ends
    up alone on a row.
    """
    if width <= 0 or len(text) <= width:
        return [text]
    chunks = []
    while len(text) > width:
        cut = max(text.rfind(" ", 0, width), text.rfind("/", 0, width),
                  text.rfind("\\", 0, width))
        if cut < 8:
            chunks.append(text[:width])
            text = text[width:]
        elif text[cut] == " ":
            chunks.append(text[:cut])
            text = text[cut + 1:]
        else:
            chunks.append(text[:cut + 1])
            text = text[cut + 1:]
    return chunks + [text] if text else chunks


class ServoCalibrator:
    """Keyboard driven calibration session with a single, self explaining panel.

    It talks to a ``ServoBank`` whose limits are wide open (0..actuation_range),
    so the full travel can be explored before deciding where the mechanical
    stops are.

    :param bank: ServoBank built with permissive limits
    :param calibration: ServoCalibration table to fill in
    :param path: where ``s`` writes the table
    :param step: initial nudge size, degrees
    :param out: stream to draw on (default: stdout)
    :param plain: force one-line output, even on a terminal
    :param clear: wipe the screen before the first frame, so whatever the
        shell printed earlier cannot show through the panel
    """

    def __init__(self, bank, calibration, path=None, step=2.0, out=None,
                 plain=False, clear=True):
        self.bank = bank
        self.cal = calibration
        self.path = path or DEFAULT_PATH
        self.step = float(step)
        self.out = out or sys.stdout
        self._ansi = (not plain) and bool(getattr(self.out, "isatty",
                                                 lambda: False)())
        self._clear, self._cleared = clear, False
        self.channel, self._dirty = 0, False
        self._notice, self._quit_armed = "", False
        self._cursor_hidden, self._height = False, None

    # -- drawing --------------------------------------------------------
    def _strip(self):
        """Two rows of eight cells; each row spans exactly PANEL_WIDTH columns.

        Sixteen labels with gaps between them need 69 columns, more than the
        panel, so the row is cut in two and every cell gets an eight-column
        slot with its label centred in it.
        """
        rows = []
        for start in range(0, self.bank.count, 8):
            row = ""
            for channel in range(start, min(start + 8, self.bank.count)):
                label = "ch%d" % channel
                lead = (8 - len(label)) // 2
                if channel == self.channel and self._ansi:
                    label = "\x1b[7m%s\x1b[0m" % label
                row += " " * lead + label + " " * (8 - len(label) - lead)
            rows.append((row, False))
        return rows

    def _terminal_height(self):
        if self._height:
            return self._height
        try:
            return shutil.get_terminal_size((80, 24)).lines
        except Exception:
            return 24

    def _notice_lines(self):
        """Feedback occupies NOTICE_ROWS rows, wrapped, so nothing shifts."""
        lines = []
        for raw in (self._notice or "").split("\n"):
            if raw:
                lines.extend(_wrap(raw, PANEL_WIDTH - 5))
        lines = lines[:NOTICE_ROWS]
        return lines + [""] * (NOTICE_ROWS - len(lines))

    def _panel_rows(self):
        """Every row keeps the same shape, so the panel never changes layout."""
        entry, joint = self.cal[self.channel], self.bank[self.channel]
        rule = "-" * PANEL_WIDTH

        def cell(label, value):
            return "%-8s%6s" % (label, value)

        rows = [(" SERVO CALIBRATION ".center(PANEL_WIDTH).rstrip(), False),
                (rule, True)]
        rows += self._strip()
        rows += [
            (rule, True),
            # The live angle is not a saved key, so it sits in its own block.
            (" " + cell("angle:", "%.1f" % joint.angle), False),
            (rule, True),
            (" " + "   ".join([cell("neutral:", "%.1f" % entry["neutral"]),
                               cell("min:", "%.1f" % entry["min"]),
                               cell("max:", "%.1f" % entry["max"])]), False),
            (" " + "   ".join([cell("dir:", "%+d" % entry["direction"]),
                               cell("step:", "%.1f" % self.step)]), False),
            (rule, True)]
        for line in self._notice_lines():
            rows.append((" >> " + line if line else "", False))

        keys = [("[c] neutral", "[n] next", "[s] save"),
                ("[l] min", "[p] previous", "[r] reload"),
                ("[h] max", "[d] dir", "[q] quit"),
                ("[+/-] nudge", "[1..9] step", "[t] sweep all")]
        widths = [max(len(row[index]) for row in keys) for index in range(3)]
        for left, middle, right in keys:
            rows.append((" %-*s  %-*s  %s"
                         % (widths[0], left, widths[1], middle, right), False))
        return rows

    def _panel_lines(self):
        """Drop decorations until the panel fits the window, so nothing scrolls."""
        rows = self._panel_rows()
        budget = max(8, self._terminal_height() - 1)
        while len(rows) > budget:
            for index in range(len(rows) - 1, -1, -1):
                if rows[index][1]:
                    del rows[index]
                    break
            else:
                break
        return [text for text, _ in rows]

    def _compact_line(self):
        entry, joint = self.cal[self.channel], self.bank[self.channel]
        return ("ch%d %-8s angle %6.1f neutral %6.1f min %5.1f max %5.1f "
                "dir %+d step %4.1f" % (self.channel, entry.get("name", ""),
                                        joint.angle, entry["neutral"],
                                        entry["min"], entry["max"],
                                        entry["direction"], self.step))

    def _draw(self):
        if not self._ansi:
            self.out.write(self._compact_line() + "\n")
            if self._notice:
                self.out.write("  " + self._notice + "\n")
            self.out.flush()
            return

        if not self._cursor_hidden:
            self.out.write("\x1b[?25l")
            self._cursor_hidden = True

        # The first frame wipes the screen, later frames only home the cursor,
        # so a resize is not fought over; \x1b[K after every line erases
        # whatever the shell left to the right of this frame.
        head = "\x1b[H"
        if self._clear and not self._cleared:
            head = "\x1b[H\x1b[2J"
        self._cleared = True

        frame = self._panel_lines()
        if len(frame) > self._terminal_height() - 1:
            # Too short for even a stripped panel: one status line beats a
            # panel that scrolls and desynchronises the cursor.
            frame = [self._compact_line()]
        self.out.write(head + "\x1b[K\n".join(frame) + "\x1b[K\n\x1b[J")
        self.out.flush()

    # -- keys -----------------------------------------------------------
    def handle(self, key):
        """Act on one key; returns False when the session should end."""
        if not key:
            return True
        if key.isalpha():
            key = key.lower()                 # every letter, either case

        if key in ("q", "\x03"):              # Ctrl+C arrives as \x03
            if self._dirty and not self._quit_armed:
                self._notice = "unsaved changes: press s to save, q again to discard"
                self._quit_armed = True
                self._draw()
                return True
            return False
        self._quit_armed = False

        if key == "n":
            self.channel = (self.channel + 1) % self.bank.count
        elif key == "p":
            self.channel = (self.channel - 1) % self.bank.count
        elif key in ("+", "="):
            self._nudge(+self.step)
        elif key in ("-", "_"):
            self._nudge(-self.step)
        elif key.isdigit():
            self._set_step(10.0 if key == "0" else float(key))
        elif key in ("c", "l", "h"):
            self._capture({"c": "neutral", "l": "min", "h": "max"}[key])
        elif key == "d":
            entry = self.cal[self.channel]
            self.cal.set(self.channel, direction=-entry["direction"])
            self._dirty = True
            self._notice = "direction = %+d" % self.cal[self.channel]["direction"]
        elif key == "t":
            self._sweep()
        elif key == "s":
            self._save()
        elif key == "r":
            self._reload()

        self._draw()
        return True

    # -- actions --------------------------------------------------------
    def _nudge(self, delta):
        joint = self.bank[self.channel]
        joint.jump(joint.angle + delta)

    def _set_step(self, value):
        self.step = float(value)
        self._notice = "step = %.1f deg" % self.step

    def _capture(self, field):
        angle = round(self.bank[self.channel].angle, 2)
        self.cal.set(self.channel, **{field: angle})
        self._dirty = True
        self._notice = "%s = %.1f captured" % (field, angle)

        entry = self.cal[self.channel]
        if entry["max"] <= entry["min"]:
            self._notice = "limit conflict: max must be above min (press l / h)"
        elif not (entry["min"] <= entry["neutral"] <= entry["max"]):
            self._notice = "neutral %.1f is outside the limits (press c)" % (
                entry["neutral"])

    def _save(self):
        problems = self.cal.validate()
        path = self.cal.save(self.path)
        self._dirty = False

        # What was written for the channel on screen, then the file it went to;
        # the panel wraps the path instead of cutting it off.
        entry = self.cal[self.channel]
        lines = ["saved ch%d: neutral=%.1f min=%.1f max=%.1f dir=%+d" % (
            self.channel, entry["neutral"], entry["min"], entry["max"],
            entry["direction"]), "-> %s" % path]
        if problems:
            lines.append("warning: %s" % problems[0])
        self._notice = "\n".join(lines)

    def _reload(self):
        fresh = ServoCalibration.load(self.path, count=self.cal.count)
        if fresh.error:
            self._notice = "reload failed: %s" % fresh.error
            return
        self.cal.__dict__.update(fresh.__dict__)
        self._dirty = False
        self._notice = "reloaded %d channels from disk" % self.cal.count

    def _sweep(self, duration=0.9):
        """Run every channel min -> max -> neutral: the all-channel smoke test.

        A channel whose ``min`` equals its ``max`` has nowhere to go on its own
        table, so it falls back to the full travel and is named in the notice:
        it is a test, and the legs are off the ground anyway.
        """
        span = float(self.cal.actuation_range or 180.0)
        plan, fallback = {}, []
        for channel in range(self.bank.count):
            entry = self.cal[channel]
            if entry["max"] > entry["min"]:
                plan[channel] = (entry["min"], entry["max"], entry["neutral"])
            else:
                fallback.append(channel)
                plan[channel] = (0.0, span, span / 2.0)

        for index in range(3):
            self.bank.move_all({ch: plan[ch][index] for ch in plan},
                               duration=duration, max_acc=600)
            self._pump()

        if fallback:
            self._notice = "swept ch %s over 0..%d deg: their min >= max" % (
                ", ".join("%02d" % channel for channel in fallback), int(span))
        else:
            self._notice = "sweep done on %d channels: min -> max -> neutral" % (
                self.bank.count)

    def _pump(self, timeout=5.0):
        """Let the bank finish a move; the tool owns the clock here."""
        last = start = time.monotonic()
        while True:
            now = time.monotonic()
            dt = now - last
            last = now
            if dt > 0.05:                     # loop was blocked, do not teleport
                dt = 0.02
            if not self.bank.update(dt):
                return
            if now - start > timeout:
                self.bank.stop_all()
                return
            time.sleep(0.002)

    def run(self):
        try:
            with _raw_terminal() as read_key:
                self._draw()
                while self.handle(read_key(0.05)):
                    pass
        finally:
            if self._cursor_hidden:
                self.out.write("\x1b[?25h")
                self._cursor_hidden = False
            self.bank.stop_all()

        if not self._ansi:                    # the panel already ends with \n
            self.out.write("\n")
        self.out.write("quit: unsaved changes, the file on disk is unchanged\n"
                       if self._dirty else "done, table on disk: %s\n" % self.path)
        self.out.flush()


@contextlib.contextmanager
def _raw_terminal():
    """Yield ``read_key(timeout)`` with single keys arriving immediately."""
    if os.name == "nt":
        yield _read_key_windows
        return

    import select
    import termios
    import tty

    descriptor = sys.stdin.fileno()
    saved = termios.tcgetattr(descriptor)
    try:
        tty.setcbreak(descriptor)
        yield lambda timeout=0.05: _read_key_posix(timeout, select)
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, saved)


def _read_key_posix(timeout, select):
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if not ready:
        return ""
    key = sys.stdin.read(1)
    if key != "\x1b":
        return key

    # Arrow and function keys arrive as ESC sequences.  This tool does not use
    # them, so swallow the sequence instead of leaking '[' / 'A' to the handler.
    for _ in range(2):
        ready, _, _ = select.select([sys.stdin], [], [], 0.005)
        if not ready:
            break
        sys.stdin.read(1)
    return ""


def _read_key_windows(timeout):
    import msvcrt

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if msvcrt.kbhit():
            key = msvcrt.getwch()
            if key in ("\x00", "\xe0"):            # arrow / function key
                msvcrt.getwch()
                return ""
            return key
        time.sleep(0.005)
    return ""


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        description="Interactive calibration for a servo bank")
    parser.add_argument("--path", default=None,
                        help="calibration file (default: %s)" % DEFAULT_PATH)
    parser.add_argument("--count", type=int, default=16,
                        help="number of channels (default: 16)")
    parser.add_argument("--i2c-bus", type=int, default=1)
    parser.add_argument("--address", type=lambda text: int(text, 0), default=0x5F)
    parser.add_argument("--freq", type=int, default=50)
    parser.add_argument("--step", type=float, default=2.0,
                        help="initial nudge size in degrees")
    parser.add_argument("--plain", action="store_true",
                        help="one line per key instead of the full panel")
    parser.add_argument("--no-clear", action="store_true",
                        help="keep earlier terminal output on screen")
    args = parser.parse_args(argv)

    from Hardware.pca9685 import PCA9685

    print("Lift the robot or put it on blocks: every channel will move.")
    pca = PCA9685(bus_num=args.i2c_bus, address=args.address, freq=args.freq)

    # Calibration needs the full travel, so build the bank with wide limits.
    bank = ServoBank(pca, count=args.count, actuation_range=180, deadband=0.0,
                     config={channel: {"min": 0.0, "max": 180.0, "neutral": 90.0,
                                       "direction": 1, "name": "ch%d" % channel}
                             for channel in range(args.count)})
    calibration = ServoCalibration.load(args.path, count=args.count)
    calibrator = ServoCalibrator(bank, calibration, path=args.path,
                                 step=args.step, plain=args.plain,
                                 clear=not args.no_clear)
    try:
        calibrator.run()
    finally:
        bank.close()


if __name__ == "__main__":
    main()
