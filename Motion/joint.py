#!/usr/bin/env python3
# File name   : joint.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
One logical joint: a Hardware.Servo plus limits, polarity and a non-blocking
trajectory.
"""
from .profile import Profile, SCURVE


class Joint:
    """
    Wraps a single ``Hardware.Servo``.

    ``Servo`` only knows "put the horn at angle X right now".  A robot needs
    two things on top of that, and both live here:

    * a *logical* angle space (``neutral`` + ``direction``), so poses can be
      written as relative offsets around the mechanical mid position:
      ``absolute = neutral + direction * offset``;
    * a *trajectory*, advanced by ``step(dt)``.  Nothing sleeps, so sixteen
      joints can share one clock and one I2C bus.

    :param servo: object exposing an ``angle`` property (Hardware.Servo)
    :param min_angle: lower limit, degrees
    :param max_angle: upper limit, degrees
    :param neutral: absolute angle that a relative offset of 0 maps to
    :param direction: +1 or -1, flips the sign of relative offsets
    :param max_vel: default speed limit, deg/s (None = unlimited)
    :param max_acc: default acceleration limit, deg/s^2 (None = unlimited)
    :param deadband: smallest angle change worth pushing onto the I2C bus
    """

    def __init__(self, servo, min_angle=0.0, max_angle=180.0, neutral=90.0,
                 direction=1, max_vel=None, max_acc=None, deadband=0.5,
                 name=None):
        if max_angle < min_angle:
            raise ValueError("max_angle must be >= min_angle")

        self.servo = servo
        self.name = name
        self.min_angle = float(min_angle)
        self.max_angle = float(max_angle)
        self.neutral = self._clamp(neutral)
        self.direction = 1.0 if float(direction) >= 0.0 else -1.0
        self.max_vel = None if max_vel is None else float(max_vel)
        self.max_acc = None if max_acc is None else float(max_acc)
        self.deadband = float(deadband)

        # Adopt whatever the servo currently holds as the starting point.
        self._pos = self._clamp(getattr(servo, "angle", self.neutral))
        self._origin = self._pos
        self._profile = None
        self._elapsed = 0.0
        self._written = None
        self._writes = 0

    # ------------------------------------------------------------------
    # state
    # ------------------------------------------------------------------
    @property
    def angle(self):
        """Current logical angle, degrees."""
        return self._pos

    @property
    def target(self):
        """Angle the joint is heading for, or None when standing still."""
        if self._profile is None:
            return None
        return self._clamp(self._origin + self._profile.distance)

    @property
    def busy(self):
        """True while a trajectory is still running."""
        return self._profile is not None

    @property
    def writes(self):
        """How many PWM updates this joint has pushed onto the bus.

        Useful when a servo does not move: a counter that keeps growing proves
        the write path is alive and the problem is downstream (power, wiring,
        channel), not this layer.
        """
        return self._writes

    def __repr__(self):
        label = self.name or "-"
        return "Joint(%s, angle=%.1f, target=%s)" % (
            label, self._pos,
            "%.1f" % self.target if self.busy else "-")

    # ------------------------------------------------------------------
    # logical / absolute angle mapping
    # ------------------------------------------------------------------
    def _clamp(self, angle):
        return max(self.min_angle, min(self.max_angle, float(angle)))

    def to_absolute(self, offset):
        """Relative offset (0 = neutral) -> absolute clamped angle."""
        return self._clamp(self.neutral + self.direction * float(offset))

    def to_relative(self, angle=None):
        """Absolute angle (default: current) -> relative offset."""
        angle = self._pos if angle is None else float(angle)
        return (angle - self.neutral) * self.direction

    def set_limits(self, min_angle, max_angle):
        """Change the mechanical limits, keeping the current position valid."""
        if max_angle < min_angle:
            raise ValueError("max_angle must be >= min_angle")
        self.min_angle = float(min_angle)
        self.max_angle = float(max_angle)
        self._pos = self._clamp(self._pos)

    def set_neutral(self, neutral, direction=None):
        """Re-define the neutral point (mounting / calibration correction)."""
        self.neutral = self._clamp(neutral)
        if direction is not None:
            self.direction = 1.0 if float(direction) >= 0.0 else -1.0

    # ------------------------------------------------------------------
    # motion
    # ------------------------------------------------------------------
    def move_to(self, angle, duration=None, max_vel=None, max_acc=None,
                mode=SCURVE):
        """
        Start a smooth move to ``angle``.

        The trajectory restarts from the *current* position, so calling this
        again mid-move retargets without a jump.  Returns True when motion was
        started (False when the joint is already there).
        """
        target = self._clamp(angle)
        if self._profile is None and abs(target - self._pos) < 1e-9:
            return False

        self._origin = self._pos
        self._profile = Profile(
            target - self._origin,
            duration,
            self.max_vel if max_vel is None else max_vel,
            self.max_acc if max_acc is None else max_acc,
            mode,
        )
        self._elapsed = 0.0
        return True

    def required_duration(self, angle, duration=None, max_vel=None,
                          max_acc=None, mode=SCURVE):
        """Seconds needed to reach ``angle``; no side effects."""
        target = self._clamp(angle)
        return Profile(
            target - self._pos,
            duration,
            self.max_vel if max_vel is None else max_vel,
            self.max_acc if max_acc is None else max_acc,
            mode,
        ).duration

    def step(self, dt):
        """
        Advance the trajectory by ``dt`` seconds and write the new angle.

        Returns True while the joint still has somewhere to go.  Never blocks,
        never sleeps: the caller owns the clock.  A ``dt`` larger than the
        remaining travel simply lands on the target.
        """
        if self._profile is None:
            return False

        self._elapsed += dt
        if self._elapsed >= self._profile.duration:
            self._pos = self._clamp(self._origin + self._profile.distance)
            self._profile = None
            self._write(force=True)
            return False

        self._pos = self._clamp(self._origin + self._profile.at(self._elapsed))
        self._write()
        return True

    def jump(self, angle):
        """Move now, no ramp: start-up pose or emergency recovery."""
        self._profile = None
        self._pos = self._clamp(angle)
        self._write(force=True)

    def stop(self):
        """Drop the trajectory and hold the current angle."""
        self._profile = None

    def close(self):
        """Release the underlying servo channel."""
        self._profile = None
        close = getattr(self.servo, "close", None)
        if close is not None:
            close()

    # ------------------------------------------------------------------
    # bus write, rate limited by deadband
    # ------------------------------------------------------------------
    def _write(self, force=False):
        if (not force) and self._written is not None and abs(self._pos - self._written) < self.deadband:
            return
        self.servo.angle = self._pos
        self._written = self._pos
        self._writes += 1
