import numpy as np
from ultralytics.engine.results import Boxes

from catwatch.core import VisitEngine
from catwatch.tracking import CatTracker


def boxes(*scores):
    rows = [[50 + i * 110, 60, 140 + i * 110, 170, score, 15]
            for i, score in enumerate(scores)]
    return Boxes(np.asarray(rows, dtype=np.float32).reshape(-1, 6), (240, 320))


def test_bytetrack_uses_weak_detections_for_existing_tracks_and_reacquires():
    tracker = CatTracker(.45, 2, 10)
    assert tracker.update(boxes(.2)) == {}
    tracker.update(boxes(.85))
    track_id = tracker.update(boxes(.85))[0]
    assert tracker.update(boxes(.25, .21)) == {0: track_id}
    assert tracker.update(boxes()) == {}
    assert tracker.update(boxes()) == {}
    assert tracker.update(boxes(.8)) == {0: track_id}


def test_track_identity_bridges_unknown_without_adding_votes_or_missing_seconds():
    tracker = CatTracker(.45, 2, 10)
    engine = VisitEngine("cam", night_grace=10, night_vote_ratio=.6)
    for i, raw in enumerate(["白猫"] * 3 + ["unknown"] * 3):
        (name, inherited), = tracker.resolve(i / 2, [(1, raw)])
        engine.tick(i / 2, [name], night=True, inherited=inherited)
    engine.tick(3, [], night=True)
    for ts in (4., 4.5, 5.):
        (name, inherited), = tracker.resolve(ts, [(1, "unknown")])
        assert (name, inherited) == ("白猫", True)
        assert engine.tick(ts, [name], night=True, inherited=inherited) == []
    assert engine.active["votes"] == {"白猫": 3}
    event, = engine.tick(15.5, [], night=True)
    assert event["cat"] == "白猫"
    assert event["observed_seconds"] == 3.5
    assert tracker.resolve(7, [(1, "unknown")]) == [("unknown", False)]


def test_track_identity_clears_on_overlap_and_does_not_transfer():
    tracker = CatTracker(.45, 2, 10)
    for ts in (0., .5, 1.):
        tracker.resolve(ts, [(1, "白猫")])
    assert tracker.resolve(1.5, [(2, "unknown")]) == [("unknown", False)]
    assert tracker.resolve(2, [(1, "unknown"), (2, "冲冲")]) == [
        ("unknown", False), ("冲冲", False),
    ]
    assert tracker.resolve(2.5, [(1, "unknown")]) == [("unknown", False)]
