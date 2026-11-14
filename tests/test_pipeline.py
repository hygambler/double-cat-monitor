"""Synthetic frames test integration, not real YOLO accuracy."""
import json
import sqlite3
import cv2
import numpy as np
from catwatch.core import load_config
from catwatch.__main__ import run
from catwatch.vision import descriptor


def test_video_pipeline_media_time_and_two_cats(tmp_path, monkeypatch):
    c = load_config()
    c.update(zone=[0,0,1,1], db=str(tmp_path / "events.db"),
             status=str(tmp_path / "status.json"), profiles=str(tmp_path / "profiles.json"))
    mask = np.ones((64,64), np.uint8)
    profiles = {name: [descriptor(np.full((64,64,3), color, np.uint8), mask).tolist()]*3
                for name, color in zip(c["cats"], (20,230))}
    (tmp_path / "profiles.json").write_text(json.dumps(profiles))
    path = tmp_path / "test.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64,64))
    assert writer.isOpened()
    for i in range(180):
        value = 20 if i < 60 else (100 if i < 110 else 230)
        writer.write(np.full((64,64,3), value, np.uint8))
    writer.release()
    class FakeDetector:
        def __init__(self, config):
            pass
        def detect(self, frame):
            if 80 < frame.mean() < 120:
                return []
            return [(np.array([0,0,64,64]), mask)]
    monkeypatch.setattr("catwatch.vision.Detector", FakeDetector)
    run(c, video=str(path))
    with sqlite3.connect(c["db"]) as conn:
        events = conn.execute("SELECT cat, observed_seconds, end_reason FROM events ORDER BY id").fetchall()
        snapshots = conn.execute("SELECT snapshot_jpeg, snapshot_ts-start_ts FROM events ORDER BY id").fetchall()
    assert [e[0] for e in events] == c["cats"]
    assert 5 <= events[0][1] <= 6
    assert events[0][2] == "left_zone"
    assert events[1][2] == "stopped"
    for jpeg, offset in snapshots:
        assert offset == 5
        assert cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR).shape == (64, 64, 3)
    assert json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))["state"] == "stopped"
