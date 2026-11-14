"""ByteTrack association and short-lived identity evidence for one camera."""
import math
from types import SimpleNamespace


class CatTracker:
    def __init__(self, confidence, fps, grace):
        from ultralytics.trackers.byte_tracker import BYTETracker

        self.tracker = BYTETracker(SimpleNamespace(
            track_high_thresh=confidence, track_low_thresh=min(.10, confidence),
            new_track_thresh=confidence, track_buffer=math.ceil(fps * grace),
            match_thresh=.8, fuse_score=False,
        ))
        self.identities = {}
        self.identity_seconds = 5.

    def update(self, boxes):
        # Each row ends with the original detection index; use its real mask.
        return {int(row[-1]): int(row[4]) for row in self.tracker.update(boxes)}

    def reset(self):
        self.tracker.reset()
        self.identities.clear()

    def resolve(self, ts, observations):
        self.identities = {key: evidence for key, evidence in self.identities.items()
                           if ts - evidence[2] <= self.identity_seconds}
        # Overlapping detections can swap track IDs. Suspend inherited names.
        if len(observations) > 1:
            self.identities.clear()
            return [(name, False) for _, name in observations]
        results = []
        for track_id, raw_name in observations:
            evidence = self.identities.get(track_id)
            if track_id is None:
                results.append((raw_name, False))
            elif raw_name != "unknown":
                # A conflicting fresh match invalidates the previous name immediately.
                count = evidence[1] + 1 if evidence and evidence[0] == raw_name else 1
                self.identities[track_id] = (raw_name, count, ts)
                results.append((raw_name, False))
            elif evidence and evidence[1] >= 3:
                results.append((evidence[0], True))
            else:
                results.append(("unknown", False))
        return results
