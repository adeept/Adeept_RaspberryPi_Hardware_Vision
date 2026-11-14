#!/usr/bin/env python
# File name   : app.py
# Website     : www.Adeept.com
# Author      : Adeept
"""
Flask web server with decoupled vision + control architecture.
Web streaming and robot control run in separate threads.
"""
from importlib import import_module
import os
from flask import Flask, render_template, Response, send_from_directory
from flask_cors import *
import threading

# Import adapter instead of original camera_opencv
from camera_web_adapter import Camera
from vision_system import VisionSystem
from robot_control_worker import RobotControlWorker

app = Flask(__name__)
CORS(app, supports_credentials=True)

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


# ====== Initialize shared vision system & control worker ======
vision_sys = VisionSystem(camera_type="auto", width=640, height=480)
vision_sys.start()

# Bind vision system to web camera adapter
Camera.bind_vision_system(vision_sys)

# Start independent robot control thread
control_worker = RobotControlWorker(vision_sys)
control_worker.start()

camera = Camera()


def gen(camera):
    while True:
        frame = camera.get_frame()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


@app.route('/video_feed')
def video_feed():
    return Response(gen(camera),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


# ====== All original static file routes remain unchanged ======
@app.route('/api/img/<path:filename>')
def sendimg(filename):
    return send_from_directory(dir_path+'/dist/img', filename)

@app.route('/js/<path:filename>')
def sendjs(filename):
    return send_from_directory(dir_path+'/dist/js', filename)

@app.route('/css/<path:filename>')
def sendcss(filename):
    return send_from_directory(dir_path+'/dist/css', filename)

@app.route('/api/img/icon/<path:filename>')
def sendicon(filename):
    return send_from_directory(dir_path+'/dist/img/icon', filename)

@app.route('/fonts/<path:filename>')
def sendfonts(filename):
    return send_from_directory(dir_path+'/dist/fonts', filename)

@app.route('/<path:filename>')
def sendgen(filename):
    return send_from_directory(dir_path+'/dist', filename)

@app.route('/')
def index():
    return send_from_directory(dir_path+'/dist', 'index.html')


class webapp:
    def __init__(self):
        self.camera = camera

    def modeselect(self, modeInput):
        Camera.modeSelect = modeInput
        vision_sys.set_mode(modeInput)

    def modeselectApp(self, modeInput):
        vision_sys.set_app_mode(True)
        Camera.modeSelect = modeInput
        vision_sys.set_mode(modeInput)

    def colorFindSet(self, H, S, V):
        camera.colorFindSet(H, S, V)

    def colorFindSetApp(self, H, S, V):
        camera.colorFindSetApp(H, S, V)

    def thread(self):
        app.run(host='0.0.0.0', port=5000, threaded=True)

    def startthread(self):
        fps_threading = threading.Thread(target=self.thread)
        fps_threading.daemon = False
        fps_threading.start()


if __name__ == "__main__":
    WEB = webapp()
    try:
        WEB.startthread()
    except KeyboardInterrupt:
        print("\nShutting down...")
        control_worker.stop()
        vision_sys.stop()
    except Exception as e:
        print(f"Exit: {e}")
        control_worker.stop()
        vision_sys.stop()
