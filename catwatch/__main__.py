import argparse
from collections import deque
import json
import logging
import os
from pathlib import Path
import signal
import time

from .core import FEEDING_EVENT, ROOT, Store, VisitEngine, atomic_json, load_config


def source_for(c):
    return os.environ.get("CATWATCH_SOURCE", c["source"])


def setup(c):
    import cv2
    from .capture import open_capture
    cap = open_capture(source_for(c), c)
    try:
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError("无法读取摄像头；检查 USB、相机权限和 source 编号。")
        x, y, w, h = cv2.selectROI("Frame the white bowl - ENTER save / ESC cancel", frame, False)
        if w == 0 or h == 0:
            print("已取消，没有修改配置。")
            return None
        height, width = frame.shape[:2]
        return frame, [x / width, y / height, (x + w) / width, (y + h) / height]
    finally:
        cap.release()
        cv2.destroyAllWindows()


def expand_images(patterns):
    # CMD and PowerShell do not expand globs for Python scripts as Unix shells do.
    import glob
    paths = []
    for pattern in patterns:
        matches = sorted(glob.glob(pattern))
        if not matches:
            raise FileNotFoundError(f"没有匹配到照片：{pattern}")
        paths.extend(matches)
    return list(dict.fromkeys(paths))


def doctor(c, check_model=False):
    import platform
    import torch
    import cv2
    print(f"System: {platform.system()} | Python: {platform.python_version()}")
    print(f"PyTorch: {torch.__version__} | CUDA build: {torch.version.cuda}")
    available = torch.cuda.is_available()
    print(f"CUDA available: {available}")
    if available:
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        x = torch.ones((32, 32), device="cuda:0")
        result = x @ x
        torch.cuda.synchronize()
        assert result[0, 0].item() == 32
        print("GPU computation: PASS")
    print(f"Configured device: {c['device']} | OpenCV: {cv2.__version__}")
    if str(c["device"]) in ("0", "cuda", "cuda:0") and not available:
        raise RuntimeError("配置要求 GPU，但 CUDA 不可用；请检查 NVIDIA 驱动及 PyTorch GPU 安装。")
    if check_model:
        import numpy as np
        from .vision import Detector
        d = Detector(c)
        d.detect(np.zeros((480, 640, 3), np.uint8))
        print(f"YOLO model: {Path(c['model']).name} | task: {d.model.task} | inference: PASS")


def enroll(c, cat, images):
    import cv2
    from .vision import Detector, descriptor
    if cat not in c["cats"]:
        raise ValueError("cat must match a configured name")
    detector = Detector(c)
    features = []
    for path in images:
        frame = cv2.imread(path)
        if frame is None:
            raise ValueError(f"Cannot read image: {path}")
        cats = detector.detect(frame)
        if len(cats) != 1:
            raise ValueError(f"Exactly one visible cat required: {path}; detected {len(cats)}")
        feature = descriptor(frame, cats[0][1])
        if feature is None:
            raise ValueError(f"Cat too small: {path}")
        features.append(feature.tolist())
    if len(features) < 3:
        raise ValueError("至少提供 3 张同一只猫的现场照片，建议 5–10 张不同姿势。")
    p = Path(c["profiles"])
    profiles = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    profiles[cat] = features
    atomic_json(p, profiles)
    print(f"已保存 {cat} 的 {len(features)} 个样本。需完成两只猫的校准才会输出名字。")


def demo(c):
    # Generated occupancy observations, explicitly separate from real evidence.
    db = ROOT / "data/demo.sqlite3"
    store = Store(db)
    if store.conn.execute("SELECT 1 FROM events WHERE kind=? LIMIT 1", (FEEDING_EVENT,)).fetchone():
        store.close()
        print(f"演示库已存在：{db}（未追加）")
        return
    start = time.time() - 3600
    for i, cat in enumerate([*c["cats"], "unknown"]):
        engine = VisitEngine("DEMO_generated", minimum=3, max_step=1)
        t = start + i * 600
        for j in range(13):
            engine.tick(t + j * .5, [cat])
        for event in engine.tick(t + 10, []):
            store.save(event)
    store.close()
    print(f"生成 3 条模拟事件：{db}；不是摄像头识别结果。")


def run(c, preview=False, video=None, seconds=None, web_preview=False, stop_requested=None):
    import cv2
    import numpy as np
    from .capture import LiveCapture, open_capture
    from .alignment import Alignment
    from .live import encode_event_snapshot, preview_path, publish_preview
    from .vision import Detector, descriptor, identify, identify_night, in_zone, load_profiles, scene_luminance
    if c["zone"] is None:
        raise ValueError("请先执行 python -m catwatch setup 框选吃猫粮区。")
    from .process_lock import collector_lock
    lock_path = Path(c["db"]).with_suffix(".lock")
    with collector_lock(lock_path):
        live_path = preview_path(c["status"]) if web_preview and not video else None
        alignment = None if video else Alignment(c)
        zone = c["zone"]
        alignment_stop = False
        detector = Detector(c)
        profiles = load_profiles(c["profiles"], c["cats"])
        night_path = c.get("night_profiles")
        night_profiles = load_profiles(night_path, c["cats"]) if night_path else {}
        if not profiles:
            print("尚未完成双猫校准，先以 unknown 记录。")
        engine = VisitEngine(c["camera_id"], c["min_observed_seconds"], c["exit_grace_seconds"],
                             c["identity_vote_ratio"], max_step=1.5 / c["inference_fps"],
                             night_grace=c.get("night_exit_grace_seconds") if night_path else None,
                             night_vote_ratio=c.get("night_identity_vote_ratio") if night_path else None)
        tracker = None
        if c.get("bytetrack", False):
            from .tracking import CatTracker
            tracker = CatTracker(c["confidence"], c["inference_fps"], engine.night_grace)
        store = Store(c["db"])
        zone_track = None
        last_tracker_frame = None
        stopping = False
        def stop(*_):
            nonlocal stopping
            stopping = True
        old_handlers = {s: signal.signal(s, stop) for s in (signal.SIGINT, signal.SIGTERM)}
        reader = None
        cap = None
        started = time.monotonic()
        epoch = time.time()
        durations = deque(maxlen=120)
        last_seq, frames, saved = -1, 0, 0
        last_heartbeat = 0.
        last_identity = []
        scene_luma = None
        min_scene_luma = c.get("identity_min_scene_luma", 0)
        night = False
        light_ok = True
        error = None
        error_detail = None
        try:
            if video:
                cap = open_capture(video, c)
                fps = cap.get(cv2.CAP_PROP_FPS)
                if not cap.isOpened() or not np.isfinite(fps) or fps <= 0:
                    raise RuntimeError("无法读取视频或有效帧率。")
                frame_index, next_sample = 0, 0.
            else:
                reader = LiveCapture(source_for(c), c).start()
            while not stopping and (seconds is None or time.monotonic() - started < seconds):
                if stop_requested and stop_requested():
                    break
                frame = None
                now = time.monotonic()
                ts = epoch + now - started
                if video:
                    ok, candidate = cap.read()
                    if not ok:
                        break
                    offset = frame_index / fps
                    frame_index += 1
                    if offset < next_sample:
                        continue
                    next_sample = offset + 1 / c["inference_fps"]
                    ts, frame = epoch + offset, candidate
                else:
                    packet = reader.latest()
                    if packet and packet[0] != last_seq and now - packet[1] < 2:
                        last_seq, _, _, frame = packet
                if frame is None:
                    scene_luma = None
                    night = False
                    light_ok = True
                    for event in engine.tick(ts, [], frame_available=False):
                        store.save(event)
                        saved += 1
                    last_identity = []
                    if tracker and last_tracker_frame is not None and ts - last_tracker_frame >= engine.grace:
                        tracker.reset()
                        zone_track = last_tracker_frame = None
                else:
                    if alignment:
                        checked = alignment.check(frame, now)
                        if not checked or zone != alignment.zone:
                            # A visit spanning a geometry change has unreliable timing.
                            event = engine.finish("alignment_changed")
                            if event:
                                store.save(event)
                                saved += 1
                            if tracker and last_tracker_frame is not None:
                                tracker.reset()
                                zone_track = last_tracker_frame = None
                        if alignment.status["state"] in ("severe", "unverified"):
                            alignment_stop = True
                            print("机位偏移过大或无法确认粮碗位置。已停止监控，请重新框选后手动启动。",
                                  flush=True)
                            break
                        zone = alignment.zone if checked else None
                    t0 = time.monotonic()
                    if tracker:
                        if last_tracker_frame is not None and ts - last_tracker_frame > engine.night_grace:
                            tracker.reset()
                            zone_track = None
                        detections = detector.detect_tracked(frame, tracker)
                        last_tracker_frame = ts
                    else:
                        detections = [(box, mask, None, True) for box, mask in detector.detect(frame)]
                    scene_luma = scene_luminance(frame) if min_scene_luma or night_path else None
                    night = bool(night_path and scene_luma <= c["night_max_scene_luma"])
                    light_limit = c["night_min_scene_luma"] if night else min_scene_luma
                    light_ok = scene_luma is None or scene_luma >= light_limit
                    identities = []
                    visual = frame.copy() if preview or live_path else None
                    display_results = []
                    observations = []
                    for box, mask, track_id, reliable in detections:
                        feature = descriptor(frame, mask) if light_ok and reliable else None
                        if night:
                            name = identify_night(feature, night_profiles)
                        else:
                            name, _ = identify(feature, profiles, c["identity_max_distance"], c["identity_margin"])
                        can_count = reliable or (track_id is not None and track_id == zone_track
                                                 and engine.active is not None)
                        inside = (can_count and zone is not None
                                  and in_zone(mask, zone, c["zone_min_mask_fraction"]))
                        observations.append((track_id, name, inside))
                    resolved = (tracker.resolve(ts, [(track_id, name) for track_id, name, _ in observations])
                                if tracker else [(name, False) for _, name, _ in observations])
                    if zone_track is not None and any(
                        track_id == zone_track and not inside and detection[3]
                        for detection, (track_id, _, inside) in zip(detections, observations)
                    ):
                        event = engine.finish("left_zone")
                        if event:
                            store.save(event)
                            saved += 1
                        tracker.identities.pop(zone_track, None)
                        zone_track = None
                    zone_tracks = []
                    inherited = False
                    for index, (detection, observation, identity) in enumerate(
                            zip(detections, observations, resolved), start=1):
                        box, _, _, _ = detection
                        track_id, raw_name, inside = observation
                        name, carried = identity
                        if inside:
                            identities.append(name)
                            zone_tracks.append(track_id)
                            inherited = carried
                        if visual is not None:
                            x1, y1, x2, y2 = box
                            cv2.rectangle(visual, (x1, y1), (x2, y2), (60, 200, 80), 2)
                            label = f"#{index}" if live_path else (
                                f"cat_{c['cats'].index(name)+1}" if name in c["cats"] else "unknown")
                            cv2.putText(visual, label, (x1, max(20, y1)), 0, .7, (60, 200, 80), 2)
                            display_results.append({"index": index, "cat": name, "in_zone": inside,
                                                    "track_id": track_id, "raw_cat": raw_name,
                                                    "inherited": carried})
                    if (zone_track is not None and len(zone_tracks) == 1
                            and zone_tracks[0] is not None and zone_tracks[0] != zone_track):
                        event = engine.finish("track_changed")
                        if event:
                            store.save(event)
                            saved += 1
                    for event in engine.tick(ts, identities, night=night, inherited=inherited):
                        store.save(event)
                        saved += 1
                    if (len(identities) == 1 and (tracker is None or zone_tracks[0] is not None)
                            and engine.snapshot_due(identities[0])):
                        try:
                            jpeg = encode_event_snapshot(frame, detections, zone)
                            if jpeg is not None:
                                engine.attach_snapshot(jpeg, ts if video else packet[2])
                        except cv2.error:
                            logging.exception("Could not encode feeding event snapshot")
                    if len(zone_tracks) == 1 and zone_tracks[0] is not None:
                        zone_track = zone_tracks[0]
                    elif len(zone_tracks) > 1:
                        zone_track = None
                    elif engine.active is None:
                        zone_track = None
                    last_identity = identities
                    frames += 1
                    elapsed = time.monotonic() - t0
                    durations.append(elapsed)
                    if visual is not None and zone is not None:
                        h, w = visual.shape[:2]
                        x1, y1, x2, y2 = [int(v * s) for v, s in zip(zone, (w, h, w, h))]
                        cv2.rectangle(visual, (x1, y1), (x2, y2), (255, 180, 0), 2)
                    if live_path:
                        publish_preview(live_path, visual, packet[2], display_results, elapsed)
                    if preview:
                        cv2.imshow("Catwatch - Q quit", visual)
                        if cv2.waitKey(1) & 255 == ord("q"):
                            break
                if now - last_heartbeat > 2:
                    atomic_json(c["status"], dict(updated=time.time(), state="running" if frame is not None else "no_signal",
                                frames=frames, saved_events=saved, zone_identities=last_identity,
                                active=engine.active is not None, replay=bool(video),
                                active_identity=engine.identity()[0],
                                tracking="ByteTrack" if tracker else None,
                                alignment=alignment.status if alignment else None,
                                identity_scene_luma=scene_luma,
                                identity_low_light=not light_ok,
                                identity_mode="night" if night else "day",
                                inference_ms_p50=round(float(np.median(durations))*1000, 1) if durations else None,
                                inference_ms_p95=round(float(np.percentile(durations,95))*1000, 1) if durations else None),
                                tolerate_busy_replace=True)
                    last_heartbeat = now
                if not video:
                    time.sleep(max(0, 1 / c["inference_fps"] - (time.monotonic() - now)))
        except BaseException as exc:
            error = type(exc).__name__
            error_detail = str(exc)
            raise
        finally:
            event = engine.finish("error" if error else "stopped")
            if event:
                store.save(event)
                saved += 1
            if reader:
                reader.close()
            if cap:
                cap.release()
            if live_path:
                for path in (live_path, live_path.with_suffix(".tmp")):
                    try:
                        path.unlink(missing_ok=True)
                    except PermissionError:
                        pass
            store.close()
            cv2.destroyAllWindows()
            final_state = "alignment_stop" if alignment_stop else "error" if error else "stopped"
            try:
                atomic_json(c["status"], dict(updated=time.time(), state=final_state,
                            error=error, error_detail=error_detail, frames=frames, saved_events=saved,
                            replay=bool(video), alignment=alignment.status if alignment else None,
                            inference_ms_p50=round(float(np.median(durations))*1000, 1) if durations else None),
                            tolerate_busy_replace=True)
            except OSError:
                if error is None:
                    raise
                logging.exception("Could not write final collector status")
            finally:
                for s, handler in old_handlers.items():
                    signal.signal(s, handler)
        print(f"处理 {frames} 帧，保存 {saved} 条候选事件。")


def web(config_path, config):
    import subprocess
    import sys

    env = dict(os.environ, CATWATCH_CONFIG=str(Path(config_path).resolve()))
    with subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(ROOT / "dashboard.py"),
         "--server.address=127.0.0.1", "--server.port=8501"],
        cwd=ROOT, env=env,
    ) as dashboard:
        try:
            run(config, web_preview=True, stop_requested=lambda: dashboard.poll() is not None)
            if dashboard.poll():
                raise RuntimeError("看板启动失败，请查看终端中的 Streamlit 输出。")
        finally:
            if dashboard.poll() is None:
                dashboard.terminate()


def main():
    p = argparse.ArgumentParser(description="家庭双猫吃猫粮监测（本地）")
    p.add_argument("--config", default=str(ROOT / "config.json"))
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="摄像头预览并框选吃猫粮区")
    snap = sub.add_parser("snapshot", help="保存一帧现场校准照片")
    snap.add_argument("output")
    e = sub.add_parser("enroll", help="从单猫现场照片建立毛色样本")
    e.add_argument("cat")
    e.add_argument("images", nargs="+")
    e.add_argument("--night", action="store_true", help="登记到夜间样本库")
    r = sub.add_parser("run", help="运行采集和推理")
    r.add_argument("--preview", action="store_true")
    r.add_argument("--video", help="离线回放；请配独立配置/数据库")
    r.add_argument("--seconds", type=float, help="限时性能试跑")
    d = sub.add_parser("doctor", help="检查环境、GPU 与可选的模型推理")
    d.add_argument("--model", action="store_true")
    sub.add_parser("demo", help="生成独立模拟数据库，不使用摄像头")
    sub.add_parser("web", help="同时运行本地看板和摄像头采集")
    args = p.parse_args()
    c = load_config(args.config)
    if args.command == "setup":
        from .alignment import calibrate
        from .process_lock import collector_lock
        with collector_lock(Path(c["db"]).with_suffix(".lock")):
            selection = setup(c)
            if selection:
                frame, zone = selection
                path = Path(args.config)
                raw = json.loads(path.read_text(encoding="utf-8"))
                calibrate(c, frame, zone, zone)
                raw["zone"] = zone
                atomic_json(path, raw)
                print(f"已保存吃猫粮区和机位基准：{zone}")
    elif args.command == "snapshot":
        import cv2
        from .capture import open_capture
        cap = open_capture(source_for(c), c)
        try:
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("无法读到摄像头画面。")
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                raise FileExistsError("照片已存在，请换一个文件名。")
            if not cv2.imwrite(str(path), frame):
                raise RuntimeError("照片保存失败。")
            print(f"照片已保存：{path}")
        finally:
            cap.release()
    elif args.command == "enroll":
        if args.night:
            if "night_profiles" not in c:
                p.error("当前配置没有夜间样本库")
            c = dict(c, profiles=c["night_profiles"])
        enroll(c, args.cat, expand_images(args.images))
    elif args.command == "doctor":
        doctor(c, args.model)
    elif args.command == "demo":
        demo(c)
    elif args.command == "web":
        web(args.config, c)
    else:
        run(c, args.preview, args.video, args.seconds)


if __name__ == "__main__":
    main()
