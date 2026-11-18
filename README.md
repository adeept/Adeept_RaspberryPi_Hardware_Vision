# Adeept_RaspberryPi_Hardware_Vision

This repository maintains hardware components, vision modules, and vision-voice sample programs for Adeept Raspberry Pi robots.

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

## Using the Motion module

`Hardware.Servo` answers "put the horn at angle X now". `Motion` adds the two
things a walking robot needs on top of that: a smooth, velocity-limited
trajectory, and one clock shared by all sixteen joints.

`Motion` imports `Hardware` as a sibling package, so the two folders travel
together:

```
|-- Hardware/
|-- Motion/
```

### Files

| file | role |
| --- | --- |
| `profile.py` | S-curve / linear travel, pure maths, no clock |
| `joint.py` | one servo: logical angle, limits, deadband, trajectory |
| `servo_bank.py` | up to 16 joints sharing one clock and one I2C bus |
| `calibration.py` | per-channel `neutral` / `direction` / `min` / `max`, JSON on disk |
| `calibrate.py` | keyboard tool that measures and writes that table |

### Running the demos

```bash
python3 -m Motion             # sweep + pose + retarget, uses the saved table
python3 -m Motion.calibrate   # keyboard calibration, writes the JSON table
```

`python3 -m Motion` prints `calibration: ...` when the table is missing or stale
and then runs on the defaults, so the demo doubles as a boot check.

### Non-blocking usage

The library never keeps time. Your loop owns the clock and passes `dt` in, so
one scheduler drives every joint and their phases cannot drift apart:

```python
import time
from Hardware import PCA9685
from Motion import ServoBank, ServoCalibration

cal  = ServoCalibration.load()                     # ~/.adeept/servo_calibration.json
pca  = PCA9685(bus_num=1, address=0x5F, freq=50)   # share the bus with Motor
bank = ServoBank(pca, count=cal.count, actuation_range=cal.actuation_range,
                 config=cal.to_config())           # pca=None creates its own chip

bank.move_all({0: 60, 1: 120}, duration=0.8)       # both arrive on the same tick

while bank.update(0.02):                           # 50 Hz
    time.sleep(0.02)
```

Leave `config` out and the bank runs on defaults: `neutral` 90, `direction` +1,
every channel `0..actuation_range`. That is fine for a bench test and wrong on
a real robot, whose mid positions are never all 90.

`move_all` returns the common duration it used, so a caller can log it or pick
its own tick count.

### API

`ServoBank`:

| call | meaning |
| --- | --- |
| `move_to(ch, angle, duration=None)` | one joint, S-curve |
| `move_all({ch: angle}, duration=None)` | several joints, one shared arrival tick |
| `pose({ch: offset}, duration=None)` | relative to `neutral`, flipped by `direction` |
| `update(dt)` | advance everything, `True` while still moving |
| `jump_all({ch: angle})` | no ramp, for start-up poses and recovery |
| `stop_all()` | drop the trajectories and hold the pose |
| `angles()` | current logical angle of every joint |
| `busy` | `True` while any joint is still moving |
| `close()` / `with ServoBank(...) as bank` | release every channel, then the chip it owns |

`Joint` (reach it as `bank[ch]`):

| call | meaning |
| --- | --- |
| `move_to(angle, duration=None)` | smooth move, `False` when already there |
| `required_duration(angle, ...)` | what the limits would cost, without moving |
| `jump(angle)` | immediate write, bypassing every ramp |
| `angle` | current absolute angle, degrees |
| `to_absolute(offset)` | `neutral + direction * offset` |
| `writes` | how many I2C writes this joint made, for chasing a dead channel |

`ServoCalibration`:

| call | meaning |
| --- | --- |
| `load(path=None, count=16, strict=False)` | read the table, record `.error` |
| `save(path=None)` | atomic write, returns the path |
| `to_config()` | dict ready for `ServoBank(config=...)` |
| `validate()` | list of human readable problems |
| `summary()` | one line per channel, for logs |
| `channel_of(name)` | channel index from its name |
| `set(ch, neutral=…, min=…, max=…, direction=…, name=…)` | edit one entry |

There is no `pause()` / `resume()` and no thread: simply stop calling
`update()` to pause, and call `jump_all()` on the safety path so a stop never
waits behind a ramp.

### Per-channel tuning

```python
cfg = cal.to_config()                              # calibrated neutral / direction / limits
cfg[0].update({"max_vel": 120, "max_acc": 600})   # gait limits on top
bank = ServoBank(pca, count=cal.count, actuation_range=cal.actuation_range,
                 config=cfg)                      # pca=None creates its own chip
```

Any key left out keeps its default, and a channel missing from `config` uses all
defaults, so the two sources compose: the table owns the geometry, the program
owns the speed.

`max_vel` (deg/s) and `max_acc` (deg/s^2) are the per-joint defaults whenever a
call does not pass its own. Duration is raised automatically so the limits
always hold, for an S-curve of travel `d` and duration `T`:

```text
v_peak = 1.5 * d / T      a_peak = 6.0 * d / T^2
```

Calling `move_all` again mid-move retargets from the current position, so a
changed command never produces a jump.

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

### Booting from the table


```python
from Motion import ServoBank, ServoCalibration

cal  = ServoCalibration.load()                       # never raises on a bad file
bank = ServoBank(pca, count=cal.count, actuation_range=cal.actuation_range,
                 config=cal.to_config())

# called once at start-up, so a stale table is visible in the log
if cal.error:                                        # missing / unreadable / count mismatch
    print("calibration:", cal.error)                 # defaults are in use
for problem in cal.validate():
    print("calibration:", problem)
```

Under a systemd service, `~` is whatever `$HOME` the unit was given — unset, it
becomes `/root` and the table is silently not found. Either set
`Environment=HOME=/home/adeept` in the unit, or pass the path explicitly:

```python
cal = ServoCalibration.load("/home/adeept/.adeept/servo_calibration.json")
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
