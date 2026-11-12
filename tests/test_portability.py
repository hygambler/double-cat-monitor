import json
import subprocess
import sys
import pytest
from catwatch.__main__ import atomic_json, expand_images
from catwatch.process_lock import collector_lock
from catwatch.core import ROOT, load_config


def test_collector_lock_excludes_other_process_and_releases(tmp_path):
    path = tmp_path / "collector.lock"
    code = "from catwatch.process_lock import collector_lock; import sys;\nwith collector_lock(sys.argv[1]): pass"
    with collector_lock(path):
        result = subprocess.run([sys.executable, "-c", code, str(path)], capture_output=True)
        assert result.returncode != 0
        assert b"RuntimeError" in result.stderr
    assert subprocess.run([sys.executable, "-c", code, str(path)], capture_output=True).returncode == 0


def test_utf8_config_and_globs(tmp_path):
    path = tmp_path / "cats.json"
    atomic_json(path, {"cats": ["冲冲", "茉莉"]})
    assert json.loads(path.read_bytes().decode("utf-8"))["cats"] == ["冲冲", "茉莉"]
    for name in ("cat_01.jpg", "cat_02.jpg"):
        (tmp_path / name).touch()
    assert len(expand_images([str(tmp_path / "cat_*.jpg"), str(tmp_path / "cat_01.jpg")])) == 2
    with pytest.raises(FileNotFoundError):
        expand_images([str(tmp_path / "missing_*.jpg")])


def test_windows_config_keeps_yolo26_and_cat_names():
    c = load_config(ROOT / "config.windows.json")
    assert c["device"] == "0"
    assert c["model"].endswith("yolo26n-seg.pt")
    assert c["cats"] == ["冲冲", "白猫"]
