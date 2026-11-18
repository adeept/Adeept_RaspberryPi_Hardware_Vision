#!/usr/bin/env python3
# File name   : vision_processor.py
# Website     : www.Adeept.com
# Author      : Adeept
"""OpenCV vision processing layer.
Implements line following, colour tracking and motion detection.
"""
import time
from collections import deque

import cv2
import numpy as np
import imutils


class VisionResult(object):
    """Detection result of a single frame."""

    def __init__(self):
        self.mode = "none"
        # Line follow
        self.line_found = False
        self.line_center = None         # smoothed centre x, what the controller uses
        self.line_center_raw = None     # raw centre x of this frame
        self.line_left_1 = None
        self.line_right_1 = None
        self.line_left_2 = None
        self.line_right_2 = None
        self.line_wide = False          # span over 90% of the width
        self.line_error = 0.0           # normalised error [-1, 1], negative = left
        self.binary_frame = None        # cached binary frame, render only
        # Colour tracking
        self.color_detected = False
        self.color_center_x = None
        self.color_center_y = None
        self.color_radius = 0
        self.color_area = 0             # contour area of the target
        self.color_error_x = 0.0        # normalised error [-1, 1], negative = left
        self.color_recent = False       # target seen within color_timeout seconds
        # Motion detection
        self.motion_detected = False    # motion in this frame
        self.motion_recent = False      # motion within motion_timeout seconds
        self.motion_rect = None         # (x, y, w, h)
        self.motion_area = 0            # area of the largest motion block
        self.motion_boxes = []          # all motion boxes: [(x, y, w, h), ...]

    def to_dict(self):
        """Return a printable dict with the fields of the current mode only.

        binary_frame is left out on purpose: a full frame would flood the console.
        """
        data = {"mode": self.mode}
        if self.mode == "findline":
            data.update({
                "line_found": self.line_found,
                "line_center": self.line_center,
                "line_center_raw": self.line_center_raw,
                "line_error": round(float(self.line_error), 4),
                "line_span_1": (self.line_left_1, self.line_right_1),
                "line_span_2": (self.line_left_2, self.line_right_2),
                "line_wide": self.line_wide,
            })
        elif self.mode == "findColor":
            data.update({
                "color_detected": self.color_detected,
                "color_center": (self.color_center_x, self.color_center_y),
                "color_radius": self.color_radius,
                "color_area": self.color_area,
                "color_error_x": round(float(self.color_error_x), 4),
                "color_recent": self.color_recent,
            })
        elif self.mode == "watchDog":
            data.update({
                "motion_detected": self.motion_detected,
                "motion_recent": self.motion_recent,
                "motion_rect": self.motion_rect,
                "motion_area": self.motion_area,
                "motion_boxes": list(self.motion_boxes),
            })
        return data

    def __str__(self):
        return str(self.to_dict())

    def __repr__(self):
        return "<VisionResult %s>" % (self.to_dict(),)


class VisionProcessor(object):
    """Vision algorithm processor.

    Input: raw BGR frame. Output: VisionResult plus an annotated frame.
    """

    def __init__(self, width=640, height=480):
        self.width = width
        self.height = height
        self.mode = "none"              # none / findline / findColor / watchDog

        # Line follow
        self.line_threshold = 80
        self.use_otsu = False           # True ignores line_threshold and uses Otsu
        # Scan lines are placed by image height ratio; 480p gives the old 440 / 380
        self.line_pos_1 = int(round(height * 440.0 / 480.0))
        self.line_pos_2 = int(round(height * 380.0 / 480.0))
        self.line_color_value = 0       # 0 tracks a black line, 255 a white one
        self.line_min_pixels = 4        # minimum pixels of one continuous run
        self.line_smooth_window = 3     # median window of centre x, 1 disables it
        self.enable_render = True
        self._line_center_hist = deque(maxlen=max(1, int(self.line_smooth_window)))

        # Colour tracking
        self.color_lower = np.array([24, 100, 100], dtype=np.uint8)
        self.color_upper = np.array([44, 255, 255], dtype=np.uint8)
        self.color_min_area = 200       # drop smaller contours (noise)
        self.color_min_radius = 10      # minimum enclosing radius
        self.color_timeout = 0.3        # seconds, hold time of color_recent
        self.app_mode = False           # thresholds came from the app scale
        self.legacy_app_hsv = False     # old BGR2RGB-as-HSV path, A/B on device only
        self._last_color_time = 0.0

        # Motion detection
        self.motion_min_area = 5000     # smaller contours are not motion
        self.motion_timeout = 0.5       # seconds, hold time of motion_recent
        self.motion_keep_frames = 15    # keep the box this long when the target blinks
        self._avg_background = None
        self._last_motion_time = time.monotonic()
        self._locked_rect = None
        self._lost_frames = 0

    def set_mode(self, mode):
        """Set the working mode."""
        if mode == self.mode:
            return
        self.mode = mode
        self._reset_state()

    def _reset_state(self):
        self._avg_background = None
        self._locked_rect = None
        self._lost_frames = 0
        self._last_motion_time = time.monotonic()
        self._last_color_time = 0.0
        self._line_center_hist.clear()

    # ===== Parameter setters =====
    def set_line_threshold(self, value):
        self.line_threshold = value

    def set_line_positions(self, pos1, pos2):
        self.line_pos_1 = pos1
        self.line_pos_2 = pos2

    def set_line_color(self, value):
        self.line_color_value = value

    def set_color_range(self, lower_hsv, upper_hsv):
        self.color_lower = np.array(lower_hsv, dtype=np.uint8)
        self.color_upper = np.array(upper_hsv, dtype=np.uint8)

    # ===== Core algorithms =====
    @staticmethod
    def _longest_run(idx):
        """Return (start, end) of the longest continuous run of indices."""
        if idx.size == 0:
            return None
        splits = np.where(np.diff(idx) > 1)[0]
        starts = np.concatenate(([0], splits + 1))
        ends = np.concatenate((splits, [idx.size - 1]))
        lengths = idx[ends] - idx[starts] + 1
        best = int(np.argmax(lengths))
        return int(idx[starts[best]]), int(idx[ends[best]])

    def _scan_line(self, bw, row_y, width):
        """Return (left, right, wide) of the line on one scan row, or None."""
        idx = np.where(bw[row_y] == self.line_color_value)[0]
        if idx.size == 0:
            return None
        if idx.size >= int(width * 0.98):
            return 0, width - 1, True
        run = self._longest_run(idx)
        if run is None or (run[1] - run[0] + 1) < self.line_min_pixels:
            return None
        return run[0], run[1], ((run[1] - run[0] + 1) >= int(width * 0.9))

    def _process_line_follow(self, img, result: VisionResult):
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if self.use_otsu:
            _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        else:
            _, bw = cv2.threshold(gray, self.line_threshold, 255, cv2.THRESH_BINARY)
        bw = cv2.erode(bw, None, iterations=2)
        bw = cv2.dilate(bw, None, iterations=2)

        if self.enable_render:
            result.binary_frame = cv2.merge((bw, bw, bw))

        p1 = min(max(int(self.line_pos_1), 0), h - 1)
        p2 = min(max(int(self.line_pos_2), 0), h - 1)
        span_1 = self._scan_line(bw, p1, w)
        span_2 = self._scan_line(bw, p2, w)
        if span_1 is None or span_2 is None:
            self._line_center_hist.clear()
            return

        l1, r1, wide_1 = span_1
        l2, r2, wide_2 = span_2
        center_raw = ((l1 + r1) // 2 + (l2 + r2) // 2) // 2

        result.line_left_1, result.line_right_1 = l1, r1
        result.line_left_2, result.line_right_2 = l2, r2
        result.line_center_raw = center_raw
        result.line_wide = bool(wide_1 or wide_2)
        result.line_found = True

        if self.line_smooth_window > 1:
            self._line_center_hist.append(center_raw)
            center = int(np.median(self._line_center_hist))
        else:
            center = center_raw
        result.line_center = center

        half = (w - 1) / 2.0
        result.line_error = 0.0 if half <= 0 else float((center - half) / half)

    def _process_color_track(self, img, result: VisionResult):
        h, w = img.shape[:2]
        now = time.monotonic()
        # A single missed frame does not clear it; color_recent gives 0.3 s of slack
        result.color_recent = (now - self._last_color_time) <= self.color_timeout

        if self.legacy_app_hsv:
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)      # old path: channels swapped, used as HSV
        else:
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        lower = self.color_lower
        upper = self.color_upper
        if int(lower[0]) > int(upper[0]):                    # hue range wraps past 0 or 180
            part_a = cv2.inRange(
                hsv,
                np.array([lower[0], lower[1], lower[2]], dtype=np.uint8),
                np.array([180, upper[1], upper[2]], dtype=np.uint8),
            )
            part_b = cv2.inRange(
                hsv,
                np.array([0, lower[1], lower[2]], dtype=np.uint8),
                np.array([upper[0], upper[1], upper[2]], dtype=np.uint8),
            )
            mask = cv2.bitwise_or(part_a, part_b)
        else:
            mask = cv2.inRange(hsv, lower, upper)

        mask = cv2.GaussianBlur(mask, (5, 5), 0)
        mask = cv2.erode(mask, None, iterations=2)
        mask = cv2.dilate(mask, None, iterations=2)

        cnts = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = imutils.grab_contours(cnts)
        if len(cnts) == 0:
            return

        c = max(cnts, key=cv2.contourArea)
        area = cv2.contourArea(c)
        if area < self.color_min_area:
            return

        (cx, cy), radius = cv2.minEnclosingCircle(c)
        if radius < self.color_min_radius:
            return

        # The centroid fits irregular or occluded targets better than the circle centre
        moments = cv2.moments(c)
        if moments["m00"] > 0:
            cx = moments["m10"] / moments["m00"]
            cy = moments["m01"] / moments["m00"]

        result.color_detected = True
        result.color_center_x = int(cx)
        result.color_center_y = int(cy)
        result.color_radius = float(radius)
        result.color_area = int(area)

        half = (w - 1) / 2.0
        result.color_error_x = 0.0 if half <= 0 else float((cx - half) / half)
        result.color_recent = True
        self._last_color_time = now

    def _process_motion(self, img, result: VisionResult):
        now = time.monotonic()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if self._avg_background is None:
            self._avg_background = gray.astype("float")
            self._last_motion_time = now
            return

        cv2.accumulateWeighted(gray, self._avg_background, 0.5)
        frame_delta = cv2.absdiff(gray, cv2.convertScaleAbs(self._avg_background))
        thresh = cv2.threshold(frame_delta, 5, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)

        cnts = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = imutils.grab_contours(cnts)

        boxes = []
        for c in cnts:
            area = cv2.contourArea(c)
            if area < self.motion_min_area:
                continue
            x, y, w, h = cv2.boundingRect(c)
            boxes.append((area, x, y, w, h))

        if boxes:
            boxes.sort(key=lambda item: item[0], reverse=True)
            result.motion_boxes = [(x, y, w, h) for (_, x, y, w, h) in boxes]
            self._locked_rect = result.motion_boxes[0]
            result.motion_rect = self._locked_rect
            result.motion_area = int(boxes[0][0])
            result.motion_detected = True
            self._last_motion_time = now
            self._lost_frames = 0
        else:
            self._lost_frames += 1
            if self._locked_rect is not None and self._lost_frames < self.motion_keep_frames:
                result.motion_rect = self._locked_rect     # hold the box, no flicker
            else:
                self._locked_rect = None

        result.motion_recent = (now - self._last_motion_time) <= self.motion_timeout

    # ===== Public interface =====
    def process(self, frame):
        """Process one frame and return a VisionResult."""
        result = VisionResult()
        result.mode = self.mode
        if self.mode == "findline":
            self._process_line_follow(frame, result)
        elif self.mode == "findColor":
            self._process_color_track(frame, result)
        elif self.mode == "watchDog":
            self._process_motion(frame, result)
        return result

    # ===== Rendering =====
    # Overlay colours, BGR. Every stroke gets a dark halo so it stays readable on
    # the white pixels of the binary mask and on bright parts of a colour frame.
    _FONT = cv2.FONT_HERSHEY_SIMPLEX
    _C_OK = (80, 240, 60)           # green: target found / locked
    _C_WARN = (0, 200, 255)         # amber: lost, holding, uncertain
    _C_ACCENT = (0, 127, 255)       # cyan: scan rows, guides, corner marks
    _C_DIM = (170, 170, 170)        # grey: idle text and reference lines
    _C_DARK = (0, 0, 0)

    def _halo_line(self, frame, p1, p2, color, thickness=2):
        cv2.line(frame, p1, p2, self._C_DARK, thickness + 3, cv2.LINE_AA)
        cv2.line(frame, p1, p2, color, thickness, cv2.LINE_AA)

    def _halo_circle(self, frame, center, radius, color, thickness=2):
        cv2.circle(frame, center, radius, self._C_DARK, thickness + 3, cv2.LINE_AA)
        cv2.circle(frame, center, radius, color, thickness, cv2.LINE_AA)

    def _dash_h(self, frame, y, x1, x2, color, dash=18, gap=12, thickness=1):
        for x in range(int(x1), int(x2), dash + gap):
            cv2.line(frame, (x, y), (min(x + dash, x2), y), color, thickness, cv2.LINE_AA)

    def _dash_v(self, frame, x, y1, y2, color, dash=14, gap=12, thickness=1):
        for y in range(int(y1), int(y2), dash + gap):
            cv2.line(frame, (x, y), (x, min(y + dash, y2)), color, thickness, cv2.LINE_AA)

    def _chip(self, frame, text, color, scale=0.55, x=14, y=12):
        """Text on a darkened plate with a coloured border: readable on any background."""
        (tw, th), _ = cv2.getTextSize(text, self._FONT, scale, 1)
        x0, y0 = int(x), int(y)
        x1 = min(x0 + tw + 18, frame.shape[1] - 1)
        y1 = min(y0 + th + 16, frame.shape[0] - 1)
        sub = frame[y0:y1, x0:x1]
        if sub.size:
            sub[:] = (sub * 0.25).astype(sub.dtype)
        cv2.rectangle(frame, (x0, y0), (x1, y1), color, 1, cv2.LINE_AA)
        cv2.putText(frame, text, (x0 + 9, y1 - 9), self._FONT, scale, color, 1, cv2.LINE_AA)

    def _corners(self, frame, rect, color, size=16, thickness=3):
        """Corner brackets instead of a full box: marks the target without covering it."""
        h, w = frame.shape[:2]
        x, y, bw, bh = [int(v) for v in rect]
        x1, y1 = min(x + bw, w - 1), min(y + bh, h - 1)
        x, y = max(x, 0), max(y, 0)
        segs = (
            ((x, y), (min(x + size, x1), y)), ((x, y), (x, min(y + size, y1))),
            ((x1, y), (max(x1 - size, x), y)), ((x1, y), (x1, min(y + size, y1))),
            ((x, y1), (min(x + size, x1), y1)), ((x, y1), (x, max(y1 - size, y))),
            ((x1, y1), (max(x1 - size, x), y1)), ((x1, y1), (x1, max(y1 - size, y))),
        )
        for a, b in segs:
            cv2.line(frame, a, b, self._C_DARK, thickness + 2, cv2.LINE_AA)
            cv2.line(frame, a, b, color, thickness, cv2.LINE_AA)

    def _error_bar(self, frame, error, color):
        """Horizontal steering scale: the centre tick is zero, the dot is the current error."""
        h, w = frame.shape[:2]
        y = h - 14
        half = w / 2.0 - 48
        x_mid = int(round(w / 2.0))
        dot = int(round(w / 2.0 + max(-1.0, min(1.0, float(error))) * half))
        cv2.line(frame, (48, y), (w - 48, y), (70, 70, 70), 2, cv2.LINE_AA)
        cv2.line(frame, (x_mid, y - 7), (x_mid, y + 7), self._C_ACCENT, 2, cv2.LINE_AA)
        cv2.circle(frame, (dot, y), 7, self._C_DARK, -1, cv2.LINE_AA)
        cv2.circle(frame, (dot, y), 4, color, -1, cv2.LINE_AA)

    def _draw_line(self, frame, result, h, w, scale):
        # The binary mask is what the algorithm sees, so it is the background here
        if result.binary_frame is not None and result.binary_frame.shape == frame.shape:
            frame[:] = result.binary_frame

        p1 = min(max(int(self.line_pos_1), 1), h - 2)
        p2 = min(max(int(self.line_pos_2), 1), h - 2)
        name = "WHITE" if self.line_color_value == 255 else "BLACK"

        p_hight = int(abs(abs(self.line_pos_1) - abs(self.line_pos_2)) / 2) - 10

        self._dash_h(frame, p1, 0, w - 1, self._C_ACCENT)              # scan rows
        self._dash_h(frame, p2, 0, w - 1, self._C_ACCENT)

        if result.line_found and result.line_center is not None:
            # Detected run on each scan row, thicker than the halo of the guide lines
            self._halo_line(frame, (result.line_left_1, p1), (result.line_right_1, p1), self._C_OK, 2)
            self._halo_line(frame, (result.line_left_2, p2), (result.line_right_2, p2), self._C_OK, 2)
            # Line centre between the two rows
            mid_y = (p1 + p2) // 2
            self._halo_line(frame, (result.line_center, mid_y - p_hight),
                            (result.line_center, mid_y + p_hight), self._C_OK, 2)
            self._chip(frame, "LINE %s  err %+.2f  x %d" %
                       (name, result.line_error, result.line_center), self._C_OK, scale)
        else:
            self._chip(frame, "LINE %s  LOST" % name, self._C_WARN, scale)

    def _draw_color(self, frame, result, h, w, scale):
        # Fixed crosshair marks the optical axis; the target circle is compared against it
        x_ref, y_ref = (w - 1) // 2, h // 2
        self._halo_line(frame, (x_ref - 10, y_ref), (x_ref + 10, y_ref), self._C_ACCENT, 1)
        self._halo_line(frame, (x_ref, y_ref - 10), (x_ref, y_ref + 10), self._C_ACCENT, 1)

        if result.color_detected:
            cx, cy = int(result.color_center_x), int(result.color_center_y)
            r = int(max(result.color_radius, 4))
            self._halo_circle(frame, (cx, cy), r, self._C_OK, 2)
            cv2.circle(frame, (cx, cy), 7, self._C_DARK, -1, cv2.LINE_AA)
            cv2.circle(frame, (cx, cy), 3, self._C_OK, -1, cv2.LINE_AA)
            self._error_bar(frame, result.color_error_x, self._C_OK)
            self._chip(frame, "COLOR  err %+.2f  r %d" %
                       (result.color_error_x, int(result.color_radius)),
                       self._C_OK, scale)
        elif result.color_recent:
            self._chip(frame, "COLOR  HOLD", self._C_WARN, scale)
        else:
            self._chip(frame, "COLOR  SEARCHING", self._C_DIM, scale)

    def _draw_motion(self, frame, result, h, w, scale):
        if result.motion_rect is None:
            self._chip(frame, "MOTION  IDLE", self._C_DIM, scale)
            return

        color = self._C_OK if result.motion_detected else self._C_WARN
        x, y = int(result.motion_rect[0]), int(result.motion_rect[1])
        x2, y2 = x + int(result.motion_rect[2]), y + int(result.motion_rect[3])
        cv2.rectangle(frame, (x, y), (x2, y2), color, 1, cv2.LINE_AA)  # thin frame
        self._corners(frame, result.motion_rect, self._C_ACCENT)        # thick corners

        ratio = 100.0 * result.motion_area / float(w * h)
        state = "LOCK" if result.motion_detected else "HOLD"
        self._chip(frame, "MOTION %s  %.1f%%" % (state, ratio), color, scale)

    def draw_overlay(self, frame, result: VisionResult):
        """Draw detection annotations on the frame (in place)."""
        if self.mode == "none" or not self.enable_render:
            return frame

        h, w = frame.shape[:2]
        scale = 0.6 if w >= 480 else 0.45
        if self.mode == "findline":
            self._draw_line(frame, result, h, w, scale)
        elif self.mode == "findColor":
            self._draw_color(frame, result, h, w, scale)
        elif self.mode == "watchDog":
            self._draw_motion(frame, result, h, w, scale)
        return frame
