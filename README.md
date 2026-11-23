# Adeept_RaspberryPi_Hardware_Vision

This repository maintains hardware components, vision modules, and voice sample programs for Adeept Raspberry Pi robots.

## Folder Structure
- **Hardware**  
  Hardware-related components and supporting files for Adeept Raspberry Pi robot kits.

- **Motion**  
  Motion layer on top of `Hardware.Servo`: smooth, velocity-limited trajectories for
  up to 16 joints, driven by one clock that the caller owns. Includes a keyboard
  calibration tool and the per-channel table it writes
  (`~/.adeept/servo_calibration.json`), which every boot reuses.

- **Vision**  
  Vision functional modules, including camera drivers and OpenCV-based processing code. MediaPipe-related features will be added in subsequent updates.

- **Voice**  
  Speech Recognition Based on sherpa‑onnx.

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
python3 -m Hardware.SystemInfo
```

Importing a component does not require its hardware library until you actually
touch the class:

```python
from Hardware import Servo, DCMotor, PCA9685
```

### Calibration

`neutral`, `direction` and the mechanical `min` / `max` are properties of the
machine, not of the code. They are measured once with a keyboard tool and then
reused on every boot. Put the robot on blocks and run:

```bash
python3 -m Motion.calibrate
```

Pressing `s` reports what was written for the channel on screen, then the file
it went to:

```
 >> saved ch3: neutral=90.0 min=10.0 max=170.0 dir=+1
 >> -> /home/adeept/.adeept/servo_calibration.json
```


| key | meaning |
| --- | --- |
| `[n]` / `[p]` | next / previous channel |
| `[+/-]` | nudge the current servo by one step |
| `[1..9]` | step size in degrees (`0` = 10°) |
| `[c]` | capture the current angle as `neutral` (offset 0) |
| `[l]` / `[h]` | capture the current angle as the `min` / `max` limit |
| `[d]` | flip the direction of the current channel |
| `[t]` | sweep every channel `min` → `max` → `neutral` |
| `[s]` / `[r]` | save to disk / reload from disk |
| `[q]` | quit (twice when there are unsaved edits) |

Channels are numbered 0..15, the same numbering as the PCA9685.

The table is written to `~/.adeept/servo_calibration.json` (override with
`--path`). Writing goes through a temporary file and a rename, so an interrupted
save cannot leave half a JSON file behind.

```json
{
  "version": 1,
  "count": 16,
  "actuation_range": 180.0,
  "saved": "2026-11-18 10:24:31",
  "servos": {
    "0": {"name": "ch0", "neutral": 88.5, "direction": -1,
          "min": 12.0, "max": 169.0}
  }
}
```


## Using the Vision module

`Vision` owns the camera (USB or CSI), the OpenCV worker thread and, optionally, an
MJPEG web stream. 

### Deployment layout

Copy the whole `Vision` folder to the robot. The web page (`dist`) is optional and
belongs next to `Vision`, not inside it:

```
|-- dist/           
|-- Vision/          
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
