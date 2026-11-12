"""Compare the camera to its last manual calibration and locate the same bowl."""

import base64
import json
from pathlib import Path
import time

import cv2
import numpy as np

from .core import atomic_json
from .process_lock import collector_lock

CHECK_INTERVAL = 3600
RETRY_INTERVAL = 10
RETRY_LIMIT = 120
SEVERE = 0.20
DEADBAND = 0.02
WIDTH = 800


def alignment_path(config):
    return Path(config["status"]).with_suffix(".alignment.json")


def switch_path(config):
    return Path(config["status"]).with_suffix(".alignment-switch.json")


def alignment_enabled(config, default=True):
    try:
        data = json.loads(switch_path(config).read_text(encoding="utf-8"))
        enabled = data.get("enabled") if isinstance(data, dict) else None
        return enabled if isinstance(enabled, bool) else default
    except (OSError, ValueError):
        return default


def set_alignment_enabled(config, enabled):
    path = switch_path(config)
    with collector_lock(path.with_suffix(".lock")):
        atomic_json(path, {"enabled": enabled})


def gray_frame(frame):
    h, w = frame.shape[:2]
    return cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
                      (WIDTH, round(h * WIDTH / w)), interpolation=cv2.INTER_AREA)


def pixels(zone, width, height):
    return np.asarray(zone) * [width, height, width, height]


def features(image, zone=None):
    mask = None
    if zone is not None:
        h, w = image.shape
        x1, y1, x2, y2 = pixels(zone, w, h).astype(int)
        mask = np.full(image.shape, 255, np.uint8)
        cv2.rectangle(mask, (x1 - 8, y1 - 8), (x2 + 8, y2 + 8), 0, -1)
    points, descriptors = cv2.SIFT_create(nfeatures=900).detectAndCompute(image, mask)
    return np.float32([point.pt for point in points]), descriptors


def calibrate(config, frame, zone, bowl):
    image = gray_frame(frame)
    h, w = image.shape
    x1, y1, x2, y2 = pixels(bowl, w, h).astype(int)
    patch = image[y1:y2, x1:x2]
    if (min(patch.shape) < 20 or patch.std() < 8
            or len(features(image, zone)[0]) < 24):
        raise ValueError("基准画面不够清晰。请在粮碗无遮挡、背景清楚时重新框选。")
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RuntimeError("无法保存机位基准。")
    atomic_json(alignment_path(config), {
        "zone": zone, "bowl": bowl, "reference": base64.b64encode(encoded).decode("ascii"),
    })


def estimate_motion(reference_features, image):
    before, reference_descriptors = reference_features
    after, descriptors = features(image)
    if reference_descriptors is None or descriptors is None or len(descriptors) < 2:
        return None
    pairs = cv2.BFMatcher().knnMatch(reference_descriptors, descriptors, k=2)
    matches = [first for first, second in pairs if first.distance < 0.72 * second.distance]
    if len(matches) < 12:
        return None
    old = before[[match.queryIdx for match in matches]]
    new = after[[match.trainIdx for match in matches]]
    matrix, inliers = cv2.estimateAffinePartial2D(old, new, ransacReprojThreshold=3)
    if matrix is None:
        return None
    supported = old[inliers.ravel().astype(bool)]
    h, w = image.shape
    if (len(supported) < 12 or len(supported) / len(matches) < .45
            or np.any(np.ptp(supported, axis=0) < [w * .20, h * .20])):
        return None
    return matrix


def offsets(matrix, width, height):
    center = np.array([width / 2, height / 2])
    dx, dy = (matrix[:, :2] @ center + matrix[:, 2] - center) / [width, height]
    dz = np.linalg.norm(matrix[:, 0]) - 1
    return [float(dx), float(dy), float(dz)]


def severe(motion):
    # Disregard fit noise below one hundredth of a percentage point.
    return round(max(map(abs, motion)), 4) >= SEVERE


def transform_box(zone, matrix, width, height):
    x1, y1, x2, y2 = pixels(zone, width, height)
    corners = np.array([[x1, y1], [x1, y2], [x2, y1], [x2, y2]])
    moved = corners @ matrix[:, :2].T + matrix[:, 2]
    return np.r_[moved.min(axis=0), moved.max(axis=0)]


def locate_bowl(reference, image, bowl, matrix):
    """Find the calibrated bowl's appearance near its predicted position."""
    h, w = image.shape
    predicted = transform_box(bowl, matrix, w, h)
    x1, y1, x2, y2 = np.rint(predicted).astype(int)
    if not (0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h):
        return None
    template = cv2.warpAffine(reference, matrix, (w, h))[y1:y2, x1:x2]
    if min(template.shape) < 12 or template.std() < 6:
        return None
    left, top = max(0, x1 - round(w * .06)), max(0, y1 - round(h * .06))
    right, bottom = min(w, x2 + round(w * .06)), min(h, y2 + round(h * .06))
    matches = cv2.matchTemplate(image[top:bottom, left:right], template, cv2.TM_CCOEFF_NORMED)
    _, score, _, (x, y) = cv2.minMaxLoc(matches)
    if score < .72:
        return None
    return np.array([left + x - x1, top + y - y1])


class Alignment:
    def __init__(self, config):
        self.config = config
        self.path = alignment_path(config)
        try:
            self.baseline = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RuntimeError("缺少机位基准，请运行 setup 重新框选粮碗。") from exc
        if self.baseline.get("blocked") or self.baseline["zone"] != config["zone"]:
            raise RuntimeError("机位需要重新校准。请运行 setup 框选粮碗，再启动监控。")
        jpeg = base64.b64decode(self.baseline["reference"])
        self.reference = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_GRAYSCALE)
        self.features = features(self.reference, self.baseline["zone"])
        self.zone = self.baseline.get("active_zone", config["zone"])
        self.enabled = alignment_enabled(config)
        self.next_check = 0.0
        self.retry_since = None
        self.status = {"state": "waiting"}

    def block(self, state, motion=None):
        self.baseline["blocked"] = state
        atomic_json(self.path, self.baseline)
        self.status = {"state": state, "offsets": motion, "checked_at": time.time()}
        return False

    def check(self, frame, now):
        self.enabled = alignment_enabled(self.config, default=self.enabled)
        if not self.enabled:
            self.status = {"state": "disabled"}
            self.retry_since = None
            self.next_check = 0.0
            return True
        if now < self.next_check:
            return self.retry_since is None
        image = gray_frame(frame)
        h, w = image.shape
        matrix = estimate_motion(self.features, image) if image.shape == self.reference.shape else None
        motion = offsets(matrix, w, h) if matrix is not None else None
        if motion is not None and severe(motion):
            return self.block("severe", motion)
        correction = None
        if matrix is not None:
            correction = locate_bowl(self.reference, image, self.baseline["bowl"], matrix)
        if correction is not None:
            old_bowl = pixels(self.baseline["bowl"], w, h)
            new_bowl = transform_box(self.baseline["bowl"], matrix, w, h) + np.tile(correction, 2)
            displacement = ((new_bowl[:2] + new_bowl[2:]) - (old_bowl[:2] + old_bowl[2:])) / [2*w, 2*h]
            for axis, value in enumerate(displacement):
                if abs(value) > abs(motion[axis]):
                    motion[axis] = float(value)
            if severe(motion):
                return self.block("severe", motion)
            box = transform_box(self.baseline["zone"], matrix, w, h) + np.tile(correction, 2)
            if max(map(abs, motion)) < DEADBAND:
                box = pixels(self.baseline["zone"], w, h)
            zone = np.clip(box / [w, h, w, h], 0, 1).tolist()
            if zone != self.zone:
                self.baseline["active_zone"] = zone
                atomic_json(self.path, self.baseline)
            self.zone = zone
            self.status = {"state": "stable" if max(map(abs, motion)) < DEADBAND else "adjusted",
                           "offsets": motion, "checked_at": time.time()}
            self.retry_since = None
            self.next_check = now + CHECK_INTERVAL
            return True
        if self.retry_since is None:
            self.retry_since = now
        if now - self.retry_since >= RETRY_LIMIT:
            return self.block("unverified", motion)
        self.status = {"state": "retrying", "offsets": motion, "checked_at": time.time()}
        self.next_check = now + RETRY_INTERVAL
        return False
