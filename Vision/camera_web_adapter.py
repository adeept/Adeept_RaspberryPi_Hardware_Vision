#!/usr/bin/env python3
# File name   : camera_web_adapter.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
Web streaming adapter for BaseCamera framework.
Only reads frames from VisionSystem, no CV processing, no hardware control.
100% compatible with original Camera class API.
"""
import time
import cv2
import numpy as np
from base_camera import BaseCamera


class Camera(BaseCamera):
    video_source = 0
    modeSelect = "none"
    _vision_system = None

    @staticmethod
    def bind_vision_system(vs):
        """Inject the shared VisionSystem instance"""
        Camera._vision_system = vs

    def __init__(self):
        if Camera._vision_system is None:
            raise RuntimeError("VisionSystem not bound. Call Camera.bind_vision_system() first.")
        super().__init__()

    def colorFindSet(self, H, S, V):
        if self._vision_system is None:
            return
        H1, H2 = min(180, H+15), max(0, H-15)
        S1, S2 = min(255, S+150), max(0, S-150)
        V1, V2 = min(255, V+150), max(0, V-150)
        self._vision_system.set_color_range([H2, S2, V2], [H1, S1, V1])

    def colorFindSetApp(self, H, S, V):
        if self._vision_system is None:
            return
        H1, H2 = min(255, H+100), max(0, H-100)
        S1, S2 = min(255, S+100), max(0, S-100)
        V1, V2 = min(255, V+100), max(0, V-100)
        self._vision_system.set_app_mode(True)
        self._vision_system.set_color_range([H2, S2, V2], [H1, S1, V1])

    def modeSet(self, invar):
        Camera.modeSelect = invar
        if self._vision_system:
            self._vision_system.set_mode(invar)

    def CVRunSet(self, invar):
        # Reserved for enabling/disabling motion control
        pass

    def linePosSet_1(self, invar):
        if self._vision_system:
            self._vision_system.set_line_positions(invar, 380)

    def linePosSet_2(self, invar):
        if self._vision_system:
            self._vision_system.set_line_positions(440, invar)

    def colorSet(self, invar):
        if self._vision_system:
            self._vision_system.set_line_color(invar)

    def randerSet(self, invar):
        pass

    def Threshold(self, value):
        if self._vision_system:
            self._vision_system.set_line_threshold(value)

    def ThresholdOK(self):
        return 80

    @staticmethod
    def set_video_source(source):
        Camera.video_source = source

    @staticmethod
    def frames():
        """Frame generator for BaseCamera streaming"""
        vs = Camera._vision_system
        if vs is None:
            raise RuntimeError("VisionSystem not bound.")

        print("Web streaming started.")
        while True:
            frame = vs.get_latest_frame()
            if frame is None:
                time.sleep(0.01)
                continue

            ret, jpeg = cv2.imencode(
                '.jpg', frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), 80]
            )
            if ret:
                yield jpeg.tobytes()
