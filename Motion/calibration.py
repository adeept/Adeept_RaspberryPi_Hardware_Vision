#!/usr/bin/env python3
# File name   : calibration.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
Per-channel mounting data for a servo robot, persisted as JSON.

The file answers three questions for every joint:

* ``neutral``  -- which absolute servo angle means "offset 0" for this robot?
* ``direction`` -- does a positive offset turn the joint the expected way?
* ``min`` / ``max`` -- where are the mechanical stops?

``ServoBank`` consumes the result directly, so booting is one line::

    cal  = ServoCalibration.load()
    bank = ServoBank(pca, count=cal.count, actuation_range=cal.actuation_range,
                     config=cal.to_config())

A missing or unreadable file never stops the robot: loading falls back to
defaults and records the reason in ``.error``.  The same field also reports a
file written for a different number of channels, so a table copied from another
build cannot be used half-way without anybody noticing.
"""
import json
import os
import time

DEFAULT_COUNT = 16
DEFAULT_PATH = os.path.join(os.path.expanduser("~"), ".adeept", "servo_calibration.json")
_VERSION = 1


def _round(value):
    return round(float(value), 2)


class ServoCalibration:
    """
    The calibration table: one dict per channel.

    Each entry holds ``name``, ``neutral`` (absolute degrees), ``direction``
    (+1 / -1), ``min`` and ``max`` (absolute degrees).

    :param count: number of channels, 16 by default
    :param actuation_range: full mechanical travel used for the defaults
    """

    def __init__(self, count=DEFAULT_COUNT, actuation_range=180.0):
        self.count = int(count)
        self.actuation_range = float(actuation_range)
        self.servos = {ch: self._default_channel(ch) for ch in range(self.count)}
        self.source = None      # path actually loaded, or None when defaults
        self.error = None       # why loading fell back, None when clean

    # ------------------------------------------------------------------
    # container
    # ------------------------------------------------------------------
    def __len__(self):
        return self.count

    def __getitem__(self, channel):
        return self.servos[int(channel)]

    def __iter__(self):
        for channel in range(self.count):
            yield channel, self.servos[channel]

    def _default_channel(self, channel):
        return {
            "name": "ch%d" % channel,
            "neutral": self.actuation_range / 2.0,
            "direction": 1,
            "min": 0.0,
            "max": self.actuation_range,
        }

    def get(self, channel, field, default=None):
        return self.servos.get(int(channel), {}).get(field, default)

    def channel_of(self, name):
        """Channel index whose ``name`` matches; raises ``KeyError`` if none.

        Lets pose code say ``bank.pose({cal.channel_of("lf_hip"): 18.0})``
        instead of hard coding channel numbers.
        """
        for channel, entry in self.servos.items():
            if entry["name"] == name:
                return channel
        raise KeyError("no channel named %r" % (name,))

    def set(self, channel, **fields):
        """Update fields of one channel; unknown field names raise KeyError."""
        entry = self.servos[int(channel)]
        for key, value in fields.items():
            if key == "name":
                entry["name"] = str(value)
            elif key == "direction":
                entry["direction"] = 1 if float(value) >= 0.0 else -1
            elif key in ("neutral", "min", "max"):
                entry[key] = _round(value)
            else:
                raise KeyError("unknown calibration field %r" % (key,))
        return entry

    # ------------------------------------------------------------------
    # handing over to ServoBank
    # ------------------------------------------------------------------
    def to_config(self):
        """A copy of the table, ready to pass as ``ServoBank(config=...)``."""
        return {channel: dict(entry) for channel, entry in self.servos.items()}

    def validate(self):
        """Return a list of human readable problems; empty means consistent."""
        problems = []
        names = {}
        for channel in range(self.count):
            entry = self.servos[channel]
            low, high, neutral = entry["min"], entry["max"], entry["neutral"]
            if high <= low:
                problems.append("ch%d: max (%.1f) <= min (%.1f)"
                                % (channel, high, low))
            elif not (low <= neutral <= high):
                problems.append("ch%d: neutral %.1f outside [%.1f, %.1f]"
                                % (channel, neutral, low, high))
            for key in ("min", "max"):
                if not (0.0 <= entry[key] <= self.actuation_range):
                    problems.append("ch%d: %s %.1f outside 0..%.0f"
                                    % (channel, key, entry[key],
                                       self.actuation_range))
            if entry["name"] in names:
                problems.append("ch%d: name %r is already used by ch%d"
                                % (channel, entry["name"], names[entry["name"]]))
            names[entry["name"]] = channel
        return problems

    def summary(self):
        """One line per channel, for logs."""
        lines = []
        for channel in range(self.count):
            entry = self.servos[channel]
            lines.append("%02d %-10s neutral %6.1f  min %5.1f  max %5.1f  dir %+d"
                         % (channel, entry["name"], entry["neutral"],
                            entry["min"], entry["max"], entry["direction"]))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------
    def as_dict(self):
        return {
            "version": _VERSION,
            "count": self.count,
            "actuation_range": self.actuation_range,
            "servos": {str(channel): dict(entry)
                       for channel, entry in self.servos.items()},
        }

    def save(self, path=None):
        """
        Write the table to ``path`` (default: ``DEFAULT_PATH``).

        The write goes to a temporary file and is then renamed over the target,
        so a crash or a pulled SD card leaves the previous file intact instead
        of half-written JSON.
        """
        path = path or DEFAULT_PATH
        target_dir = os.path.dirname(os.path.abspath(path))
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)

        payload = self.as_dict()
        payload["saved"] = time.strftime("%Y-%m-%d %H:%M:%S")

        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        self.source = path
        return path

    @classmethod
    def load(cls, path=None, count=DEFAULT_COUNT, strict=False):
        """
        Read the table back.

        :param strict: raise on a broken file instead of falling back to defaults
        :return: ServoCalibration; check ``.error`` to see why defaults were used
        """
        path = path or DEFAULT_PATH
        calibration = cls(count=count)

        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            calibration.error = "not found: %s" % path
            return calibration
        except (OSError, ValueError) as exc:
            if strict:
                raise
            calibration.error = "unreadable: %s (%s)" % (path, exc)
            return calibration

        try:
            span = float(data.get("actuation_range", calibration.actuation_range))
            calibration.actuation_range = span
            # Rebuild the defaults for the new span before applying the file.
            calibration.servos = {ch: calibration._default_channel(ch)
                                  for ch in range(calibration.count)}

            declared = data.get("count")
            if declared is not None and int(declared) != calibration.count:
                calibration.error = ("count mismatch: file has %d channels, "
                                     "this robot asked for %d"
                                     % (int(declared), calibration.count))

            for channel_key, entry in (data.get("servos") or {}).items():
                channel = int(channel_key)
                if not 0 <= channel < calibration.count:
                    continue
                calibration.set(channel, **{
                    key: entry[key]
                    for key in ("name", "neutral", "direction", "min", "max")
                    if key in entry
                })
        except (TypeError, ValueError, KeyError) as exc:
            if strict:
                raise
            calibration.error = "bad content: %s (%s)" % (path, exc)
            return calibration

        calibration.source = path
        return calibration
