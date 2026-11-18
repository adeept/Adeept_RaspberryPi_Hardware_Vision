#!/usr/bin/env python3
# File name   : profile.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
Time-parameterised motion profile.

Pure math, no clock: the caller owns the time step and passes ``dt`` in, so a
profile can be exercised in a unit test with synthetic timestamps and needs no
hardware, no thread and no sleep().
"""
import math

SCURVE = "scurve"
LINEAR = "linear"


def _clamp01(u):
    """Clamp a normalised progress value to [0, 1]."""
    if u < 0.0:
        return 0.0
    return 1.0 if u > 1.0 else u


def smoothstep(u):
    """C1-continuous ramp 0 -> 1: zero slope at both ends."""
    u = _clamp01(u)
    return u * u * (3.0 - 2.0 * u)


class Profile:
    """
    Signed displacement from 0 to ``distance`` (degrees) over ``duration``.

    ``duration`` is raised automatically so the move stays within ``max_vel``
    (deg/s) and ``max_acc`` (deg/s^2).  Peak values of the default S-curve,
    with T = duration and d = |distance|::

        v_peak = 1.5 * d / T        ->  T_min = 1.5 * d / max_vel
        a_peak = 6.0 * d / T^2      ->  T_min = sqrt(6 * d / max_acc)

    A ``duration`` longer than the minimum simply slows the move down while
    the limits stay satisfied.  With neither ``duration`` nor limits the move
    is instant, which is what ``Joint.jump()`` relies on.

    :param distance: signed travel, degrees
    :param duration: desired travel time, seconds (None = as fast as limits allow)
    :param max_vel: speed limit, deg/s (None = unlimited)
    :param max_acc: acceleration limit, deg/s^2 (None = unlimited)
    :param mode: ``"scurve"`` (default) or ``"linear"``
    """

    def __init__(self, distance, duration=None, max_vel=None, max_acc=None,
                 mode=SCURVE):
        if mode not in (SCURVE, LINEAR):
            raise ValueError("unknown profile mode %r" % (mode,))

        self.distance = float(distance)
        self.mode = mode

        span = abs(self.distance)
        if span == 0.0:
            self.duration = 0.0
            return

        dur = 0.0 if duration is None else max(0.0, float(duration))
        if mode == LINEAR:
            # Constant speed: peak velocity == speed.
            if max_vel:
                dur = max(dur, span / float(max_vel))
        else:
            if max_vel:
                dur = max(dur, 1.5 * span / float(max_vel))
            if max_acc:
                dur = max(dur, math.sqrt(6.0 * span / float(max_acc)))
        self.duration = dur

    def at(self, t):
        """Signed displacement reached ``t`` seconds after the start."""
        if self.duration <= 0.0:
            return self.distance
        u = _clamp01(t / self.duration)
        s = smoothstep(u) if self.mode == SCURVE else u
        return self.distance * s

    def __repr__(self):
        return "Profile(distance=%+.1f, duration=%.3fs, mode=%s)" % (
            self.distance, self.duration, self.mode)
