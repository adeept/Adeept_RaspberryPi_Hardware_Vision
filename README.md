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
cd ~            # the directory holding Hardware/
python3 -m Hardware.Motor
python3 -m Hardware.Servo
python3 -m Hardware.BatteryMonitor
python3 -m Hardware.LightTracking
```


Importing a component does not require its hardware library until you actually
touch the class, so a missing dependency is reported exactly where it is used:

```python
from Hardware import Servo, DCMotor, PCA9685
```

