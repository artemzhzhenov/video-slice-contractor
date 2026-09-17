"""The video frames slice/check_asset.sh renders, chosen from the shot's EXPORTS so the round-trip
has something to test: the shot's first frame, the frame whose head turns most WITHIN ITS OWN
SHUTTER (angle between the socket's first and last sub-frame samples — the sub-frame positive
control can only discriminate where the head moves across that frame's shutter; the first frame
of v01 did not, measured 2026-09-16; camera motion is not ranked) and the frame with the widest
open jaw (the deformed-head re-projection is exercised where the rest head would fail — v01
frame 1100).
Plain Python, no Blender:

    python3 slice/pick_frames.py <exports dir>        # prints e.g. 1001,1090,1102

Frames are printed ascending and without duplicates; ties go to the earliest frame. A shot
whose head never turns or whose jaw never opens yields fewer frames, never an invented one."""
import json
import math
import sys
from pathlib import Path


def pick(exports):
    d = Path(exports)
    sock = json.loads((d / "socket.json").read_text())["frames"]
    track = json.loads((d / "performance_track.json").read_text())["frames"]
    frames = [f["frame"] for f in sock]
    picked = {frames[0]}
    best, best_at = 0.0, None
    for f in sock:
        ends = sorted(f["samples"], key=lambda s: s["offset"])
        dot = min(1.0, abs(sum(x * y for x, y in zip(ends[0]["quaternion"], ends[-1]["quaternion"]))))
        ang = 2 * math.acos(dot)
        if ang > best:
            best, best_at = ang, f["frame"]
    if best_at is not None:
        picked.add(best_at)
    jaw = [(f["channels"]["jaw_open"], -f["frame"]) for f in track]
    top = max(jaw)
    if top[0] > 0:
        picked.add(-top[1])
    return sorted(picked)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: pick_frames.py <exports dir>", file=sys.stderr)
        sys.exit(64)
    print(",".join(str(f) for f in pick(sys.argv[1])))
