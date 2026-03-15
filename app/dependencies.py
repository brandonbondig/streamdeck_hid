import sys

try:
    from StreamDeck.DeviceManager import DeviceManager, ProbeError
    from StreamDeck.Transport.Transport import TransportError
except ImportError as exc:
    raise SystemExit(
        "The `streamdeck` package is not available in this Python interpreter.\n"
        "Run this script with the same interpreter you used for `pip install streamdeck`."
    ) from exc

try:
    from PIL import ImageDraw, ImageFont
    from StreamDeck.ImageHelpers import PILHelper

    PIL_AVAILABLE = True
except ImportError:
    ImageDraw = None
    ImageFont = None
    PILHelper = None
    PIL_AVAILABLE = False
