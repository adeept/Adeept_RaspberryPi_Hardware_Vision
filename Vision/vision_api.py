#!/usr/bin/env python3
# File name   : vision_api.py
# Website     : www.Adeept.com
# Author      : Adeept
"""Adeept vision module - single public interface.
Camera selection: "auto" detects the type, "usb" forces V4L2, "csi" forces Picamera2.
"""
import threading
import time

import cv2
import numpy as np

import vision_system as _vision

class Vision(object):
    """Single public interface of the vision module (process-wide singleton).

    Covers start/stop, camera selection, mode and thresholds, results,
    raw frames and the optional web stream.
    """

    _instance = None
    _instance_lock = threading.Lock()

    def __init__(self):
        self._lock = threading.RLock()
        self._system = None
        self._web_thread = None
        # JPEG cache: one encode per frame, shared by all clients (saves Pi CPU)
        self._jpeg_lock = threading.Lock()
        self._jpeg_seq = -1
        self._jpeg_bytes = None
        self._placeholder = None

    @classmethod
    def get(cls):
        """Return the process-wide singleton, so all modules share one instance."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ====== Lifecycle ======
    def start(self, camera_type="auto", width=640, height=480, fps=30, web=False, host="0.0.0.0", port=5000):
        """Start the vision system (idempotent: reuse it if already running).

        :param camera_type: "auto" / "usb" / "csi", only used on the first start
        :param web: also start the Flask stream in a daemon thread
        :return: self, for chaining
        """
        with self._lock:
            active = _vision.VisionSystem.get_active()
            if active is not None:
                self._system = active
            else:
                self._system = _vision.VisionSystem(
                    camera_type=camera_type, width=width, height=height, fps=fps)
                self._system.start()
        if web:
            self.spawn_web(host=host, port=port)
        return self

    def stop(self):
        """Stop vision and release the camera. The web thread is a daemon."""
        with self._lock:
            system = _vision.VisionSystem.get_active()
            if system is not None:
                system.stop()
            self._system = None
            with self._jpeg_lock:
                self._jpeg_seq = -1
                self._jpeg_bytes = None

    def system(self):
        """Underlying VisionSystem instance (advanced use; prefer the wrappers below)."""
        return _vision.VisionSystem.get_active()

    def is_running(self):
        system = self.system()
        return bool(system is not None and system.get_stats()["running"])

    def _require(self):
        system = self.system()
        if system is None:
            raise RuntimeError("Vision.start() has not been called")
        return system

    # ====== Mode and parameters ======
    def set_mode(self, mode):
        """Switch mode, applied on the next frame (asynchronous).

        :param mode: "findline" / "findColor" / "watchDog" / "none"
        """
        self._require().set_mode(mode)

    def get_mode(self):
        """Mode currently used by the processor. "none" means no detection."""
        return self._require().get_mode()

    def set_line_threshold(self, value):
        self._require().set_line_threshold(value)

    def set_line_positions(self, pos1, pos2):
        self._require().set_line_positions(pos1, pos2)

    def set_line_color(self, value):
        self._require().set_line_color(value)

    def set_color_range(self, lower, upper):
        self._require().set_color_range(lower, upper)

    # ====== HSV form ======
    @staticmethod
    def hsv_range(H, S, V, dh, ds, dv):
        """Expand an HSV centre + tolerance into OpenCV's [lower, upper].

        H uses OpenCV's 0..180 scale (not 0..255). A range crossing 0 or 180 is
        returned as lower[0] > upper[0]; the algorithm splits it into two masks.
        """
        H = int(max(0, min(180, H)))
        S = int(max(0, min(255, S)))
        V = int(max(0, min(255, V)))
        dh = int(max(0, min(90, dh)))
        ds = int(max(0, min(255, ds)))
        dv = int(max(0, min(255, dv)))

        s1, s2 = max(0, S - ds), min(255, S + ds)
        v1, v2 = max(0, V - dv), min(255, V + dv)

        if 2 * dh >= 180:                   # half width covers the whole hue circle
            return [0, s1, v1], [180, s2, v2]

        h1, h2 = H - dh, H + dh
        if h1 < 0:                          # wraps past 0
            return [180 + h1, s1, v1], [h2, s2, v2]
        if h2 > 180:                        # wraps past 180
            return [h1, s1, v1], [h2 - 180, s2, v2]
        return [h1, s1, v1], [h2, s2, v2]

    def set_color_hsv(self, H, S, V, dh=15, ds=150, dv=150):
        """Set the colour range from an HSV centre; web and app share this entry.

        :param H: 0..180 centre hue
        :param S: 0..255 centre saturation
        :param V: 0..255 centre brightness
        :param dh: half width of hue, larger is looser
        :param ds: half width of saturation
        :param dv: half width of brightness
        """
        lower, upper = self.hsv_range(H, S, V, dh, ds, dv)
        self._require().set_color_range(lower, upper)

    def set_color_hsv_app(self, H, S, V, h_max=255):
        """App-side scale: H arrives as 0..h_max (255 = full 360 circle by default).

        The app sends raw colour-wheel values, so the scale difference is resolved
        on the threshold side only; the image is always converted with BGR2HSV.
        S and V already match OpenCV (0..255).
        """
        scale = 180.0 / float(h_max)
        self.set_app_mode(True)
        self.set_color_hsv(
            int(round(H * scale)), S, V,
            dh=int(round(100 * scale)), ds=100, dv=100,
        )

    def set_legacy_hsv(self, enable):
        """Reproduce the old app-mode path (BGR2RGB used as HSV), for on-device A/B only."""
        self._require().set_legacy_app_hsv(enable)

    def set_app_mode(self, enable):
        """Record that thresholds came from the app scale; does not change detection."""
        self._require().set_app_mode(enable)

    # Legacy names kept for existing callers
    colorFindSet = set_color_hsv
    colorFindSetApp = set_color_hsv_app

    # ====== From the RGB colour wheel ======
    @staticmethod
    def rgb_to_hsv(r, g, b):
        """sRGB (0..255) -> OpenCV (H, S, V) with H in 0..180 and S/V in 0..255."""
        px = np.uint8([[[int(b), int(g), int(r)]]])     # OpenCV expects BGR
        hsv = cv2.cvtColor(px, cv2.COLOR_BGR2HSV)[0][0]
        return int(hsv[0]), int(hsv[1]), int(hsv[2])

    def set_color_rgb(self, r, g, b, dh=15, ds=150, dv=150):
        """Set thresholds from a colour-wheel RGB value (offline conversion, a starting point).

        :return: converted (H, S, V), handy for logging
        """
        H, S, V = self.rgb_to_hsv(r, g, b)
        self.set_color_hsv(H, S, V, dh=dh, ds=ds, dv=dv)
        return H, S, V

    def set_color_at(self, x, y, patch=8, dh=None, ds=None, dv=None):
        """Sample the current frame at (x, y) and derive thresholds from it.

        Far more reliable than converting a colour-wheel RGB value, because this is
        what the camera actually sees (white balance, exposure and light included).
        Passing None for dh/ds/dv derives the tolerance from the sample spread.

        :return: (H, S, V, dh, ds, dv)
        """
        frame = self.raw_frame()
        if frame is None:
            raise RuntimeError("vision is not running or has no frame yet")

        h, w = frame.shape[:2]
        x = int(max(0, min(w - 1, x)))
        y = int(max(0, min(h - 1, y)))
        r = max(1, int(patch))
        x1, x2 = max(0, x - r), min(w, x + r + 1)
        y1, y2 = max(0, y - r), min(h, y + r + 1)

        hsv = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
        hsv = hsv.reshape(-1, 3).astype(np.float32)

        # Grey, black and over-exposed edge pixels are unreliable, drop them
        usable = (hsv[:, 1] > 40) & (hsv[:, 2] > 40)
        if usable.sum() < max(4, len(hsv) // 4):
            usable = np.ones(len(hsv), dtype=bool)

        # Hue is circular: average as angles or red 0 and red 179 cancel out
        ang = np.deg2rad(hsv[usable, 0] * 2.0)
        cm, sm = float(np.cos(ang).mean()), float(np.sin(ang).mean())
        mean_deg = (np.degrees(np.arctan2(sm, cm)) + 360.0) % 360.0
        result_len = min(1.0, float(np.hypot(cm, sm)))
        std_deg = 180.0 if result_len <= 1e-6 else float(np.degrees(np.sqrt(-2.0 * np.log(result_len))))

        H = int(mean_deg // 2) % 180
        S = int(np.median(hsv[usable, 1]))
        V = int(np.median(hsv[usable, 2]))

        if dh is None:
            dh = max(10, int(round(std_deg / 2.0 * 3)))         # 3 sigma, at least +-10
        if ds is None:
            ds = max(60, int(round(float(hsv[usable, 1].std()) * 3)))
        if dv is None:
            dv = max(60, int(round(float(hsv[usable, 2].std()) * 3)))
        dh, ds, dv = min(int(dh), 90), min(int(ds), 255), min(int(dv), 255)

        self.set_color_hsv(H, S, V, dh=dh, ds=ds, dv=dv)
        return H, S, V, dh, ds, dv

    # ====== Results ======
    def wait_result(self, last_seq, timeout=0.5):
        """Wait for a result newer than last_seq.

        :return: (seq, VisionResult); on timeout (last_seq, None)
        """
        return self._require().wait_new_result(last_seq, timeout)

    def result(self):
        """Latest VisionResult object."""
        return self._require().get_latest_result()

    def result_seq(self):
        """Frame number the latest result belongs to."""
        return self._require().get_latest_result_seq()

    def raw_frame(self):
        """Latest raw BGR frame, without overlay (use it for MediaPipe etc.)."""
        return self._require().get_raw_frame()

    def frame(self):
        """Latest annotated frame, with detection drawn on it."""
        return self._require().get_latest_frame()

    def stats(self):
        """Runtime counters: raw_seq / result_seq / processed_frames / dropped_frames / ..."""
        return self._require().get_stats()

    def healthy(self):
        """True when the camera is ready, processing advances and no error occurred."""
        return self._require().healthy()

    # ====== Frames for streaming (consumed by the app view layer) ======
    def _make_placeholder(self):
        if self._placeholder is None:
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(img, "NO CAMERA / VISION NOT READY", (70, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
            ok, buf = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            self._placeholder = buf.tobytes() if ok else b''
        return self._placeholder

    def jpeg(self):
        """Return (seq, jpeg_bytes) for MJPEG streaming.

        One encode per frame shared by all clients; a placeholder when there is no frame.
        """
        seq = self.result_seq()
        frame = self.frame()
        if frame is None:
            return 0, self._make_placeholder()
        with self._jpeg_lock:
            if seq == self._jpeg_seq and self._jpeg_bytes:
                return self._jpeg_seq, self._jpeg_bytes
            ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if not ok:
                return 0, None
            self._jpeg_seq = seq
            self._jpeg_bytes = buf.tobytes()
            return self._jpeg_seq, self._jpeg_bytes

    # ====== Web streaming ======
    def _load_app(self):
        """Lazily import the view layer and inject the frame source into it.

        Dependencies stay one way: vision_api -> app. app.py never imports this module.
        """
        import app as _app
        _app.bind_stream(self.jpeg, self.is_running)
        return _app

    def spawn_web(self, host="0.0.0.0", port=5000):
        """Start Flask in a daemon thread; returns the thread (cannot start twice)."""
        with self._lock:
            if self._web_thread is not None and self._web_thread.is_alive():
                return self._web_thread
            _app = self._load_app()
            self._web_thread = threading.Thread(target=_app.app.run,
                kwargs=dict(host=host, port=port, threaded=True),
                name="vision-web", daemon=True)
            self._web_thread.start()
            return self._web_thread

    def serve_web(self, host="0.0.0.0", port=5000):
        """Run Flask in the calling thread, when the web server should own it."""
        self._load_app().app.run(host=host, port=port, threaded=True)

# ====== Command line entry ======
def main(argv=None):
    """Single entry point: python3 vision_api.py [auto|usb|csi] [--camera=csi] [--port=5000]"""
    import argparse

    parser = argparse.ArgumentParser(description="Adeept vision service")
    parser.add_argument("camera", nargs="?", default=None, choices=("auto", "usb", "csi"))
    parser.add_argument("--camera", dest="camera_opt", choices=("auto", "usb", "csi"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--no-web", action="store_true", help="run vision only, no Flask")
    args = parser.parse_args(argv)

    camera_type = args.camera_opt or args.camera or "auto"
    vision = Vision.get()
    vision.start(camera_type=camera_type, web=not args.no_web,
                 host=args.host, port=args.port)
    # vision.set_mode("findline")
    # vision.set_mode("watchDog")  
    vision.set_mode("findColor")
    try:
        while True:
            time.sleep(1)
            print(vision.result())
    except KeyboardInterrupt:
        pass
    finally:
        vision.stop()


if __name__ == "__main__":
    main()
