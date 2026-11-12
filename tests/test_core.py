import json
import sqlite3
import pytest
from catwatch.core import VisitEngine, Store, load_config, ROOT


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


def test_stop_finalizes_once_and_rejects_clock_reversal():
    e = VisitEngine("cam")
    occupied(e, "冲冲")
    assert e.finish()["end_reason"] == "stopped"
    assert e.finish() is None
    with pytest.raises(ValueError):
        e.tick(1, [])


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
