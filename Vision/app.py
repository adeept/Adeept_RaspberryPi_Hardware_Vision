#!/usr/bin/env python
# File name   : app.py
# Website     : www.Adeept.com
# Author      : Adeept
"""Flask view layer for the video stream (presentation only, no vision_api import).

Scope: HTTP routes, MJPEG streaming and static files under dist/. 
"""
import os
import threading
import time

from flask import Flask, Response, send_from_directory
from flask_cors import *

app = Flask(__name__)
CORS(app, supports_credentials=True)

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

_stream = None          # callable() -> (seq, jpeg_bytes)
_ready = None           # callable() -> bool
_bind_lock = threading.Lock()

def bind_stream(stream_fn, ready_fn=None):
    """Inject the frame source (called by vision_api on startup).

    :param stream_fn: returns (seq, jpeg_bytes); None bytes means no frame yet
    :param ready_fn: returns whether vision is running; False ends the stream
    """
    global _stream, _ready
    with _bind_lock:
        _stream = stream_fn
        _ready = ready_fn

def _is_ready():
    return True if _ready is None else bool(_ready())

def gen():
    last_seq = -1
    while True:
        if not _is_ready():
            return                      # vision stopped: end the stream, do not hang
        if _stream is None:
            time.sleep(0.05)
            continue
        seq, jpeg = _stream()
        if jpeg is None:
            time.sleep(0.02)
            continue
        if seq == last_seq:             # same frame: skip, a slow client drops frames
            time.sleep(0.005)
            continue
        last_seq = seq
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')

# ====== Routes ======
@app.route('/video_feed')
def video_feed():
    if _stream is None or not _is_ready():
        return Response(b"vision system is not running\n", status=503)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/img/<path:filename>')
def sendimg(filename):
    return send_from_directory(dir_path + '/dist/img', filename)

@app.route('/js/<path:filename>')
def sendjs(filename):
    return send_from_directory(dir_path + '/dist/js', filename)

@app.route('/css/<path:filename>')
def sendcss(filename):
    return send_from_directory(dir_path + '/dist/css', filename)

@app.route('/api/img/icon/<path:filename>')
def sendicon(filename):
    return send_from_directory(dir_path + '/dist/img/icon', filename)

@app.route('/fonts/<path:filename>')
def sendfonts(filename):
    return send_from_directory(dir_path + '/dist/fonts', filename)

@app.route('/<path:filename>')
def sendgen(filename):
    return send_from_directory(dir_path + '/dist', filename)

@app.route('/')
def index():
    return send_from_directory(dir_path + '/dist', 'index.html')

if __name__ == "__main__":
    print("app.py is the Flask view layer, start with: sudo python3 vision_api.py [auto|usb|csi]")
