"""Bounded latest-frame capture: no inference backlog on live sources."""
import sys
import threading
import time
import cv2
from .focus import FocusControl


def open_capture(source, c):
    if isinstance(source, str) and source.isdecimal():
        source = int(source)
    if isinstance(source, str) and source.lower().startswith("rtsp://"):
        cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG,
                               [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
                                cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000])
    elif isinstance(source, int) and sys.platform == "win32":
        # DirectShow exposes the C920's autofocus and manual focus controls.
        cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(source)
    else:
        cap = cv2.VideoCapture(source)
    if isinstance(source, int):
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, c["width"])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, c["height"])
        cap.set(cv2.CAP_PROP_FPS, c["capture_fps"])
    return cap


class LiveCapture:
    def __init__(self, source, config):
        self.source, self.config = source, config
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.packet = None
        self.sequence = 0
        self.usb = isinstance(source, int) or (isinstance(source, str) and source.isdecimal())
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def _run(self):
        while not self.stop.is_set():
            cap = open_capture(self.source, self.config)
            focus = FocusControl(self.config["status"]) if self.usb else None
            try:
                while not self.stop.is_set() and cap.isOpened():
                    if focus:
                        focus.poll(cap)
                    ok, frame = cap.read()
                    if not ok:
                        break
                    with self.lock:
                        self.sequence += 1
                        self.packet = (self.sequence, time.monotonic(), time.time(), frame)
            finally:
                cap.release()
                if focus:
                    focus.report(state="offline")
            self.stop.wait(2)

    def latest(self):
        with self.lock:
            return self.packet

    def close(self):
        self.stop.set()
        self.thread.join(timeout=6)
