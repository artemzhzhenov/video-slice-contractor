"""What one hand can cover at all: the whole hand's projected area against the head silhouette (head + hair),
per frame of a split render — the attainability check behind hand_over_head.fraction_min (2026-09-26). If the
hand lies entirely on the head and still covers less than the bound, no placement reaches it.

    blender -b --python-exit-code 2 -P slice/measurements/hand_area_vs_head.py -- <exports> <renders/video> <out.json>

Measured on SHOT_003 v01 (the early checkpoint, every frame of 1305-1332 at 25 %, 16 samples) →
slice/measurements/hand_over_head_attainable_2026-09-26.json."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from slice import roundtrip as rt  # noqa: E402
from slice.measure_hand_over_head import measure  # noqa: E402
from slice.composite import read_parts  # noqa: E402

ex, rd, out = (Path(a) for a in sys.argv[sys.argv.index("--") + 1:][:3])
shot, scale, rows = measure(ex, rd)
bm = json.loads(next(rd.glob("bundle_manifest.*.json")).read_text())
files = {r["frame"]: r["file"] for r in bm["bundles"]["COMPOSITE_BUNDLE"]["frames"]}
for r in rows:
    fg = read_parts(rd / "COMPOSITE_BUNDLE" / files[r["frame"]])["FOREGROUND_PLATE"][0][..., 3]
    whole = float((fg >= 0.5).sum()) / r["head_px"]
    r["whole_hand"] = round(whole, 4)
    r["hand_share_on_head"] = round(r["hand"] / whole, 3) if whole else None
held = [r for r in rows if r["hand_share_on_head"] and r["hand_share_on_head"] >= 0.99]
record = {
    "what": "attainability of hand_over_head.fraction_min: the whole hand's projected area against the head silhouette (head + hair)",
    "date": "2026-09-26", "shot": shot, "source": "SHOT_003_v01.blend (contractor's early checkpoint, 2026-09-25)",
    "render": f"{scale} %, 16 samples, every frame of hand_over_face 1305-1332", "tool": "slice/measurements/hand_area_vs_head.py",
    "frames": rows,
    "hand_entirely_on_the_head": {"frames": [r["frame"] for r in held], "hand": [r["hand"] for r in held],
                                  "forearm": [r["forearm"] for r in held], "covered": [r["covered"] for r in held]},
    "whole_hand_max": max(rows, key=lambda r: r["whole_hand"]),
    "finding": "where the whole hand lies on the head it covers 0.09-0.10 of the silhouette and the forearm adds ~0.04; the whole hand "
               "never exceeds ~0.16 (turned towards the camera as it leaves). One child's hand cannot reach 0.2 of the head with hair; "
               "the task's 'a fifth to a half' was an eyeball estimate of the face, turned into a pixel gate on 2026-09-25 without this check",
    "decision": "owner, 2026-09-26 (option 1): the hand covers the near eye entirely, fingers across the bridge towards the far eye, on every "
                "frame of the window — judged by the owner on the GPU preview; the measure keeps 0.1-0.5 on every frame against a token hand",
}
out.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n")
print(f"HAND_AREA_OK {len(rows)} frames; entirely on the head: {len(held)} frames, hand {min(record['hand_entirely_on_the_head']['hand'], default=0):.3f}-"
      f"{max(record['hand_entirely_on_the_head']['hand'], default=0):.3f}; whole hand max {record['whole_hand_max']['whole_hand']:.3f} at {record['whole_hand_max']['frame']}")
