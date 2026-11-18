#!/usr/bin/env python3
# File name   : servo_bank.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
ServoBank: up to 16 logical joints sharing one PCA9685 bus and one clock.
"""
from .joint import Joint
from .profile import SCURVE

DEFAULT_COUNT = 16


class ServoBank:
    """
    A bank of servo joints driven by a single ``update(dt)`` call.

    The PCA9685 can be passed in (share the bus with ``Hardware.Motor``) or
    left as None, in which case the bank creates and owns one.  ``count`` is
    16 by default, matching the chip's channel count.

    Per-channel tuning goes in ``config``::

        config = {
            0: {"min": 10, "max": 170, "neutral": 90, "direction": -1,
                "max_vel": 120, "max_acc": 600, "name": "leg_lf_hip"},
        }

    Any key left out keeps the default; a channel missing from ``config``
    uses all defaults.

    :param pca: existing Hardware.PCA9685, or None to create one
    :param count: number of joints, 1..16
    :param bus_num: I2C bus, only used when the bank creates its own chip
    :param address: PCA9685 address, only used when the bank creates its own chip
    :param freq: PWM frequency, only used when the bank creates its own chip
    :param min_pulse: pulse width at 0 deg, microseconds
    :param max_pulse: pulse width at full range, microseconds
    :param actuation_range: full travel of the servos, degrees
    :param servo_factory: optional ``callable(channel) -> servo``; use it to
        inject a fake servo in tests, or a different driver on other boards
    :param config: optional per-channel dict (see above)
    :param deadband: default smallest change worth writing, degrees
    """

    def __init__(self, pca=None, count=DEFAULT_COUNT, bus_num=1, address=0x5F,
                 freq=50, min_pulse=500, max_pulse=2400, actuation_range=180,
                 servo_factory=None, config=None, deadband=0.5):
        if not 1 <= int(count) <= DEFAULT_COUNT:
            raise ValueError("count must be between 1 and 16")

        self.count = int(count)
        self._min_pulse = min_pulse
        self._max_pulse = max_pulse
        self._actuation_range = actuation_range
        self._factory = servo_factory
        self._closed = False

        if pca is None and servo_factory is None:
            from Hardware.pca9685 import PCA9685   # lazy: smbus only on the Pi
            pca = PCA9685(bus_num=bus_num, address=address, freq=freq)
            self.owns_pca = True
        else:
            self.owns_pca = False
        self.pca = pca

        self.joints = []
        for channel in range(self.count):
            cfg = self._channel_config(config, channel)
            joint = Joint(
                self._make_servo(channel),
                min_angle=cfg.get("min", 0.0),
                max_angle=cfg.get("max", float(actuation_range)),
                neutral=cfg.get("neutral", 90.0),
                direction=cfg.get("direction", 1),
                max_vel=cfg.get("max_vel"),
                max_acc=cfg.get("max_acc"),
                deadband=cfg.get("deadband", deadband),
                name=cfg.get("name", "ch%d" % channel),
            )
            self.joints.append(joint)

    # ------------------------------------------------------------------
    # construction helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _channel_config(config, channel):
        if config is None:
            return {}
        if isinstance(config, dict):
            return dict(config.get(channel) or {})
        if channel < len(config):
            return dict(config[channel] or {})
        return {}

    def _make_servo(self, channel):
        if self._factory is not None:
            return self._factory(channel)
        from Hardware.Servo import Servo          # lazy: smbus only on the Pi
        return Servo(self.pca, channel,
                     min_pulse=self._min_pulse,
                     max_pulse=self._max_pulse,
                     actuation_range=self._actuation_range)

    # ------------------------------------------------------------------
    # container sugar
    # ------------------------------------------------------------------
    def __len__(self):
        return len(self.joints)

    def __iter__(self):
        return iter(self.joints)

    def __getitem__(self, channel):
        return self.joints[channel]

    def __repr__(self):
        moving = sum(1 for j in self.joints if j.busy)
        return "ServoBank(%d joints, %d moving)" % (len(self.joints), moving)

    # ------------------------------------------------------------------
    # motion
    # ------------------------------------------------------------------
    def move_to(self, channel, angle, duration=None, max_vel=None, max_acc=None, mode=SCURVE):
        """Smooth move of one joint.  Returns True when motion started."""
        return self.joints[channel].move_to(angle, duration, max_vel, max_acc, mode)

    def move_all(self, targets, duration=None, max_vel=None, max_acc=None, mode=SCURVE):
        """
        Move several joints and make them arrive together.

        ``targets`` is a dict ``{channel: angle}`` or a sequence where ``None``
        skips that channel.  The returned value is the common duration: it is
        the longest time any joint needs, so every joint finishes on the same
        tick instead of chasing its own deadline.
        """
        pairs = self._normalise_targets(targets)
        if not pairs:
            return 0.0

        common = 0.0 if duration is None else max(0.0, float(duration))
        for channel, angle in pairs:
            common = max(common, self.joints[channel].required_duration(angle, None, max_vel, max_acc, mode))

        for channel, angle in pairs:
            self.joints[channel].move_to(angle, common, max_vel, max_acc, mode)
        return common

    def pose(self, offsets, duration=None, max_vel=None, max_acc=None,
             mode=SCURVE):
        """
        Same as ``move_all`` but the values are relative offsets around
        ``neutral`` (0 = mid position), flipped by ``direction`` where needed.
        """
        pairs = self._normalise_targets(offsets)
        targets = {channel: self.joints[channel].to_absolute(offset)
                   for channel, offset in pairs}
        return self.move_all(targets, duration, max_vel, max_acc, mode)

    def update(self, dt):
        """
        Advance every joint by ``dt`` seconds.

        Call this from exactly one place -- the robot's main loop or a
        scheduler thread -- and use the same ``dt`` for all joints so their
        phases never drift apart.  Returns True while anything is still moving.
        """
        moving = False
        for joint in self.joints:
            if joint.step(dt):
                moving = True
        return moving

    @property
    def busy(self):
        """True while at least one joint is moving."""
        return any(joint.busy for joint in self.joints)

    # ------------------------------------------------------------------
    # immediate / safety paths
    # ------------------------------------------------------------------
    def jump_all(self, targets):
        """Place joints immediately, bypassing every ramp."""
        for channel, angle in self._normalise_targets(targets):
            self.joints[channel].jump(angle)

    def stop_all(self):
        """Drop all trajectories and hold the current pose."""
        for joint in self.joints:
            joint.stop()

    def angles(self):
        """Current logical angle of every joint, in channel order."""
        return [joint.angle for joint in self.joints]

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def close(self):
        """Release every servo channel, then the chip if the bank owns it."""
        if self._closed:
            return
        self._closed = True

        for joint in self.joints:
            try:
                joint.close()
            except Exception:
                pass

        if self.owns_pca and self.pca is not None:
            try:
                self.pca.deinit()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------
    def _normalise_targets(self, targets):
        if isinstance(targets, dict):
            items = list(targets.items())
        else:
            items = [(channel, angle)
                     for channel, angle in enumerate(targets)
                     if angle is not None]

        pairs = []
        for channel, angle in items:
            channel = int(channel)
            if not 0 <= channel < self.count:
                raise IndexError("channel %d out of range (0..%d)"
                                 % (channel, self.count - 1))
            if angle is None:
                continue
            pairs.append((channel, float(angle)))
        return pairs
