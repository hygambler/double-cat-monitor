import json
import sqlite3
import pytest
from catwatch.core import VisitEngine, Store, atomic_json, load_config, ROOT


def test_busy_windows_heartbeat_can_be_skipped_and_then_recovers(tmp_path, monkeypatch, caplog):
    status = tmp_path / "status.json"
    atomic_json(status, {"frames": 1})
    original_replace = type(status).replace
    attempts = []

    def busy_replace(source, target):
        attempts.append(target)
        error = PermissionError("destination open")
        error.winerror = 5
        raise error

    with monkeypatch.context() as patch:
        patch.setattr(type(status), "replace", busy_replace)
        patch.setattr("catwatch.core.time.sleep", lambda _: None)
        atomic_json(status, {"frames": 2}, tolerate_busy_replace=True)
        assert len(attempts) == 4
        with pytest.raises(PermissionError):
            atomic_json(status, {"frames": 2})
    assert type(status).replace is original_replace
    assert "Status update skipped" in caplog.text
    assert json.loads(status.read_text()) == {"frames": 1}
    atomic_json(status, {"frames": 3}, tolerate_busy_replace=True)
    assert json.loads(status.read_text()) == {"frames": 3}


def occupied(engine, name, start=0, seconds=6):
    for i in range(seconds * 2 + 1):
        engine.tick(start + i / 2, [name])


def test_confirmed_duration_and_end_excludes_grace():
    e = VisitEngine("cam")
    occupied(e, "冲冲")
    assert e.tick(8, []) == []
    event, = e.tick(10, [])
    assert event["cat"] == "冲冲"
    assert event["end_ts"] == 6
    assert event["observed_seconds"] == 6
    assert e.tick(11, []) == []


def test_short_passby_discarded():
    e = VisitEngine("cam")
    e.tick(0, ["茉莉"])
    e.tick(.5, ["茉莉"])
    assert e.tick(5, []) == []


def test_dropout_is_not_accumulated():
    e = VisitEngine("cam", minimum=1)
    e.tick(0, ["茉莉"])
    e.tick(.5, ["茉莉"])
    e.tick(1, [])
    e.tick(2, ["茉莉"])
    e.tick(2.5, ["茉莉"])
    event, = e.tick(6, [])
    assert event["observed_seconds"] == 1


def test_long_gap_splits_even_without_absent_tick():
    e = VisitEngine("cam")
    occupied(e, "冲冲")
    event, = e.tick(20, ["茉莉"])
    assert event["cat"] == "冲冲"
    assert e.active["start"] == 20
    assert e.active["observed"] == 0


def test_two_cats_and_handoffs_are_unknown():
    e = VisitEngine("cam")
    occupied(e, "冲冲")
    e.tick(6.5, ["冲冲", "茉莉"])
    assert e.finish()["cat"] == "unknown"
    e = VisitEngine("cam")
    occupied(e, "冲冲")
    e.tick(6.5, ["茉莉"])
    assert e.finish()["cat"] == "unknown"


def test_unknown_counts_against_identity_votes():
    e = VisitEngine("cam")
    occupied(e, "unknown")
    e.tick(6.5, ["冲冲"])
    assert e.finish()["cat"] == "unknown"


def test_night_bridges_brief_detection_gap_without_counting_missing_time():
    engine = VisitEngine("cam", night_grace=10, night_vote_ratio=.6)
    for i, cat in enumerate(["白猫", "白猫", "unknown", "白猫", "unknown"]):
        engine.tick(i / 2, [cat], night=True)
    for i in range(5, 14):
        assert engine.tick(i / 2, [], night=True) == []
    for i, cat in enumerate(["白猫", "unknown", "白猫", "白猫", "unknown"]):
        assert engine.tick(7 + i / 2, [cat], night=True) == []

    assert engine.identity() == ("白猫", .6)
    event, = engine.tick(19.5, [], night=True)
    assert event["cat"] == "白猫"
    assert event["observed_seconds"] == 4
    assert event["end_ts"] == 9


def test_night_does_not_bridge_long_gaps_or_keep_a_conflicting_name():
    engine = VisitEngine("cam", night_grace=10, night_vote_ratio=.6)
    for i in range(8):
        engine.tick(i / 2, ["白猫"], night=True)
    engine.tick(4, ["冲冲"], night=True)
    event, = engine.tick(48, ["白猫"], night=True)
    assert event["cat"] == "unknown"
    assert event["ambiguous"] == 1
    assert engine.active["start"] == 48


def test_lost_camera_signal_still_ends_a_night_visit():
    engine = VisitEngine("cam", night_grace=10)
    for i in range(8):
        engine.tick(i / 2, ["白猫"], night=True)
    assert engine.tick(4, [], frame_available=False) == []
    event, = engine.tick(7, ["白猫"], night=True)
    assert event["end_reason"] == "no_signal"
    assert event["end_ts"] == 3.5
    assert engine.active["start"] == 7


def test_stop_finalizes_once_and_rejects_clock_reversal():
    e = VisitEngine("cam")
    occupied(e, "冲冲")
    assert e.finish()["end_reason"] == "stopped"
    assert e.finish() is None
    with pytest.raises(ValueError):
        e.tick(1, [])


def test_snapshot_requires_five_observed_seconds_and_is_saved_once(tmp_path):
    engine = VisitEngine("cam")
    occupied(engine, "白猫", seconds=2)
    engine.tick(2.5, [])
    occupied(engine, "白猫", start=4, seconds=3)
    assert engine.snapshot_due("白猫")
    assert not engine.snapshot_due("unknown")
    engine.attach_snapshot(b"jpeg", 7)
    assert not engine.snapshot_due("白猫")
    store = Store(tmp_path / "events.db")
    store.save(engine.finish())
    assert store.conn.execute(
        "SELECT observed_seconds, snapshot_jpeg, snapshot_ts FROM events"
    ).fetchone() == (5., b"jpeg", 7.)
    store.close()


def test_store_reopen_and_read_concurrently(tmp_path):
    db = tmp_path / "events.sqlite3"
    store = Store(db)
    e = VisitEngine("cam")
    occupied(e, "茉莉")
    store.save(e.finish())
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as reader:
        assert reader.execute("SELECT cat, review FROM events").fetchone() == ("茉莉", "pending")
    store.close()
    store = Store(db)
    assert store.conn.execute("SELECT count(*) FROM events").fetchone()[0] == 1
    store.close()


def test_config_rejects_missing_or_invalid_roi(tmp_path):
    c = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    c["zone"] = [0, 0, 2, 1]
    path = tmp_path / "config.json"
    path.write_text(json.dumps(c))
    with pytest.raises(ValueError):
        load_config(path)
