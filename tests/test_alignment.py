import json
import time

import cv2
import numpy as np
import pytest

from catwatch.alignment import Alignment, alignment_path, calibrate, set_alignment_enabled, severe
from catwatch.__main__ import run
from catwatch.core import load_config


@pytest.fixture
def calibrated_camera(tmp_path):
    rng = np.random.default_rng(14)
    frame = np.full((450, 800, 3), 85, dtype=np.uint8)
    for x, y, value in zip(rng.integers(8, 792, 300), rng.integers(8, 442, 300),
                           rng.integers(110, 245, 300)):
        cv2.circle(frame, (int(x), int(y)), 4, (int(value),) * 3, -1)
    cv2.ellipse(frame, (360, 200), (36, 26), 0, 0, 360, (235, 235, 235), -1)
    cv2.ellipse(frame, (360, 195), (30, 18), 0, 0, 360, (47, 55, 69), -1)
    zone = [312 / 800, 160 / 450, 408 / 800, 242 / 450]
    bowl = [323 / 800, 173 / 450, 397 / 800, 227 / 450]
    config = {"status": str(tmp_path / "status.json"), "zone": zone}
    calibrate(config, frame, zone, bowl)
    return config, frame, bowl


def shifted(frame, x):
    return cv2.warpAffine(frame, np.float32([[1, 0, x], [0, 1, 0]]), (800, 450))


def test_hourly_relocation_and_persistent_shutdown(calibrated_camera):
    config, frame, bowl = calibrated_camera
    alignment = Alignment(config)
    assert alignment.check(frame, 1)
    assert alignment.check(shifted(frame, 80), 3600)
    assert alignment.zone == config["zone"]
    assert alignment.check(shifted(frame, 80), 3601)
    assert alignment.status["state"] == "adjusted"
    assert alignment.zone[0] == pytest.approx(config["zone"][0] + .1, abs=.005)

    assert not alignment.check(shifted(frame, 172), 7201)
    assert alignment.status["state"] == "severe"
    assert json.loads(alignment_path(config).read_text(encoding="utf-8"))["blocked"] == "severe"
    with pytest.raises(RuntimeError, match="重新校准"):
        Alignment(config)
    calibrate(config, frame, config["zone"], bowl)
    assert Alignment(config).check(frame, 1)


def test_obscured_bowl_pauses_and_recovers(calibrated_camera):
    config, frame, _ = calibrated_camera
    alignment = Alignment(config)
    hidden = frame.copy()
    hidden[145:260, 280:435] = 0
    assert not alignment.check(hidden, 1)
    assert alignment.status["state"] == "retrying"
    assert not alignment.check(frame, 2)
    assert alignment.check(frame, 11)
    assert alignment.status["state"] == "stable"


def test_switch_keeps_adjusted_zone_and_checks_immediately_when_reenabled(calibrated_camera):
    config, frame, _ = calibrated_camera
    alignment = Alignment(config)
    assert alignment.check(shifted(frame, 80), 1)
    adjusted_zone = alignment.zone
    set_alignment_enabled(config, False)
    alignment = Alignment(config)
    assert alignment.check(shifted(frame, 172), 2)
    assert alignment.status["state"] == "disabled"
    assert alignment.zone == adjusted_zone
    set_alignment_enabled(config, True)
    assert not alignment.check(shifted(frame, 172), 3)
    assert alignment.status["state"] == "severe"


def test_severe_motion_stops_collector_before_inference(calibrated_camera, tmp_path, monkeypatch):
    config, frame, _ = calibrated_camera
    config = load_config() | config | {
        "db": str(tmp_path / "events.db"), "profiles": str(tmp_path / "profiles.json"),
    }
    moved = shifted(frame, 172)

    class Capture:
        def __init__(self, source, config):
            self.closed = False

        def start(self):
            return self

        def latest(self):
            return 1, time.monotonic(), time.time(), moved

        def close(self):
            self.closed = True

    class Detector:
        def __init__(self, config):
            pass

        def detect(self, frame):
            pytest.fail("A frame with severe displacement must not be counted")

    capture = Capture(None, config)
    monkeypatch.setattr("catwatch.capture.LiveCapture", lambda source, config: capture)
    monkeypatch.setattr("catwatch.vision.Detector", Detector)
    run(config, seconds=1, web_preview=True)
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["state"] == "alignment_stop"
    assert status["saved_events"] == 0
    assert capture.closed


@pytest.mark.parametrize("axis", [0, 1, 2])
def test_severe_boundary_is_inclusive(axis):
    motion = [0., 0., 0.]
    motion[axis] = .199
    assert not severe(motion)
    motion[axis] = -.20
    assert severe(motion)
