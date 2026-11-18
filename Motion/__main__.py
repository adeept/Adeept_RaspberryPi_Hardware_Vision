#!/usr/bin/env python3
# File name   : __main__.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
Demo for the Motion layer.  Run from the folder that contains Hardware/ and
Motion/:

    python3 -m Motion

The demo owns the clock (``DT`` below) because a demo is the one place a clock
belongs; the library itself never keeps time.
"""
import time

from .calibration import ServoCalibration
from .servo_bank import ServoBank

DT = 0.02          # one scheduler tick, 50 Hz


def drive_until_idle(bank, dt=DT, timeout=None):
    """Pump the bank until every joint has arrived.  Demo only."""
    start = time.monotonic()
    while bank.update(dt):
        time.sleep(dt)
        if timeout is not None and time.monotonic() - start > timeout:
            return False
    return True


def main():
    # Boot: the table written by "python3 -m Motion.calibrate" is what turns
    # absolute servo angles into the robot's own mid position and direction.
    cal = ServoCalibration.load()
    if cal.error:
        print("calibration: %s -- running on defaults" % cal.error)
    for problem in cal.validate():
        print("calibration: %s" % problem)

    bank = ServoBank(count=cal.count, freq=50, address=0x5F,
                     actuation_range=cal.actuation_range,
                     config=cal.to_config())
    print("%d joints ready, tick = %.0f ms" % (len(bank), DT * 1000.0))

    try:
        # 1. Synchronised sweep: every joint starts and stops on the same tick.
        for angle in (40.0, 140.0, 40.0):
            travel = bank.move_all({ch: angle for ch in range(16)},
                                   duration=1.2, max_acc=600)
            print("sweep to %.0f deg over %.2f s" % (angle, travel))
            drive_until_idle(bank)

        # 2. Relative pose: neutral + direction * offset.
        bank.pose({ch: 25.0 for ch in range(16)}, duration=0.8)
        drive_until_idle(bank)
        bank.pose({ch: -25.0 for ch in range(16)}, duration=0.8)
        drive_until_idle(bank)

        # 3. Retarget mid-move: no jump, the curve restarts from where it is.
        bank.move_all({ch: 150.0 for ch in range(16)}, duration=2.0)
        time.sleep(0.6)
        bank.move_all({ch: 60.0 for ch in range(16)}, duration=0.9)
        drive_until_idle(bank)
        print("done, all joints at %.1f deg" % bank.angles()[0])

    except KeyboardInterrupt:
        print("\nCtrl+C detected, holding position")
    finally:
        bank.stop_all()
        bank.close()
        print("servo outputs released")


if __name__ == "__main__":
    main()
