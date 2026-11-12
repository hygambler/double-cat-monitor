import json
import time

import numpy as np
from streamlit.testing.v1 import AppTest
from catwatch.core import ROOT, Store, VisitEngine
from catwatch.live import preview_path, publish_preview
from catwatch.vision import in_zone


def test_dashboard_stats_and_review(tmp_path, monkeypatch):
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    config["db"] = str(tmp_path / "events.db")
    config["status"] = str(tmp_path / "status.json")
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    store = Store(config["db"])
    monkeypatch.setenv("CATWATCH_CONFIG", str(path))
    app = AppTest.from_file(str(ROOT / "dashboard.py"), default_timeout=30).run()
    assert not app.exception
    assert app.dataframe[0].value["候选进食次数"].tolist() == [0, 0, 0]
    e = VisitEngine("test")
    start = time.time() - 10
    for i in range(13):
        e.tick(start + i*.5, ["冲冲"])
    store.save(e.finish())
    store.save(dict(camera_id="old", start_ts=start, end_ts=start + 6, observed_seconds=6,
                    cat="茉莉", identity_ratio=1, ambiguous=0, end_reason="stopped",
                    kind="water_zone_visit"))
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    mask = np.ones(frame.shape[:2], dtype=np.uint8)
    inside = in_zone(mask, [0, 0, 1, 1], config["zone_min_mask_fraction"])
    publish_preview(preview_path(config["status"]), frame, time.time(),
                    [{"index": 1, "cat": "冲冲", "in_zone": inside}], .032)
    app.run()
    assert not app.exception
    assert {metric.label: metric.value for metric in app.metric}["候选进食"] == "1"
    assert {metric.label: metric.value for metric in app.metric}["当前画面中的猫"] == "1"
    assert any("冲冲" in item.value and "在吃猫粮区" in item.value for item in app.markdown)
    app.selectbox(key="review_result").select("confirmed_eating")
    app.selectbox(key="review_cat").select("白猫")
    next(button for button in app.button if button.label == "保存复核").click().run()
    assert not app.exception
    assert store.conn.execute("SELECT review,reviewed_cat FROM events ORDER BY id").fetchall() == [
        ("confirmed_eating", "白猫"), ("pending", None),
    ]
    summary = app.dataframe[0].value.set_index("猫咪")
    assert summary.loc["白猫", ["确认进食次数", "确认进食秒数"]].tolist() == [1, 6]
    store.close()
