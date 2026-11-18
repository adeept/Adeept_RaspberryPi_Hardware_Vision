# Adeept_RaspberryPi_Hardware_Vision

This repository maintains hardware components, vision modules, and vision-voice sample programs for Adeept Raspberry Pi robots.

## Folder Structure
- **Hardware**  
  Hardware-related components and supporting files for Adeept Raspberry Pi robot kits.

- **Vision**  
  Vision functional modules, including camera drivers and OpenCV-based processing code. MediaPipe-related features will be added in subsequent updates.

- **Vision_Voice_Examples**  
  Ready-to-run sample programs that integrate vision and voice capabilities.

## Quick Usage
You can directly copy the folder you need to your Raspberry Pi, then use the corresponding components or run the demo programs.

### Running the Hardware demos

The files in `Hardware` import each other as a package, so the demos must be started
with `python3 -m` from the directory that **contains** the `Hardware` folder:

```bash
cd ~            
python3 -m Hardware.Motor
python3 -m Hardware.Servo
python3 -m Hardware.BatteryMonitor
python3 -m Hardware.LightTracking
```


Importing a component does not require its hardware library until you actually
touch the class:

```python
from Hardware import Servo, DCMotor, PCA9685
```

## Using the Vision module

`Vision` owns the camera (USB or CSI), the OpenCV worker thread and, optionally, an
MJPEG web stream. 

### Requirements

```bash
sudo apt install python3-opencv python3-picamera2     
pip3 install flask flask-cors                         
```

### Deployment layout

Copy the whole `Vision` folder to the robot. The web page (`dist`) is optional and
belongs next to `Vision`, not inside it:

```
|-- dist/           
|-- Vision/          
```

`/video_feed` works without `dist`; `/` returns 404 when `dist` is missing.

### Importing

Run from the folder that contains `Vision/`:

```python
from Vision import Vision, VisionResult
```


### Quick start: line following

```python
from Vision import Vision

vision = Vision.get()                   # process-wide singleton
vision.start(camera_type="auto")        # auto / usb / csi
vision.set_mode("findline")

seq = 0
try:
    while True:                # your own loop condition
        seq, res = vision.wait_result(seq, timeout=0.02)
        if res is None:                 # no new frame yet
            continue
        print("line found, error=%.1f" % res.line_error)
finally:
    vision.stop()                       # releases the camera
```


### Modes and result fields

| mode | field | meaning |
|---|---|---|
| `findline` | `line_found` | a line was seen on both scan rows |
| | `line_center` | smoothed centre x, the value the controller uses |
| | `line_center_raw` | centre x of this frame |
| | `line_error` | `(center-(w-1)/2)/((w-1)/2)`, -1 left .. +1 right |
| | `line_span_1`, `line_span_2` | `(left, right)` of the line on each scan row |
| | `line_wide` | one span covering 90% of the width or more |
| `findColor` | `color_detected` | target seen in this frame |
| | `color_center` | `(x, y)` centroid of the largest blob |
| | `color_radius`, `color_area` | enclosing radius and contour area |
| | `color_error_x` | normalised horizontal error, -1 left .. +1 right |
| | `color_recent` | target seen within `color_timeout` seconds |
| `watchDog` | `motion_detected` | motion in this frame |
| | `motion_recent` | motion within `motion_timeout` seconds |
| | `motion_rect` | `(x, y, w, h)` of the largest block |
| | `motion_area` | area of the largest block |
| | `motion_boxes` | all blocks found in this frame |

`print(result)` prints only the fields of the active mode:

```
{'mode': 'findline', 'line_found': True, 'line_center': 239, 'line_error': -0.252, ...}
```

### Tuning

```python
vision.set_mode("findline")             # none / findline / findColor / watchDog
vision.set_line_threshold(80)           # binary threshold applied to the grey image
vision.set_line_positions(440, 380)     # scan rows in pixels, defaults for 640x480
vision.set_line_color(0)                # 0 black line, 255 white line

vision.set_mode("findColor")
vision.set_color_range([24, 100, 100], [44, 255, 255])   # raw OpenCV HSV limits
vision.set_color_hsv(30, 255, 255)                        # centre value + tolerance
vision.set_color_rgb(255, 200, 0)                         # pick a colour, not a scale
vision.set_color_at(320, 240)                             # sample the frame centre
```

### Latest frame

```python
raw    = vision.raw_frame()      # clean BGR frame, for MediaPipe and friends
drawn  = vision.frame()          # frame with the detection drawn on it
seq, jb = vision.jpeg()          # (frame number, JPEG bytes), encoded once per frame
```

### Web streaming

Start the module and the stream in one call:

```python
vision.start(camera_type="auto", web=True, host="0.0.0.0", port=5000)
vision.set_mode("findColor")
```

Then open `http://<pi-ip>:5000/video_feed` (MJPEG with the overlay) or
`http://<pi-ip>:5000/` (front end, needs `dist`). Recognition keeps running in its
own thread, so the loop above still reads results while clients watch.
