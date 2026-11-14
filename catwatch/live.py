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


def encode_event_snapshot(frame, detections, zone):
    import cv2
    import numpy as np

    height, width = frame.shape[:2]
    annotated = frame.copy()
    overlay = frame.copy()
    for _, mask, _, _ in detections:
        overlay[mask != 0] = (60, 200, 80)
    cv2.addWeighted(overlay, .34, annotated, .66, 0, dst=annotated)
    for index, (box, mask, track_id, _) in enumerate(detections, start=1):
        contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(annotated, contours, -1, (60, 225, 80), 2)
        x1, y1, x2, y2 = box
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 200, 255), 2)
        label = f"ByteTrack #{track_id}" if track_id is not None else f"YOLO #{index}"
        cv2.putText(annotated, label, (x1, max(24, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX,
                    .7, (0, 200, 255), 2, cv2.LINE_AA)
    x1, y1, x2, y2 = [int(v * size) for v, size in zip(zone, (width, height, width, height))]
    cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 180, 0), 2)
    ok, encoded = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return encoded.tobytes() if ok else None
