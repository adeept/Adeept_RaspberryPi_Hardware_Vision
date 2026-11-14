#!/usr/bin/env python3
# File name   : MPU6050.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
MPU6050 6-axis IMU driver with internal temperature sensor.
Provides raw sensor data, calculated Roll/Pitch/Yaw angles and chip temperature.
Note: Yaw cannot be derived from accelerometer alone; gyro integration is provided optionally.
"""
import math
from mpu6050 import mpu6050
import time
from smbus import SMBus


class MPU6050:
    """
    MPU6050 6-axis motion sensor controller.
    :param address: I2C device address, default 0x68
    :param bus: I2C bus number, default 1 for Raspberry Pi
    """

    def __init__(self, address=0x68, bus=1):
        self.address = address
        self.bus = SMBus(bus)
        self._sensor = mpu6050(address, bus=bus)
        self._yaw = 0.0
        self._last_gyro_time = None

    def get_accel_data(self):
        """
        Get raw accelerometer readings.
        :return: Dict with keys 'x', 'y', 'z', unit: g (gravity)
        """
        return self._sensor.get_accel_data()

    def get_gyro_data(self):
        """
        Get raw gyroscope readings.
        :return: Dict with keys 'x', 'y', 'z', unit: °/s
        """
        return self._sensor.get_gyro_data()

    def get_temperature(self):
        """Get internal temperature sensor reading in Celsius."""
        temp_raw = self.bus.read_i2c_block_data(self.address, 0x41, 2)
        raw = (temp_raw[0] << 8) | temp_raw[1]

        if raw & 0x8000:
            raw -= 0x10000

        return raw / 340.0 + 36.53

    def _calc_rpy_from_accel(self, accel):
        """Calculate Roll and Pitch from accelerometer; Yaw is not available from accelerometer"""
        ax = accel['x']
        ay = accel['y']
        az = accel['z']
        roll = math.atan2(ay, math.sqrt(ax**2 + az**2)) * 180 / math.pi
        pitch = math.atan2(-ax, math.sqrt(ay**2 + az**2)) * 180 / math.pi
        return (roll, pitch, 0.0)

    def get_rpy(self):
        """
        Get single-sample Roll/Pitch/Yaw from accelerometer.
        :return: Tuple (roll, pitch, yaw) in degrees; yaw = 0 (accelerometer cannot measure yaw)
        """
        accel = self.get_accel_data()
        return self._calc_rpy_from_accel(accel)

    def get_rpy_averaged(self, samples=10):
        """
        Get averaged Roll/Pitch/Yaw 
        :param samples: Number of samples for averaging, default 10
        :return: Tuple (roll_avg, pitch_avg, yaw_avg) in degrees
        """
        roll_sum = 0.0
        pitch_sum = 0.0
        for _ in range(samples):
            roll, pitch, _ = self.get_rpy()
            roll_sum += roll
            pitch_sum += pitch
        return (roll_sum / samples, pitch_sum / samples, 0.0)

    def update_yaw_by_gyro(self):
        """
        Update yaw angle by integrating gyroscope Z-axis data.
        Call this periodically in a loop for continuous yaw estimation.
        :return: Current yaw angle in degrees, range [-180, 180]
        """
        gyro = self.get_gyro_data()
        now = time.time()

        if self._last_gyro_time is None:
            self._last_gyro_time = now
            return self._yaw

        dt = now - self._last_gyro_time
        self._last_gyro_time = now
        # Integrate Z-axis angular rate over time
        self._yaw += gyro['z'] * dt
        # Normalize angle to [-180, 180]
        if self._yaw > 180:
            self._yaw -= 360
        elif self._yaw < -180:
            self._yaw += 360
        return self._yaw

    def reset_yaw(self):
        """Reset yaw angle to 0 degrees"""
        self._yaw = 0.0
        self._last_gyro_time = None

    def close(self):
        """Release sensor resources."""
        if self.bus is not None:
            self.bus.close()
            self.bus = None
        self._sensor = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


if __name__ == "__main__":
    print("MPU6050 test started.")
    with MPU6050() as imu:
        try:
            print("=== Averaged RPY + temperature output ===")
            while True:
                roll, pitch, yaw = imu.get_rpy_averaged(samples=10)
                temp = imu.get_temperature()
                print(f"Roll={roll:.2f}°, Pitch={pitch:.2f}°, Yaw={yaw:.2f}°, Temp={temp:.1f}°C")
                time.sleep(0.3)

        except KeyboardInterrupt:
            print("\nTest stopped by user.")
        except Exception as e:
            print(f"Error: {e}")
