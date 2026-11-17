#!/usr/bin/env python3
# File name   : camera_capture.py
# Website     : www.Adeept.com
# Author      : Adeept
"""Camera capture abstraction layer.

Supports USB (V4L2) and CSI (Picamera2) cameras, auto detection or manual choice.
Outputs unified BGR frames, no CV processing and no hardware control.
"""
import cv2
import numpy as np

# Picamera2 is only available on Raspberry Pi OS with the CSI stack
try:
    from picamera2 import Picamera2
    import libcamera
    HAS_PICAMERA2 = True
except ImportError:
    HAS_PICAMERA2 = False


class CameraCapture:
    """Unified camera capture interface.

    :param camera_type: "auto" / "usb" / "csi"
    :param width: frame width in pixels
    :param height: frame height in pixels
    :param fps: target frame rate
    :param hflip: horizontal flip
    :param vflip: vertical flip
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

    _UVC_HINTS = ("usb", "uvc")

    @classmethod
    def _is_uvc(cls, entry):
        text = " ".join(str(entry.get(key, "")) for key in ("Id", "Model", "Location")).lower()
        return any(hint in text for hint in cls._UVC_HINTS)

    @staticmethod
    def _libcamera_devices():
        """Enumerate libcamera devices (nothing is acquired by doing this).

        :return: device list; [] means libcamera really has no camera;
                 None means this picamera2 cannot enumerate (old version or an error)
        """
        info = getattr(Picamera2, "global_camera_info", None)
        if info is None:
            return None
        try:
            return list(info())
        except Exception:
            return None

    def _detect_camera(self):
        """Detect which camera type to use."""
        if self.camera_type == "usb":
            return "usb"
        if self.camera_type == "csi":
            if not HAS_PICAMERA2:
                raise RuntimeError("Picamera2 library not installed, cannot use the CSI camera")
            return "csi"

        # Auto mode: only a real CSI sensor counts as CSI. A USB webcam exposed
        # through libcamera's uvcvideo pipeline must take the V4L2 path.
        if HAS_PICAMERA2:
            devices = self._libcamera_devices()
            if devices is not None:
                for entry in devices:
                    if self._is_uvc(entry):
                        print("USB(UVC) camera found in libcamera, using V4L2 path: %s"
                              % (entry.get("Id") or entry.get("Model") or "?"))
                        continue
                    return "csi"
                return "usb"

            try:
                Picamera2().close()
                return "csi"
            except Exception:
                pass
        return "usb"

    def _apply_flip(self, img):
        """Apply the flip settings to a frame."""
        if not self.hflip and not self.vflip:
            return img
        if self.hflip and self.vflip:
            return cv2.flip(img, -1)
        elif self.hflip:
            return cv2.flip(img, 1)
        return cv2.flip(img, 0)

    def _open_csi(self):
        """Open the CSI camera through Picamera2 (format kept identical to v1)."""
        cam = Picamera2()
        try:
            config = cam.create_preview_configuration(
                main={"size": (self.width, self.height), "format": "RGB888"},
                transform=libcamera.Transform(hflip=int(self.hflip), vflip=int(self.vflip)),
                colour_space=libcamera.ColorSpace.Sycc(),
                buffer_count=4,
                queue=True
            )
            cam.configure(config)
            cam.start()
        except Exception:
            try:
                cam.close()
            except Exception:
                pass
            raise
        self._device = cam

    def _open_usb(self):
        """Open the USB (V4L2) camera."""
        cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            raise RuntimeError("USB camera open failed")
        self._device = cap

    def start(self):
        """Open and initialise the camera."""
        if self._opened:
            return

        self._device_type = self._detect_camera()
        if self._device_type == "csi":
            try:
                self._open_csi()
            except Exception as e:
                if self.camera_type != "auto":
                    raise
                self._device = None
                self._device_type = "usb"
                print("CSI open failed (%s), falling back to USB" % e)

        if self._device_type == "usb":
            self._open_usb()

        self._opened = True
        print(f"Camera initialized: {self._device_type}, {self.width}x{self.height} @ {self.fps}fps")

    def read_frame(self):
        """Read one frame.

        :return: BGR numpy array, or None when the read failed
        """
        if not self._opened:
            return None

        if self._device_type == "csi":
            return self._device.capture_array()
        ret, frame = self._device.read()
        if not ret:
            return None
        return self._apply_flip(frame)

    def stop(self):
        """Release the camera."""
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
