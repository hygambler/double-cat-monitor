"""Exchange the latest annotated camera frame with the local dashboard."""

import base64
import json
from pathlib import Path
import time

from .core import atomic_json


def preview_path(status):
    return Path(status).with_suffix(".live.json")


def read_preview(status):
    try:
        preview = json.loads(preview_path(status).read_text(encoding="utf-8"))
        if time.time() - preview["captured_at"] > 4:
            return None
        preview["jpeg"] = base64.b64decode(preview["jpeg"], validate=True)
        return preview
    except (OSError, ValueError, KeyError, TypeError):
        return None


def publish_preview(path, frame, captured_at, detections, elapsed):
    import cv2

    height, width = frame.shape[:2]
    if width > 960:
        frame = cv2.resize(frame, (960, round(960 * height / width)), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if ok:
        try:
            atomic_json(path, {
                "captured_at": captured_at,
                "jpeg": base64.b64encode(encoded).decode("ascii"),
                "detections": detections,
                "inference_ms": round(elapsed * 1000, 1),
            })
        except PermissionError:
            # On Windows a concurrent read can briefly prevent atomic replacement.
            pass
