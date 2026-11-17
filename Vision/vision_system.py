#!/usr/bin/env python3
# File name   : vision_system.py
# Website     : www.Adeept.com
# Author      : Adeept
"""Unified vision system with a background capture thread.
Thread-safe shared state for both web streaming and robot control.
"""
import threading
import time

from camera_capture import CameraCapture
from vision_processor import VisionProcessor, VisionResult


class VisionSystem:
    """Central vision management.

    Runs capture and CV processing in two background threads and exposes
    thread-safe access to the latest frame and detection result.
    """

    # The single active instance in this process.
    _active = None

    @classmethod
    def get_active(cls):
        """Return the VisionSystem started in this process, or None."""
        return cls._active

    def __init__(self, camera_type="auto", width=640, height=480, fps=30):
        self._camera = CameraCapture(camera_type=camera_type, width=width, height=height, fps=fps)
        self._processor = VisionProcessor(width=width, height=height)
        self.width = width
        self.height = height

        # Raw frame slot: written by the capture thread, read by the process thread
        self._camera_lock = threading.Lock()
        self._raw_frame = None
        self._raw_seq = 0
        self._camera_ready = False

        # Output slot: written by the process thread, read by web and robot code
        self._output_lock = threading.Lock()
        self._display_frame = None
        self._latest_result = VisionResult()
        self._result_seq = 0
        self._processed_count = 0       # raw_seq minus this is the number of dropped frames
        self._last_result_time = 0.0

        # Mode switches take effect on a frame boundary, never mid-algorithm
        self._pending_mode = None

        self._running = False
        self._last_error = None
        self._capture_thread = None
        self._process_thread = None

    # ====== Mode and parameters ======
    def set_mode(self, mode):
        """Switch mode. Applied on the next frame, so do not read the result immediately.

        :param mode: "findline" / "findColor" / "watchDog" / "none"
        """
        self._pending_mode = mode

    def get_mode(self):
        """Mode currently used by the processor. Defaults to "none": no detection."""
        return self._processor.mode

    def set_line_threshold(self, value):
        self._processor.set_line_threshold(value)

    def set_line_positions(self, pos1, pos2):
        self._processor.set_line_positions(pos1, pos2)

    def set_line_color(self, value):
        self._processor.set_line_color(value)

    def set_color_range(self, lower, upper):
        self._processor.set_color_range(lower, upper)

    def set_app_mode(self, enable):
        self._processor.app_mode = enable

    def set_legacy_app_hsv(self, enable):
        """Reproduce the old app path (BGR2RGB as HSV), on-device comparison only."""
        self._processor.legacy_app_hsv = bool(enable)

    # ====== Thread-safe read APIs ======
    def get_latest_frame(self):
        """Latest annotated frame."""
        with self._output_lock:
            return self._display_frame.copy() if self._display_frame is not None else None

    def get_raw_frame(self):
        """Latest raw BGR frame."""
        with self._camera_lock:
            return self._raw_frame.copy() if self._raw_frame is not None else None

    def get_latest_result(self):
        """Latest VisionResult."""
        with self._output_lock:
            return self._latest_result

    def get_latest_result_seq(self):
        with self._output_lock:
            return self._result_seq

    def wait_new_result(self, last_seq, timeout=0.5):
        """Block until a result newer than last_seq is published.

        :param last_seq: frame number from the previous call (0 the first time)
        :param timeout: maximum seconds to wait
        :return: (seq, result); (last_seq, None) when nothing new arrived
        """
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            with self._output_lock:
                if self._result_seq > last_seq:
                    return self._result_seq, self._latest_result
                seq = self._result_seq
            if time.monotonic() >= deadline:
                return seq, None
            time.sleep(0.002)

    def get_stats(self):
        with self._camera_lock:
            raw_seq = self._raw_seq
            camera_ready = self._camera_ready
        with self._output_lock:
            result_seq = self._result_seq
            processed = self._processed_count
            last_time = self._last_result_time
        age = time.monotonic() - last_time if last_time else float("inf")
        return {
            "raw_seq": raw_seq,
            "result_seq": result_seq,
            "processed_frames": processed,
            "dropped_frames": max(0, raw_seq - processed),
            "camera_ready": camera_ready,
            "processing_age": age,
            "last_error": self._last_error,
            "running": self._running,
        }

    def healthy(self):
        stats = self.get_stats()
        return (stats["running"] and stats["last_error"] is None
                and stats["camera_ready"] and stats["processing_age"] < 2.0)

    # ====== Background workers ======
    def _capture_worker(self):
        try:
            self._camera.start()
        except Exception as e:
            self._last_error = "camera start failed: %s" % e
            print(self._last_error)
            self._running = False
            return

        with self._camera_lock:
            self._camera_ready = True

        try:
            while self._running:
                frame = self._camera.read_frame()
                if frame is None:
                    time.sleep(0.01)
                    continue
                with self._camera_lock:
                    self._raw_frame = frame
                    self._raw_seq += 1
        except Exception as e:
            self._last_error = "capture failed: %s" % e
            print(self._last_error)
        finally:
            try:
                self._camera.stop()
            except Exception:
                pass
            with self._camera_lock:
                self._camera_ready = False
            self._running = False

    def _process_worker(self):
        last_seq = 0
        while self._running:
            with self._camera_lock:
                frame = self._raw_frame
                seq = self._raw_seq

            if frame is None or seq == last_seq:
                time.sleep(0.002)       # wait for a new frame, no busy loop
                continue
            last_seq = seq

            if self._pending_mode is not None:
                mode, self._pending_mode = self._pending_mode, None
                self._processor.set_mode(mode)

            try:
                result = self._processor.process(frame)
                display = frame.copy()
                self._processor.draw_overlay(display, result)
            except Exception as e:
                self._last_error = "process failed: %s" % e
                print(self._last_error)
                time.sleep(0.05)
                continue

            with self._output_lock:
                self._display_frame = display
                self._latest_result = result
                self._result_seq = seq
                self._processed_count += 1
                self._last_result_time = time.monotonic()

    def start(self):
        if self._running:
            return
        self._running = True
        self._last_error = None
        self._capture_thread = threading.Thread(target=self._capture_worker, name="vision-capture", daemon=True)
        self._process_thread = threading.Thread(target=self._process_worker, name="vision-process", daemon=True)
        self._capture_thread.start()
        self._process_thread.start()
        VisionSystem._active = self
        print("Vision system started (capture + process threads).")

    def stop(self):
        self._running = False
        for thread in (self._process_thread, self._capture_thread):
            if thread is not None and thread.is_alive():
                thread.join(timeout=3)
                if thread.is_alive():
                    print("Warning: %s did not exit in time (camera may still be releasing)"
                          % thread.name)
        self._process_thread = None
        self._capture_thread = None
        with self._output_lock:
            self._display_frame = None      # cleared so streaming threads exit
        if VisionSystem._active is self:
            VisionSystem._active = None
        print("Vision system stopped.")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False
