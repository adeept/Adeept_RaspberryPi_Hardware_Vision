#!/usr/bin/env python3
# File name   : vision_system.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
Unified vision system with background capture thread.
Thread-safe shared state for both web streaming and robot control.
"""
import threading
import time
from camera_capture import CameraCapture
from vision_processor import VisionProcessor, VisionResult


class VisionSystem:
    """
    Central vision management.
    Runs capture + CV processing in a single background thread.
    Provides thread-safe access to latest frame and detection result.
    """

    def __init__(self, camera_type="auto", width=640, height=480, fps=30):
        # Hardware & algorithm
        self._camera = CameraCapture(camera_type=camera_type, width=width, height=height, fps=fps)
        self._processor = VisionProcessor(width=width, height=height)

        # Thread-safe shared state
        self._lock = threading.Lock()
        self._latest_frame = None
        self._latest_result = VisionResult()

        # Control flags
        self._running = False
        self._thread = None

    # ====== Mode & parameter control (compatible with original API) ======
    def set_mode(self, mode):
        with self._lock:
            self._processor.set_mode(mode)

    def set_line_threshold(self, value):
        with self._lock:
            self._processor.set_line_threshold(value)

    def set_line_positions(self, pos1, pos2):
        with self._lock:
            self._processor.set_line_positions(pos1, pos2)

    def set_line_color(self, value):
        with self._lock:
            self._processor.set_line_color(value)

    def set_color_range(self, lower, upper):
        with self._lock:
            self._processor.set_color_range(lower, upper)

    def set_app_mode(self, enable):
        with self._lock:
            self._processor.app_mode = enable

    # ====== Thread-safe read APIs ======
    def get_latest_frame(self):
        """Get latest annotated frame (bytes for JPEG or numpy array)"""
        with self._lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    def get_latest_result(self):
        """Get latest vision detection result"""
        with self._lock:
            return self._latest_result

    # ====== Background worker ======
    def _worker(self):
        self._camera.start()
        while self._running:
            frame = self._camera.read_frame()
            if frame is None:
                time.sleep(0.01)
                continue

            # Run vision algorithm
            with self._lock:
                result = self._processor.process(frame)
                self._processor.draw_overlay(frame, result)
                self._latest_frame = frame
                self._latest_result = result

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        print("Vision system background thread started.")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        self._camera.stop()
        print("Vision system stopped.")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False
