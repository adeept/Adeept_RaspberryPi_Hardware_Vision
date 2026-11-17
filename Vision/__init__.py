# Vision/__init__.py
"""Adeept vision package.

The modules in this folder import each other as top-level modules (``vision_system``,
``camera_capture``, ``app``), so this package puts its own directory on ``sys.path``
and then re-exports the public names. Both import styles therefore work, and they
yield the SAME module objects, so there is only one ``Vision`` class and one
singleton in the process:

    from Vision import Vision, VisionResult       # package style, from the parent folder
    from vision_api import Vision                 # flat style, Vision/ on sys.path

Run the service as a script. Do not use ``python3 -m Vision.vision_api``: that loads
a second copy of the module and a second singleton.

    python3 Vision/vision_api.py auto             # from the folder holding Vision/
    cd ~/Vision && python3 vision_api.py csi
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from vision_api import Vision                   # noqa: E402
from vision_processor import VisionResult       # noqa: E402

__all__ = ["Vision", "VisionResult"]
