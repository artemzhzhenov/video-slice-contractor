"""How much of the head the hand and the forearm cover — ACCEPTANCE item 4 of burst 2 ("the hand covers a
fifth to a half of the head silhouette", slice/state_requirements.json → hand_over_head), measured on the
render instead of bounding boxes: on the SHOT_003 early checkpoint (2026-09-25) boxes said 28 % where the
render shows 16 %. Per rendered frame of a split video render:

  head      the default head's full silhouette (head + hair), re-projected from the exports at the centre
            sample (slice/roundtrip.py) — HEAD_HOLDOUT itself is cut by the forearm, so it cannot be used;
  forearm   the objects that hold the head out (C_BODY / C_ENV; object cryptomatte ≥ 0.5) over the head;
  hand      the foreground plate (C_HAND_FG; FOREGROUND_PLATE alpha ≥ 0.5) over the head;
  covered   (forearm or hand) / head.

The range holds on every frame of the hand_over_face window, not only at the peak (Q40, 2026-09-25: the hand
at the eyes is a hold — the SHOT_003 v02 work in progress had 0.255 / 0.107 / 0.081, in range at the peak
only). Render every frame of the window first — any scale, a few samples are enough for mattes; acceptance
measures every frame, so a self-check on every other frame must include both edges of the window:

    blender -b SHOT_003_vNN.blend --python-exit-code 2 -P slice/render_passes.py -- --shot SHOT_003 \\
        --profile video --frames 1305-1332 --samples 16 --scale 25 --out /tmp/hand
    blender -b --python-exit-code 2 -P slice/split_bundles.py -- /tmp/hand/video --no-plus-files
    blender -b --python-exit-code 2 -P slice/measure_hand_over_head.py -- <exports> /tmp/hand/video [--json out.json]

Prints one HAND_OVER_HEAD line per frame (OUT marks a frame outside the range), then HAND_OVER_HEAD_IN_RANGE
when every measured frame is in range or HAND_OVER_HEAD_OUT_OF_RANGE naming the frames outside it, with the
lowest and the peak frame. The number informs the owner, who judges the gesture (a human item): the exit code is 0 either way,
2 only when it cannot measure."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np  # noqa: E402
from slice import roundtrip as rt  # noqa: E402
from slice.composite import read_parts  # noqa: E402

RULE = json.loads((ROOT / "slice" / "state_requirements.json").read_text())["hand_over_head"]


def measure(ex, rd):
    manifests = sorted(rd.glob("bundle_manifest.*.json"))
    if len(manifests) != 1:
        raise rt.RoundTripError(f"expected one bundle_manifest in {rd}, found {len(manifests)} — run split_bundles.py first")
    bm = json.loads(manifests[0].read_text())
    rm = json.loads((rd / bm["source_render_manifest"]).read_text())
    scale = rm["settings"]["resolution_percentage"]
    exman = json.loads((ex / "export_manifest.json").read_text())
    if exman["shot_id"] != bm["shot_id"]:
        raise rt.RoundTripError(f"exports are for {exman['shot_id']}, renders for {bm['shot_id']}")
    cams = {f["frame"]: f for f in json.loads((ex / "camera.json").read_text())["frames"]}
    socks = {f["frame"]: f for f in json.loads((ex / "socket.json").read_text())["frames"]}
    verts, faces = rt.load_obj(ex / "default_head_rest.obj")
    deformed = np.load(ex / exman["default_head_deformed"]["file"], allow_pickle=False)
    offs = rt.CONV["exports"]["sub_frame_offsets_frames"]
    classes = {k: exman[k] for k in ("head_objects", "occluder_objects", "holdout_objects")}
    rows = []
    for row in bm["bundles"]["COMPOSITE_BUNDLE"]["frames"]:
        fr = row["frame"]
        comp = read_parts(rd / "COMPOSITE_BUNDLE" / row["file"])
        fg = comp["FOREGROUND_PLATE"][0][..., 3]
        h, w = fg.shape
        px = cams[fr]["intrinsics"]["px_by_profile"][bm["profile"]]
        f = scale / 100
        cov = rt.coverage_for_frame(rt.head_at(deformed[fr - exman["frames"][0]], verts, offs), faces, rt.samples_of(socks[fr], "matrix_4x4"),
                                    rt.samples_of(cams[fr], "extrinsic_matrix_4x4"), [v * f for v in px["focal_length_px"]],
                                    [v * f for v in px["principal_point_px"]], w, h, [0.0])
        head = cov >= 0.5
        n = int(head.sum())
        if not n:
            raise rt.RoundTripError(f"frame {fr}: the head is not in frame")
        hold, _ = rt.holdout_coverage(rd / "COMPOSITE_BUNDLE" / row["file"], classes)
        forearm, hand = head & (hold >= 0.5), head & (fg >= 0.5)
        rows.append({"frame": fr, "head_px": n, "forearm": round(float(forearm.sum()) / n, 4), "hand": round(float(hand.sum()) / n, 4),
                     "covered": round(float((forearm | hand).sum()) / n, 4)})
    return bm["shot_id"], scale, rows


def judge(rows, rule=RULE):
    """The verdict over every measured frame: in range only when each frame is — a hold, not a peak (Q40)."""
    lo, hi = rule["fraction_min"], rule["fraction_max"]
    out = [r["frame"] for r in rows if not lo <= r["covered"] <= hi]
    return {"status": "OUT_OF_RANGE" if out else "IN_RANGE", "frames_out_of_range": out,
            "lowest": min(rows, key=lambda r: r["covered"]), "peak": max(rows, key=lambda r: r["covered"])}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("exports")
    ap.add_argument("renders", help="renders/<profile> of a split render (split_bundles.py; --no-plus-files is enough)")
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)
    shot, scale, rows = measure(Path(a.exports), Path(a.renders))
    v = judge(rows)
    for r in rows:
        mark = " OUT" if r["frame"] in v["frames_out_of_range"] else ""
        print(f"HAND_OVER_HEAD {r['frame']} covered={r['covered']:.3f} (forearm {r['forearm']:.3f}, hand {r['hand']:.3f}) head_px={r['head_px']}{mark}")
    report = {"shot_id": shot, "resolution_percentage": scale, "rule": RULE, "frames": rows, **v,
              "frames_measured": [r["frame"] for r in rows],
              "note": "a human item: the owner judges the gesture; this is its measurement, on every frame measured"}
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=1) + "\n")
    lo, pk = v["lowest"], v["peak"]
    outs = f" — out of range on {', '.join(map(str, v['frames_out_of_range']))}" if v["frames_out_of_range"] else ""
    print(f"HAND_OVER_HEAD_{v['status']} on {len(rows)} frames{outs}: lowest {lo['covered']:.3f} at {lo['frame']}, "
          f"peak {pk['covered']:.3f} at {pk['frame']} (ACCEPTANCE item 4: {RULE['fraction_min']}–{RULE['fraction_max']} on every frame)")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    try:
        main(argv)
    except (rt.RoundTripError, OSError, KeyError, ValueError) as e:
        print(f"HAND_OVER_HEAD_ERROR: {e}", file=sys.stderr)
        sys.exit(2)
