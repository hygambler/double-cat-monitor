"""YOLO foreground masks and calibrated coat color and pattern matching."""
import json
import os
from pathlib import Path
import cv2
import numpy as np

COLOR_BINS = 512
PATTERN_SIZE = 26


def coat_pattern(frame, mask):
    x, y, width, height = cv2.boundingRect(mask)
    foreground = mask[y:y + height, x:x + width] != 0
    gray = cv2.cvtColor(frame[y:y + height, x:x + width], cv2.COLOR_BGR2GRAY)
    # Use the brighter fur in this frame as the reference for darker patches.
    relative = np.clip(gray / max(1, np.percentile(gray[foreground], 85)), 0, 1).astype(np.float32)
    levels = np.quantile(relative[foreground], [.1, .2, .3, .4, .5, .6, .7, .8])
    coverage = cv2.resize(foreground.astype(np.float32), (3, 3), interpolation=cv2.INTER_AREA)
    patches = cv2.resize(relative * foreground, (3, 3), interpolation=cv2.INTER_AREA)
    patches /= np.maximum(coverage, .0001)
    return np.concatenate((levels, patches.ravel(), coverage.ravel()))


def pattern_distance(first, second):
    levels = np.mean(np.abs(first[:8] - second[:8]))
    weights = np.minimum(first[17:], second[17:])
    if weights.sum() == 0:
        return float(levels)
    patches = np.average(np.abs(first[8:17] - second[8:17]), weights=weights)
    return float(.65 * levels + .35 * patches)


def descriptor(frame, mask):
    # LAB keeps achromatic dark/white coat information as well as color.
    if np.count_nonzero(mask) < 200:
        return None
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    hist = cv2.calcHist([lab], [0, 1, 2], mask.astype(np.uint8), [8, 8, 8], [0, 256] * 3)
    color = hist.ravel() / max(float(hist.sum()), 1.)
    return np.concatenate((color, coat_pattern(frame, mask.astype(np.uint8)))).astype(np.float32)


def identify(feature, profiles, max_distance=.55, margin=.12):
    if feature is None or len(profiles) != 2:
        return "unknown", None
    scores = sorted((min(float(cv2.compareHist(feature[:COLOR_BINS], np.array(sample[:COLOR_BINS], np.float32),
                                             cv2.HISTCMP_BHATTACHARYYA)) for sample in samples), cat)
                    for cat, samples in profiles.items() if samples)
    if len(scores) != 2:
        return "unknown", None
    (d, cat), (second, _) = scores
    if d > max_distance or second - d < margin:
        return "unknown", d
    if len(feature) == COLOR_BINS + PATTERN_SIZE:
        pattern_scores = sorted(
            (min(pattern_distance(feature[COLOR_BINS:], np.asarray(sample[COLOR_BINS:]))
                 for sample in samples if len(sample) == len(feature)), name)
            for name, samples in profiles.items() if any(len(sample) == len(feature) for sample in samples)
        )
        if len(pattern_scores) == 2:
            (closest, pattern_cat), (runner_up, _) = pattern_scores
            if closest <= .20 and runner_up - closest >= .025 and pattern_cat != cat:
                return "unknown", d
    return cat, d


def scene_luminance(frame):
    thumbnail = cv2.resize(frame, (64, 36), interpolation=cv2.INTER_AREA)
    return float(np.median(cv2.cvtColor(thumbnail, cv2.COLOR_BGR2GRAY)))


def identify_night(feature, profiles):
    if feature is None or len(feature) != COLOR_BINS + PATTERN_SIZE or len(profiles) != 2:
        return "unknown"
    scores = {}
    for name, samples in profiles.items():
        full_samples = [np.asarray(sample, dtype=np.float32)
                        for sample in samples if len(sample) == COLOR_BINS + PATTERN_SIZE]
        if not full_samples:
            return "unknown"
        color = min(cv2.compareHist(feature[:COLOR_BINS], sample[:COLOR_BINS],
                                    cv2.HISTCMP_BHATTACHARYYA) for sample in full_samples)
        pattern = min(pattern_distance(feature[COLOR_BINS:], sample[COLOR_BINS:])
                      for sample in full_samples)
        scores[name] = (color, pattern)
    first, second = sorted(scores, key=lambda name: sum(scores[name]))
    color, pattern = scores[first]
    other_color, other_pattern = scores[second]
    if (color < other_color and pattern < other_pattern
            and (color + pattern) / 2 <= .11
            and (other_color + other_pattern - color - pattern) / 2 >= .035):
        return first
    return "unknown"


class Detector:
    def __init__(self, c):
        os.environ.setdefault("YOLO_CONFIG_DIR", str(Path(c["model"]).parent / "ultralytics"))
        os.environ.setdefault("MPLCONFIGDIR", str(Path(c["model"]).parent / "matplotlib"))
        from ultralytics import YOLO
        self.c = c
        self.model = YOLO(c["model"])
        if self.model.task != "segment":
            raise ValueError("Use a segmentation model, e.g. yolo26n-seg.pt")
        self.cat_class = next(int(k) for k, name in self.model.names.items() if name == "cat")

    def detect(self, frame):
        return [detection[:2] for detection in self._detect(frame)]

    def detect_tracked(self, frame, tracker):
        return self._detect(frame, tracker)

    def _detect(self, frame, tracker=None):
        confidence = self.c["confidence"] if tracker is None else min(.10, self.c["confidence"])
        r = self.model.predict(frame, classes=[self.cat_class], conf=confidence,
                               imgsz=self.c["imgsz"], device=self.c["device"],
                               retina_masks=True, verbose=False)[0]
        tracks = tracker.update(r.boxes.cpu().numpy()) if tracker is not None else {}
        if r.masks is None:
            return []
        h, w = frame.shape[:2]
        result = []
        for index, (box, mask, score) in enumerate(zip(r.boxes.xyxy.cpu().numpy(),
                r.masks.data.cpu().numpy(), r.boxes.conf.cpu().numpy())):
            track_id = tracks.get(index)
            reliable = bool(score >= self.c["confidence"])
            if not reliable and track_id is None:
                continue
            mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST) > .5
            result.append((box.astype(int), mask.astype(np.uint8), track_id, reliable))
        return result


def load_profiles(path, cats):
    p = Path(path)
    if not p.exists():
        return {}
    profiles = json.loads(p.read_text(encoding="utf-8"))
    if set(profiles) != set(cats):
        return {}
    for samples in profiles.values():
        for sample in samples:
            a = np.asarray(sample)
            if (a.shape not in ((COLOR_BINS,), (COLOR_BINS + PATTERN_SIZE,))
                    or not np.isfinite(a).all() or (a < 0).any()
                    or not np.isclose(a[:COLOR_BINS].sum(), 1, atol=.01)
                    or (a[COLOR_BINS:] > 1.0001).any()):
                raise ValueError("Invalid coat profile; re-enroll")
    return profiles


def in_zone(mask, zone, threshold):
    h, w = mask.shape
    x1, y1, x2, y2 = [int(v * size) for v, size in zip(zone, (w, h, w, h))]
    fraction = np.count_nonzero(mask[y1:y2, x1:x2]) / max(1, np.count_nonzero(mask))
    return bool(fraction >= threshold)
