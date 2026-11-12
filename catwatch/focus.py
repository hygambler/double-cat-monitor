"""Send focus settings to the process that owns the USB camera."""

import json
from pathlib import Path
import time
from uuid import uuid4

from .core import atomic_json
from .process_lock import collector_lock

FOCUS_MIN = 0
FOCUS_MAX = 250
# DirectShow returns the camera-control flags, including 2 for manual.
FOCUS_MODES = {0: "manual", 1: "auto", 2: "manual", 3: "auto"}


def focus_file(status, name):
    return Path(status).with_suffix(f".focus-{name}.json")


def read_focus(status, name):
    try:
        value = json.loads(focus_file(status, name).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def request_focus(status, mode, value):
    if mode not in ("auto", "manual"):
        raise ValueError("Invalid focus mode")
    if mode == "manual" and (type(value) is not int or not FOCUS_MIN <= value <= FOCUS_MAX):
        raise ValueError("Invalid manual focus value")
    path = focus_file(status, "request")
    with collector_lock(path.with_suffix(".lock")):
        atomic_json(path, {"id": uuid4().hex, "mode": mode,
                           "value": value if mode == "manual" else None})


class FocusControl:
    def __init__(self, status):
        self.status = status
        self.last_request = None
        self.next_poll = 0

    def report(self, **fields):
        try:
            atomic_json(focus_file(self.status, "result"), fields)
        except OSError:
            # The camera must keep recording if a dashboard read races with replacement.
            return False
        return True

    def poll(self, cap):
        import cv2

        now = time.monotonic()
        if now < self.next_poll:
            return
        self.next_poll = now + .5
        request = read_focus(self.status, "request")
        if request == self.last_request:
            return
        old_mode = FOCUS_MODES.get(cap.get(cv2.CAP_PROP_AUTOFOCUS))
        old_value = cap.get(cv2.CAP_PROP_FOCUS)
        outcome = "ready"
        mode = request.get("mode")
        if mode == "auto":
            if not cap.set(cv2.CAP_PROP_AUTOFOCUS, 1) or FOCUS_MODES.get(cap.get(cv2.CAP_PROP_AUTOFOCUS)) != "auto":
                outcome = "rejected"
        elif mode == "manual":
            value = request.get("value")
            if type(value) is not int or not FOCUS_MIN <= value <= FOCUS_MAX:
                outcome = "rejected"
            elif not (cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
                      and cap.set(cv2.CAP_PROP_FOCUS, value)
                      and FOCUS_MODES.get(cap.get(cv2.CAP_PROP_AUTOFOCUS)) == "manual"):
                if old_value >= 0:
                    cap.set(cv2.CAP_PROP_FOCUS, old_value)
                if old_mode:
                    cap.set(cv2.CAP_PROP_AUTOFOCUS, int(old_mode == "auto"))
                outcome = "rejected"
        actual = cap.get(cv2.CAP_PROP_FOCUS)
        auto = cap.get(cv2.CAP_PROP_AUTOFOCUS)
        if self.report(state=outcome, id=request.get("id"),
                       mode=FOCUS_MODES.get(auto),
                       value=actual if FOCUS_MIN <= actual <= FOCUS_MAX else None):
            self.last_request = request
