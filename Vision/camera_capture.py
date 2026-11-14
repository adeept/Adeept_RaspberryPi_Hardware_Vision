#!/usr/bin/env python3
# File name   : camera_capture.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
Camera capture abstraction layer.
Supports USB (V4L2) and CSI (Picamera2) cameras, auto-detection or manual selection.
Outputs unified BGR format frames, no CV processing, no hardware control.
"""
import cv2
import numpy as np

# Try to import Picamera2 for CSI camera support
try:
    from picamera2 import Picamera2
    import libcamera
    HAS_PICAMERA2 = True
except ImportError:
    HAS_PICAMERA2 = False


class CameraCapture:
    """
    Unified camera capture interface.
    :param camera_type: "auto" / "usb" / "csi"
    :param width: Frame width in pixels
    :param height: Frame height in pixels
    :param fps: Target frame rate
    :param hflip: Horizontal flip
    :param vflip: Vertical flip
    """

    def __init__(self, camera_type="auto", width=640, height=480, fps=30, hflip=False, vflip=False):
        self.camera_type = camera_type
        self.width = width
        self.height = height
        self.fps = fps
        self.hflip = hflip
        self.vflip = vflip

        self._device = None
        self._device_type = None
        self._opened = False

    def _detect_camera(self):
        """Auto-detect available camera type"""
        if self.camera_type == "usb":
            return "usb"
        if self.camera_type == "csi":
            if not HAS_PICAMERA2:
                raise RuntimeError("Picamera2 library not installed, cannot use CSI camera")
            return "csi"

        # Auto mode: try CSI first, fall back to USB
        if HAS_PICAMERA2:
            try:
                test_cam = Picamera2()
                test_cam.close()
                return "csi"
            except Exception:
                pass
        return "usb"

    def _apply_flip(self, img):
        """Apply flip settings to frame"""
        if not self.hflip and not self.vflip:
            return img
        if self.hflip and self.vflip:
            return cv2.flip(img, -1)
        elif self.hflip:
            return cv2.flip(img, 1)
        else:
            return cv2.flip(img, 0)

    def start(self):
        """Open and initialize camera"""
        if self._opened:
            return

        self._device_type = self._detect_camera()

        if self._device_type == "csi":
            cam = Picamera2()
            config = cam.create_preview_configuration(
                main={"size": (self.width, self.height), "format": "RGB888"},
                transform=libcamera.Transform(hflip=int(self.hflip), vflip=int(self.vflip)),
                colour_space=libcamera.ColorSpace.Sycc(),  
                buffer_count=4,  
                queue=True
            )
            cam.configure(config)
            cam.start()
            self._device = cam
        else:
            cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FPS, self.fps)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not cap.isOpened():
                raise RuntimeError("USB camera open failed")
            self._device = cap

        self._opened = True
        print(f"Camera initialized: {self._device_type}, {self.width}x{self.height} @ {self.fps}fps")

    def read_frame(self):
        """
        Read one frame from camera.
        :return: BGR format numpy array, or None if read failed
        """
        if not self._opened:
            return None

        if self._device_type == "csi":
            return self._device.capture_array()
        else:
            ret, frame = self._device.read()
            if not ret:
                return None
            return self._apply_flip(frame)

    def stop(self):
        """Release camera resources"""
        if not self._opened:
            return
        if self._device_type == "csi":
            self._device.stop()
            self._device.close()
        else:
            self._device.release()
        self._opened = False
        print("Camera released.")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False
