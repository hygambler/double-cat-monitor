"""Dependency-free event state machine, configuration and SQLite storage."""
from collections import Counter
from pathlib import Path
import json
import logging
import math
import sqlite3
import time

ROOT = Path(__file__).resolve().parent.parent
FEEDING_EVENT = "feeding_zone_visit"


def atomic_json(path, value, *, tolerate_busy_replace=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    attempts = 4 if tolerate_busy_replace else 1
    for attempt in range(attempts):
        try:
            temp.replace(path)
            return
        except PermissionError as exc:
            if not tolerate_busy_replace or getattr(exc, "winerror", None) not in (5, 32, 33):
                raise
            if attempt == attempts - 1:
                logging.warning("Status update skipped after %d attempts: %s", attempts, exc)
                return
            time.sleep(.02 * (attempt + 1))


def load_config(path=None):
    path = Path(path or ROOT / "config.json").resolve()
    c = json.loads(path.read_text(encoding="utf-8"))
    path_keys = ["db", "profiles", "status", "model"]
    if "night_profiles" in c:
        path_keys.append("night_profiles")
    for key in path_keys:
        p = Path(c[key])
        c[key] = str(p if p.is_absolute() else path.parent / p)
    for key in ("inference_fps", "min_observed_seconds", "exit_grace_seconds"):
        if not isinstance(c[key], (int, float)) or not math.isfinite(c[key]) or c[key] <= 0:
            raise ValueError(f"{key} must be positive and finite")
    if not 0 < c["identity_vote_ratio"] <= 1:
        raise ValueError("identity_vote_ratio must be in (0,1]")
    min_luma = c.get("identity_min_scene_luma", 0)
    if not isinstance(min_luma, (int, float)) or not 0 <= min_luma <= 255:
        raise ValueError("identity_min_scene_luma must be in [0,255]")
    if "night_profiles" in c:
        night_min = c.get("night_min_scene_luma")
        night_max = c.get("night_max_scene_luma")
        if (not isinstance(night_min, (int, float)) or not isinstance(night_max, (int, float))
                or not 0 <= night_min < night_max <= 255):
            raise ValueError("Night mode requires ordered luminance thresholds in [0,255]")
        night_grace = c.get("night_exit_grace_seconds", c["exit_grace_seconds"])
        if (not isinstance(night_grace, (int, float)) or not math.isfinite(night_grace)
                or night_grace < c["exit_grace_seconds"]):
            raise ValueError("Night exit grace must be finite and at least the normal exit grace")
        night_vote = c.get("night_identity_vote_ratio", c["identity_vote_ratio"])
        if not isinstance(night_vote, (int, float)) or not 0 < night_vote <= 1:
            raise ValueError("night_identity_vote_ratio must be in (0,1]")
    if len(c["cats"]) != 2 or len(set(c["cats"])) != 2 or "unknown" in c["cats"]:
        raise ValueError("Configure two distinct cat names, excluding 'unknown'")
    z = c["zone"]
    if z is not None and (len(z) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in z)
                          or not (0 <= z[0] < z[2] <= 1 and 0 <= z[1] < z[3] <= 1)):
        raise ValueError("zone must be normalized [x1,y1,x2,y2] or null")
    return c


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, timeout=10)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute('''CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, camera_id TEXT NOT NULL, start_ts REAL NOT NULL,
            end_ts REAL NOT NULL, observed_seconds REAL NOT NULL, cat TEXT NOT NULL,
            identity_ratio REAL NOT NULL, ambiguous INTEGER NOT NULL,
            end_reason TEXT NOT NULL, review TEXT NOT NULL DEFAULT 'pending',
            kind TEXT NOT NULL DEFAULT 'water_zone_visit', reviewed_cat TEXT,
            snapshot_jpeg BLOB, snapshot_ts REAL)''')
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(events)")}
        if "snapshot_jpeg" not in columns:
            self.conn.execute("ALTER TABLE events ADD COLUMN snapshot_jpeg BLOB")
        if "snapshot_ts" not in columns:
            self.conn.execute("ALTER TABLE events ADD COLUMN snapshot_ts REAL")
        self.conn.execute("CREATE INDEX IF NOT EXISTS events_start ON events(start_ts)")
        self.conn.commit()

    def save(self, event):
        keys = list(event)
        with self.conn:
            self.conn.execute(f"INSERT INTO events ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
                              [event[k] for k in keys])

    def close(self):
        self.conn.close()


class VisitEngine:
    """Group continuous observations in the feeding area into candidate meals.

    Multiple cats in the zone make the entire session unknown. Identity is voted
    over the entire session, including unknown observations. Missing frames do
    not add observed seconds. Continuous identity handoffs are merged/unknown.
    """
    def __init__(self, camera_id, minimum=3., grace=3., vote_ratio=.8, max_step=1.,
                 *, night_grace=None, night_vote_ratio=None):
        self.camera_id = camera_id
        self.minimum, self.grace, self.vote_ratio, self.max_step = minimum, grace, vote_ratio, max_step
        self.night_grace = grace if night_grace is None else night_grace
        self.night_vote_ratio = vote_ratio if night_vote_ratio is None else night_vote_ratio
        self.active = None
        self.previous_present = False
        self.previous_ts = None
        self.signal_lost_since = None

    def tick(self, ts, identities, *, night=False, frame_available=True, inherited=False):
        if self.previous_ts is not None and ts < self.previous_ts:
            raise ValueError("timestamps must be monotonic")
        done = []
        if not frame_available and self.signal_lost_since is None:
            self.signal_lost_since = ts
        if self.active:
            grace = self.night_grace if self.active["night"] else self.grace
            signal_lost = self.signal_lost_since is not None and ts - self.signal_lost_since >= self.grace
            if signal_lost or ts - self.active["last"] > grace:
                event = self.finish("no_signal" if signal_lost else "left_zone")
                if event:
                    done.append(event)
        if frame_available:
            self.signal_lost_since = None
        if identities:
            if self.active is None:
                self.active = dict(start=ts, last=ts, observed=0., votes=Counter(), ambiguous=False, night=night)
            a = self.active
            if self.previous_present and self.previous_ts is not None:
                a["observed"] += min(ts - self.previous_ts, self.max_step)
            a["last"] = ts
            a["ambiguous"] |= len(identities) > 1
            if not inherited or len(identities) != 1:
                a["votes"][identities[0] if len(identities) == 1 else "unknown"] += 1
            a["ambiguous"] |= len(set(a["votes"]) - {"unknown"}) > 1
        self.previous_present, self.previous_ts = bool(identities), ts
        return done

    def identity(self):
        a = self.active
        if a is None:
            return None, None
        if not a["votes"]:
            return "unknown", 0.
        cat, n = a["votes"].most_common(1)[0]
        ratio = n / sum(a["votes"].values())
        vote_ratio = self.night_vote_ratio if a["night"] else self.vote_ratio
        if a["ambiguous"] or ratio < vote_ratio or n < 3:
            cat = "unknown"
        return cat, ratio

    def snapshot_due(self, current_name):
        return (self.active is not None and self.active["observed"] >= 5
                and "snapshot_jpeg" not in self.active and current_name not in (None, "unknown")
                and current_name == self.identity()[0])

    def attach_snapshot(self, jpeg, captured_at):
        self.active.update(snapshot_jpeg=jpeg, snapshot_ts=captured_at)

    def finish(self, reason="stopped"):
        a = self.active
        cat, ratio = self.identity()
        self.active = None
        self.previous_present = False
        if a is None or a["observed"] < self.minimum:
            return None
        event = dict(camera_id=self.camera_id, start_ts=a["start"], end_ts=a["last"],
                    observed_seconds=round(a["observed"], 3), cat=cat,
                    identity_ratio=ratio, ambiguous=int(a["ambiguous"]), end_reason=reason,
                    kind=FEEDING_EVENT)
        if "snapshot_jpeg" in a:
            event.update(snapshot_jpeg=a["snapshot_jpeg"], snapshot_ts=a["snapshot_ts"])
        return event
