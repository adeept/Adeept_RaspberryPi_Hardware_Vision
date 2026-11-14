#!/usr/bin/env python3
# File name   : vision_processor.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
OpenCV vision processing layer.
Implements line following, color tracking and motion detection algorithms.
Fixed: line follow mode now renders binary thresholded frame (same as original code).
"""
import cv2
import numpy as np
import imutils
import datetime


class VisionResult:
    """Structured vision detection result"""
    def __init__(self):
        self.mode = "none"
        # Line follow
        self.line_found = False
        self.line_center = None
        self.line_left_1 = None
        self.line_right_1 = None
        self.line_left_2 = None
        self.line_right_2 = None
        self.binary_frame = None  # 新增：缓存二值化三通道画面，用于渲染
        # Color tracking
        self.color_detected = False
        self.color_center_x = None
        self.color_center_y = None
        self.color_radius = 0
        # Motion detection
        self.motion_detected = False
        self.motion_rect = None  # (x, y, w, h)


class VisionProcessor:
    """
    Vision algorithm processor.
    Input: raw BGR image
    Output: VisionResult + annotated image
    """

    def __init__(self, width=640, height=480):
        self.width = width
        self.height = height
        self.mode = "findline"  # none / findline / findColor / watchDog

        # ===== Line follow parameters =====
        self.line_threshold = 80
        self.line_pos_1 = 440
        self.line_pos_2 = 380
        self.line_color_value = 0
        self.enable_render = True

        # ===== Color tracking parameters =====
        self.color_lower = np.array([24, 100, 100])
        self.color_upper = np.array([44, 255, 255])
        self.app_mode = False  # True = RGB input from APP

        # ===== Motion detection state =====
        self._avg_background = None
        self._last_motion_time = datetime.datetime.now()
        self._motion_counter = 0

    def set_mode(self, mode):
        """Set vision working mode"""
        self.mode = mode
        if mode != "watchDog":
            self._avg_background = None

    # ===== Parameter setters =====
    def set_line_threshold(self, value):
        self.line_threshold = value

    def set_line_positions(self, pos1, pos2):
        self.line_pos_1 = pos1
        self.line_pos_2 = pos2

    def set_line_color(self, value):
        self.line_color_value = value

    def set_color_range(self, lower_hsv, upper_hsv):
        self.color_lower = np.array(lower_hsv)
        self.color_upper = np.array(upper_hsv)

    # ===== Core algorithms =====
    def _process_line_follow(self, img, result: VisionResult):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, bw = cv2.threshold(gray, self.line_threshold, 255, cv2.THRESH_BINARY)
        bw = cv2.erode(bw, None, iterations=2)
        bw = cv2.dilate(bw, None, iterations=2)

        # 新增：将单通道二值图转为三通道，存入结果供渲染使用，对齐原版画面效果
        result.binary_frame = cv2.merge((bw, bw, bw))

        row_1 = bw[self.line_pos_1]
        row_2 = bw[self.line_pos_2]

        try:
            idx_1 = np.where(row_1 == self.line_color_value)[0]
            idx_2 = np.where(row_2 == self.line_color_value)[0]

            if len(idx_1) >= 2 and len(idx_2) >= 2:
                l1, r1 = idx_1[1], idx_1[-2]
                l2, r2 = idx_2[1], idx_2[-2]
                c1 = (l1 + r1) // 2
                c2 = (l2 + r2) // 2

                result.line_found = True
                result.line_center = (c1 + c2) // 2
                result.line_left_1, result.line_right_1 = l1, r1
                result.line_left_2, result.line_right_2 = l2, r2
        except Exception:
            result.line_found = False

    def _process_color_track(self, img, result: VisionResult):
        if self.app_mode:
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        else:
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        mask = cv2.inRange(hsv, self.color_lower, self.color_upper)
        mask = cv2.GaussianBlur(mask, (5, 5), 0)
        mask = cv2.erode(mask, None, iterations=2)
        mask = cv2.dilate(mask, None, iterations=2)

        cnts = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = imutils.grab_contours(cnts)

        if len(cnts) > 0:
            c = max(cnts, key=cv2.contourArea)
            (cx, cy), radius = cv2.minEnclosingCircle(c)
            result.color_detected = True
            result.color_center_x = int(cx)
            result.color_center_y = int(cy)
            result.color_radius = float(radius)

    def _process_motion(self, img, result: VisionResult):
        timestamp = datetime.datetime.now()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if self._avg_background is None:
            self._avg_background = gray.astype("float")
            return

        cv2.accumulateWeighted(gray, self._avg_background, 0.5)
        frame_delta = cv2.absdiff(gray, cv2.convertScaleAbs(self._avg_background))
        thresh = cv2.threshold(frame_delta, 5, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)

        cnts = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = imutils.grab_contours(cnts)

        for c in cnts:
            if cv2.contourArea(c) < 5000:
                continue
            x, y, w, h = cv2.boundingRect(c)
            result.motion_detected = True
            result.motion_rect = (x, y, w, h)
            self._last_motion_time = timestamp
            self._motion_counter += 1

        if (timestamp - self._last_motion_time).seconds >= 0.5:
            result.motion_detected = False

    # ===== Public interface =====
    def process(self, frame):
        """
        Process a single frame.
        :return: VisionResult object
        """
        result = VisionResult()
        result.mode = self.mode

        if self.mode == "findline":
            self._process_line_follow(frame, result)
        elif self.mode == "findColor":
            self._process_color_track(frame, result)
        elif self.mode == "watchDog":
            self._process_motion(frame, result)

        return result

    def draw_overlay(self, frame, result: VisionResult):
        """Draw detection annotations on the image (in-place)"""
        if self.mode == "none":
            return frame

        if self.mode == "findline" and self.enable_render:
            # 核心修复：原地覆盖像素，替换为二值化画面，外部调用方可直接生效
            if result.binary_frame is not None:
                frame[:] = result.binary_frame

            if result.line_found:
                # 两条扫描线
                cv2.line(frame, (0, self.line_pos_1), (self.width, self.line_pos_1), (255, 128, 64), 1)
                cv2.line(frame, (0, self.line_pos_2), (self.width, self.line_pos_2), (64, 128, 255), 1)
                # 左右边缘标记（第一行）
                cv2.line(frame, (result.line_left_1, self.line_pos_1 - 30),
                         (result.line_left_1, self.line_pos_1 + 30), (255, 128, 64), 2)
                cv2.line(frame, (result.line_right_1, self.line_pos_1 - 30),
                         (result.line_right_1, self.line_pos_1 + 30), (64, 128, 255), 2)
                # 左右边缘标记（第二行）
                cv2.line(frame, (result.line_left_2, self.line_pos_2 - 30),
                         (result.line_left_2, self.line_pos_2 + 30), (64, 128, 255), 2)
                cv2.line(frame, (result.line_right_2, self.line_pos_2 - 30),
                         (result.line_right_2, self.line_pos_2 + 30), (64, 128, 255), 2)
                # 中心十字
                mid_y = (self.line_pos_1 + self.line_pos_2) // 2
                cv2.line(frame, (result.line_center - 20, mid_y),
                         (result.line_center + 20, mid_y), (0, 0, 0), 1)
                cv2.line(frame, (result.line_center, mid_y - 20),
                         (result.line_center, mid_y + 20), (0, 0, 0), 1)

            # 文字提示
            label = "Following White Line" if self.line_color_value == 255 else "Following Black Line"
            cv2.putText(frame, label, (30, 50), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (128, 255, 128), 1, cv2.LINE_AA)

        elif self.mode == "findColor":
            label = "Target Detected" if result.color_detected else "Target Detecting"
            cv2.putText(frame, label, (40, 60), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (255, 255, 255), 1, cv2.LINE_AA)
            if result.color_detected and result.color_radius > 10:
                x, y, r = result.color_center_x, result.color_center_y, result.color_radius
                cv2.rectangle(frame, (int(x - r), int(y - r)),
                              (int(x + r), int(y + r)), (255, 255, 255), 1)

        elif self.mode == "watchDog" and result.motion_detected:
            x, y, w, h = result.motion_rect
            cv2.rectangle(frame, (x, y), (x + w, y + h), (128, 255, 0), 1)

        return frame
