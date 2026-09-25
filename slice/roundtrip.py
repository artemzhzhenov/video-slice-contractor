"""D7 round-trip test (ADR-0002 D7; brief deliverable H; conventions.json → roundtrip).

Re-projects the default head from the EXPORTED data alone — camera.json, socket.json,
default_head_rest.obj (faces, rigid hair) and default_head_deformed.npy (the C_HEAD vertices as
the renderer saw them at every sub-frame sample) — and compares its matte against HEAD_HOLDOUT
from the HEAD_RENDER bundle. The deformed head makes the test compare transforms, not facial
deformation: the rest head failed a correct export on an open jaw (contractor v01, frame 1100,
2026-09-16); it is still re-projected on every frame and reported as `rest_head_comparison`.
No scene is loaded: if the numbers written to the head technology cannot put the head where the
renderer put it, this is where it shows. Runs under Blender's Python for numpy + OpenImageIO:

    blender -b --python-exit-code 2 -P slice/roundtrip.py -- --exports <shot exports> \
        --renders <pkg>/shots/SHOT_001/renders/<profile> [--ignore-subframes]

Per frame: p95 symmetric boundary distance between the sub-pixel 0.5 iso-contours, centroid
displacement, IoU of the ≥0.5 silhouettes and the mean absolute coverage difference in the edge
band — all four gated with PROVISIONAL thresholds (conventions.json → roundtrip.gate), pixel
thresholds scaled by the render's resolution percentage. Pixels where the body or environment
is in front of the re-projected head are excluded from the comparison and their fraction is
reported (C_BODY / C_ENV hold the head out in L_HEAD; only C_HAND_FG occluders are shadow-only).
Negative controls run on every frame and MUST fail the gate, else the metric is NOT VALIDATED
and the script exits 2: a socket translation worth 5 px on screen and a focal scale that grows
the silhouette by 5 px; a 3° yaw is reported VALIDATED / NOT_VALIDATED. The positive control
compares the shutter-integrated result with the centre sample and reports DISCRIMINATING or
NOT_DISCRIMINATING per frame (a frame that does not move across the shutter cannot
discriminate).

The shutter is integrated over the exports' own sub-frame samples (nine since the ADR-0002
amendment of 2026-09-25) with trapezoid weights, against a blur reference rendered at the same
instants — the reference's render manifest must say so. When the blurred matte comes from that
reference, the centre sample is ALSO gated against the plates' own sharp HEAD_HOLDOUT: the plates
are rendered with the time stretched so their vectors reach the shutter's ends, and nothing else
compares their head with the exports.
The bundle manifest's roundtrip status is set to ERROR before the first frame and to the result
after the last, so an aborted run never leaves a stale PASS. Writes roundtrip_report.<profile>.json."""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slice.camera_model import project  # noqa: E402
from slice.composite import coverage, crypto_manifest, read_parts  # noqa: E402
from slice.cryptomatte import float_id_from_hex  # noqa: E402
from slice.matte_metrics import SS, MatteError, iou_min_for, metrics, rasterize, reference_quantization_px  # noqa: E402

CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
RT = CONV["roundtrip"]


class RoundTripError(RuntimeError):
    pass


# ---------------------------------------------------------------- geometry

def load_obj(path):
    verts, faces = [], []
    for line in Path(path).read_text().splitlines():
        if line.startswith("v "):
            verts.append([float(t) for t in line.split()[1:4]])
        elif line.startswith("f "):
            idx = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
            for k in range(1, len(idx) - 1):  # fan triangulation: exact for convex polygons (quads/tris here); a concave n-gon would over-cover
                faces.append([idx[0], idx[k], idx[k + 1]])
    if not verts or not faces:
        raise RoundTripError(f"{path}: no geometry")
    return np.asarray(verts, np.float64), np.asarray(faces, np.int64)


def slerp(q0, q1, t):
    q0, q1 = np.asarray(q0, float), np.asarray(q1, float)
    d = float(np.dot(q0, q1))
    if d < 0:
        q1, d = -q1, -d
    if d > 0.9995:
        q = q0 + t * (q1 - q0)
        return q / np.linalg.norm(q)
    th = math.acos(d)
    return (math.sin((1 - t) * th) * q0 + math.sin(t * th) * q1) / math.sin(th)


def quat_to_mat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def sample_at(samples, offset):
    """Similarity transform (4x4) at a shutter offset, interpolated between the exported
    sub-frame samples: position and scale linear, rotation slerp (conventions.roundtrip)."""
    offs = [s["offset"] for s in samples]
    if offset <= offs[0]:
        return np.asarray(samples[0]["matrix"], float)
    if offset >= offs[-1]:
        return np.asarray(samples[-1]["matrix"], float)
    k = max(i for i, o in enumerate(offs) if o <= offset)
    a, b = samples[k], samples[k + 1]
    t = (offset - a["offset"]) / (b["offset"] - a["offset"])
    q = slerp(a["quaternion"], b["quaternion"], t)
    s = (1 - t) * a["scale"] + t * b["scale"]
    p = (1 - t) * np.asarray(a["position_m"]) + t * np.asarray(b["position_m"])
    m = np.eye(4)
    m[:3, :3] = quat_to_mat(q) * s
    m[:3, 3] = p
    return m


def reproject(verts, faces, socket_m, cam_m, fx_fy, cx_cy, w, h):
    world = (socket_m @ np.c_[verts, np.ones(len(verts))].T).T[:, :3]
    cam_inv = np.linalg.inv(cam_m)
    cam = (cam_inv @ np.c_[world, np.ones(len(world))].T).T[:, :3]
    uv = np.asarray([(u, v) for u, v, _ in project(cam, fx_fy, cx_cy)], float)
    return rasterize(uv[faces], w, h)


def head_at(samples_xyz, rest_verts, sample_offsets):
    """verts(offset) for one frame: the exported deformed C_HEAD vertices (samples_xyz, one row
    per exported sub-frame offset) interpolated linearly between samples, like the socket's
    position; the remaining OBJ vertices (rigid hair) from the rest head."""
    n = samples_xyz.shape[1]
    rows = np.asarray(samples_xyz, np.float64)

    def at(offset):
        if offset <= sample_offsets[0]:
            cur = rows[0]
        elif offset >= sample_offsets[-1]:
            cur = rows[-1]
        else:
            k = max(i for i, o in enumerate(sample_offsets) if o <= offset)
            t = (offset - sample_offsets[k]) / (sample_offsets[k + 1] - sample_offsets[k])
            cur = (1 - t) * rows[k] + t * rows[k + 1]
        v = rest_verts.copy()
        v[:n] = cur
        return v
    return at


def coverage_for_frame(verts, faces, sock_samples, cam_samples, fx_fy, cx_cy, w, h, offsets, weights=None):
    """verts: an (N, 3) array, or a function offset → (N, 3) array (head_at). `weights` (default
    equal) average the instants — trapezoid over the exported sub-frame samples since the ADR-0002
    amendment of 2026-09-25: the continuous average of the path through them, as the renderer's
    shutter integrates between its own time points."""
    wts = np.ones(len(offsets)) if weights is None else np.asarray(weights, np.float64)
    acc = np.zeros((h, w), np.float64)
    for off, wt in zip(offsets, wts):
        v = verts(off) if callable(verts) else verts
        acc += wt * reproject(v, faces, sample_at(sock_samples, off), sample_at(cam_samples, off), fx_fy, cx_cy, w, h)
    return (acc / wts.sum()).astype(np.float32)


def trapezoid_weights(n):
    w = np.ones(n)
    if n > 1:
        w[0] = w[-1] = 0.5
    return w


def samples_for_quantization(q_at_one_sample, floor_samples):
    """Reference samples that bring the contour quantization to conventions → roundtrip.
    reference_quantization.target_px: the estimate scales as 1/n (matte_metrics), rounded up to the
    step and never below floor_samples."""
    qr = RT["reference_quantization"]
    return max(int(floor_samples), int(math.ceil(q_at_one_sample / qr["target_px"] / qr["samples_step"])) * qr["samples_step"])


def plan_reference_samples(frames, cam_by_frame, sock_by_frame, deformed, first, verts, faces, offsets, profile, scale, floor_samples):
    """How many samples the blur reference needs so that ITS quantization does not decide the
    round-trip: per frame, the shutter-integrated re-projection's own ramps (no reference needed —
    it does not exist yet) give the quantization at one sample; the run needs the largest. Found on
    SHOT_002 1209 at 4K (2026-09-25): at 64 samples the reference alone cost the IoU 0.23 of its
    0.15 px budget and a correct export failed; at 256 it passed."""
    rows, need = [], int(floor_samples)
    weights = trapezoid_weights(len(offsets))
    for frame in frames:
        px = cam_by_frame[frame]["intrinsics"]["px_by_profile"][profile]
        f = scale / 100.0
        w, h = [round(v * f) for v in px["resolution_px"]]
        cov = coverage_for_frame(head_at(deformed[frame - first], verts, offsets), faces, samples_of(sock_by_frame[frame], "matrix_4x4"),
                                 samples_of(cam_by_frame[frame], "extrinsic_matrix_4x4"), [v * f for v in px["focal_length_px"]],
                                 [v * f for v in px["principal_point_px"]], w, h, offsets, weights)
        q1 = reference_quantization_px(cov, 1)
        n = samples_for_quantization(q1, floor_samples)
        rows.append({"frame": frame, "quantization_px_at_one_sample": round(q1, 3), "samples_needed": n})
        need = max(need, n)
    cap = RT["reference_quantization"]["samples_max"]
    if need > cap:
        raise RoundTripError(f"the blur reference would need {need} samples on frames {[r['frame'] for r in rows if r['samples_needed'] > cap]} "
                             f"(cap {cap}, conventions → roundtrip.reference_quantization): motion this wide cannot be resolved by a "
                             "reference render at this scale — measure it at a lower scale or raise the cap deliberately")
    return need, rows


def thresholds_for(shot, frame, scale):
    g = RT["gate"]["default"]
    sw = RT["gate"]["stress_window"]
    if shot == sw["shot_id"] and sw["frames"][0] <= frame <= sw["frames"][1]:
        g = sw
    f = scale / 100.0
    # Pixel thresholds scale with the render; the boundary distance is quantised to 1/SS px by
    # the upsampled iso-contour, so its threshold never drops below 2/SS — one quantum of
    # headroom (review round 2). IoU and the band coverage difference are resolution-free.
    return {"p95_boundary_px_max": max(g["p95_boundary_px_max"] * f, 2.0 / SS),
            "centroid_px_max": g["centroid_px_max"] * f,
            "iou_boundary_error_px_max": g["iou_boundary_error_px_max"], "iou_rule": RT["gate"]["iou_rule"],
            "mean_abs_coverage_in_band_max": RT["gate"]["mean_abs_coverage_in_band_max"],
            "body_over_head_excluded_fraction_max": RT["gate"]["body_over_head_excluded_fraction_max"]}


def iou_min_of(m, th):
    """This frame's IoU floor — the rule lives in matte_metrics so CI can test it without Blender."""
    r = th["iou_rule"]
    return iou_min_for(m, th["iou_boundary_error_px_max"], r["floor"], r["ceiling"])


def gate(m, th):
    failed = []
    if m["p95_boundary_px"] > th["p95_boundary_px_max"]:
        failed.append("p95_boundary_px")
    if m["centroid_px"] > th["centroid_px_max"]:
        failed.append("centroid_px")
    if m["iou"] < iou_min_of(m, th):
        failed.append("iou")
    if m["mean_abs_coverage_in_band"] > th["mean_abs_coverage_in_band_max"]:
        failed.append("mean_abs_coverage_in_band")
    return failed


# ---------------------------------------------------------------- driver

def samples_of(rec_frame, key):
    return [{"offset": s["offset"], "matrix": s[key], "quaternion": s["quaternion"], "position_m": s["position_m"], "scale": s["scale"]} for s in rec_frame["samples"]]


def perturb_translation(samples, cam_samples, fx, depth_px):
    """Displace the socket along the camera's x axis by the distance that moves it depth_px
    pixels at the centre sample's depth (conventions.roundtrip.negative_control.translation)."""
    cam_m = sample_at(cam_samples, 0.0)
    sock_m = sample_at(samples, 0.0)
    cam_inv = np.linalg.inv(cam_m)
    depth = -(cam_inv @ np.r_[sock_m[:3, 3], 1.0])[2]
    shift = cam_m[:3, 0] * (depth_px * depth / fx)
    out = []
    for s in samples:
        m = np.asarray(s["matrix"], float).copy()
        m[:3, 3] += shift
        out.append({**s, "matrix": m, "position_m": list(np.asarray(s["position_m"]) + shift)})
    return out, float(np.linalg.norm(shift))


def quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz]


def perturb_rotation(samples, yaw_deg):
    """Yaw about the socket's local +Y on EVERY sample: the matrix (used at the shutter's ends)
    and the quaternion (used by sample_at for every interior time) — review round 2 found the
    quaternion untouched, so 7 of 9 shutter samples were not rotated at all."""
    c, s_ = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    r = np.array([[c, 0, s_], [0, 1, 0], [-s_, 0, c]])
    q_yaw = [0.0, math.sin(math.radians(yaw_deg) / 2), 0.0, math.cos(math.radians(yaw_deg) / 2)]
    out = []
    for s in samples:
        m = np.asarray(s["matrix"], float).copy()
        m[:3, :3] = m[:3, :3] @ r
        q = quat_mul(s["quaternion"], q_yaw)
        n = math.sqrt(sum(v * v for v in q))
        q = [v / n for v in q]
        if q[3] < 0:
            q = [-v for v in q]
        out.append({**s, "matrix": m, "quaternion": q})
    return out


def holdout_coverage(comp_path, classes):
    """The summed cryptomatte coverage of the objects that hold the head out in L_HEAD
    (export_manifest → holdout_objects: C_BODY ∪ C_ENV), from the object cryptomatte of the
    COMPOSITE bundle. Where it covers the re-projected head (≥ 0.5 both) HEAD_HOLDOUT is cut by the
    renderer and cannot be reproduced from the exports, so those pixels are excluded and counted.
    Every geometry name in the cryptomatte manifest must be classified by the export (head /
    occluder / holdout); an unclassified name with coverage is an error, not a guess."""
    parts = read_parts(comp_path)
    attrs = parts["CRYPTO_OBJECT00"][1]
    names = [v for k, v in attrs.items() if k.startswith("cryptomatte/") and k.endswith("/name") and "Object" in v]
    if len(names) != 1:
        raise RoundTripError(f"expected one object cryptomatte manifest on CRYPTO_OBJECT00, found {names}")
    manifest = crypto_manifest(attrs, names[0])
    known = set(classes["head_objects"]) | set(classes["occluder_objects"]) | set(classes["holdout_objects"])
    cov = np.zeros(parts["CRYPTO_OBJECT00"][0].shape[:2], np.float32)
    unclassified = []
    for name, hex_id in manifest.items():
        c = coverage(parts, "OBJECT", float_id_from_hex(hex_id))
        if name in classes["holdout_objects"]:
            cov += c
        elif name not in known:
            if float(c.max()) > 0:
                raise RoundTripError(f"cryptomatte object {name!r} has coverage but is not classified by the export (head / occluder / holdout)")
            unclassified.append(name)  # lights and empties: no coverage, no class
    return cov, {"holdout_objects": sorted(n for n in manifest if n in classes["holdout_objects"]), "unclassified_without_coverage": sorted(unclassified)}


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--exports", required=True)
    p.add_argument("--renders", required=True, help="renders/<profile> directory with a bundle_manifest")
    p.add_argument("--ignore-subframes", action="store_true", help="centre sample only, written as a separate report")
    p.add_argument("--plan-reference-samples", action="store_true",
                   help="before the blur reference exists: print BLUR_REFERENCE_SAMPLES <n>, the samples it needs so that its "
                        "quantization does not decide the comparison (conventions → roundtrip.reference_quantization); "
                        "writes reference_plan.<profile>.json and leaves the bundle manifest alone")
    p.add_argument("--min-samples", type=int, default=None, help="with --plan-reference-samples: the floor (default: the plates' samples)")
    p.add_argument("--blur-reference", default=None,
                   help="the --blur-reference render of the same frames. Since the 2026-09-22 amendment the plates are "
                        "rendered sharp, so the matte to compare a shutter-integrated re-projection with lives there; "
                        "without it this run tests the centre sample only and says so")
    args = p.parse_args(argv)
    ex, rd = Path(args.exports), Path(args.renders)
    manifests = sorted(rd.glob("bundle_manifest.*.json"))
    if len(manifests) != 1:
        raise RoundTripError(f"expected one bundle_manifest in {rd}, found {len(manifests)} — run split_bundles.py first")
    bm = json.loads(manifests[0].read_text())
    if not args.ignore_subframes and not args.plan_reference_samples:
        # First thing after the manifest is read: an aborted run (missing export, bad OBJ, a frame
        # that raises) must leave ERROR behind, never the previous run's status.
        bm["roundtrip"] = {"status": "ERROR", "note": "run started and did not finish", "script": RT["script"]}
        manifests[0].write_text(json.dumps(bm, indent=1) + "\n")
    rm = json.loads((rd / bm["source_render_manifest"]).read_text())
    profile, shot = bm["profile"], bm["shot_id"]
    scale = rm["settings"]["resolution_percentage"]
    cam_rec = json.loads((ex / "camera.json").read_text())
    sock_rec = json.loads((ex / "socket.json").read_text())
    exman = json.loads((ex / "export_manifest.json").read_text())
    track = json.loads((ex / "performance_track.json").read_text())
    if exman["shot_id"] != shot:
        raise RoundTripError(f"exports are for {exman['shot_id']}, renders for {shot}")
    prof = CONV["render_profiles"][profile]
    vp = CONV["render_profiles"]["video"]
    want_offsets = CONV["exports"]["sub_frame_offsets_frames"]
    ends = [-vp["shutter_angle_deg"] / 720, vp["shutter_angle_deg"] / 720]
    if [want_offsets[0], want_offsets[-1]] != ends or 0.0 not in want_offsets or want_offsets != sorted(want_offsets):
        raise RoundTripError(f"conventions' sub-frame offsets {want_offsets} do not run from shutter open to close {ends} through the centre")
    if cam_rec["sub_frame_offsets_frames"] != want_offsets or sock_rec["sub_frame_offsets_frames"] != want_offsets:
        raise RoundTripError(f"exported sub-frame offsets {cam_rec['sub_frame_offsets_frames']} are not the conventions' {want_offsets} — re-export with the current export_shot.py")
    verts, faces = load_obj(ex / "default_head_rest.obj")
    dh = exman.get("default_head_deformed")
    if dh is None or not (ex / dh["file"]).exists():
        raise RoundTripError("the exports carry no default_head_deformed.npy — re-export with the current export_shot.py (the rest head alone cannot be compared with a deformed frame)")
    deformed = np.load(ex / dh["file"], allow_pickle=False)
    first, last = exman["frames"]
    n_head = sum(o["vertices"] for o in dh["objects"])
    if list(deformed.shape) != dh["shape"] or deformed.shape != (last - first + 1, len(want_offsets), n_head, 3) or n_head > len(verts):
        raise RoundTripError(f"default_head_deformed.npy shape {deformed.shape} does not match the manifest {dh['shape']}, the shot range, the offsets or the head OBJ ({len(verts)} vertices)")
    rest_dev = float(np.abs(deformed[0, want_offsets.index(0.0)].astype(np.float64) - verts[:n_head]).max())
    if rest_dev > CONV["exports"]["default_head_deformed"]["rigid_tolerance_m"]:
        raise RoundTripError(f"default_head_deformed.npy at the rest sample differs from default_head_rest.obj by {rest_dev:.2e} m — the two do not share a vertex order or a frame")
    classes = {k: exman[k] for k in ("head_objects", "occluder_objects", "holdout_objects")}
    if args.plan_reference_samples:
        if prof["shutter_angle_deg"] <= 0:
            raise RoundTripError(f"profile {profile} has no shutter: there is no blur reference to plan")
        frames = [r["frame"] for r in bm["bundles"]["HEAD_RENDER_BUNDLE"]["frames"]]
        floor = args.min_samples if args.min_samples is not None else rm["settings"]["samples"]
        need, rows = plan_reference_samples(frames, {f["frame"]: f for f in cam_rec["frames"]}, {f["frame"]: f for f in sock_rec["frames"]},
                                            deformed, first, verts, faces, want_offsets, profile, scale, floor)
        plan = {"schema_note": "blur-reference sample plan; conventions.json → roundtrip.reference_quantization", "shot_id": shot, "profile": profile,
                "resolution_percentage": scale, "floor_samples": floor, "samples": need, "frames": rows, "rule": RT["reference_quantization"]}
        (rd / f"reference_plan.{profile}.json").write_text(json.dumps(plan, indent=1) + "\n")
        for r in rows:
            print(f"PLAN_FRAME {r['frame']} quantization_at_one_sample={r['quantization_px_at_one_sample']}px needs={r['samples_needed']}")
        print(f"BLUR_REFERENCE_SAMPLES {need}")
        return
    # Compare like with like. The plates are sharp since the 2026-09-22 amendment (ADR-0002 D5),
    # so integrating the re-projection across the shutter and comparing it with a sharp matte
    # fails frames that are perfectly exported — measured on SHOT_001 v01 at 100 %: centroid
    # 0.81 px and band 0.29 on the laugh peak. The motion-blurred matte now comes from the
    # blur-reference render, which is also what the blur-fidelity gate uses.
    ref_dir = Path(args.blur_reference) if args.blur_reference else None
    ref_frames = {}
    if ref_dir:
        refman = sorted(ref_dir.glob("render_manifest.*.json")) or sorted(ref_dir.glob("*/render_manifest.*.json"))
        if len(refman) != 1:
            raise RoundTripError(f"expected one render_manifest under {ref_dir}, found {len(refman)}")
        rman = json.loads(refman[0].read_text())
        if rman.get("kind") != "blur_reference" or not rman["settings"].get("render_motion_blur"):
            raise RoundTripError(f"{refman[0].name} is not a blur-reference render (shutter open) — see render_passes.py --blur-reference")
        if rman["settings"]["resolution_percentage"] != scale or rman["shot_id"] != shot:
            raise RoundTripError("the blur reference was rendered for another shot or scale")
        if rman["settings"].get("shutter_time_points") != len(want_offsets):
            raise RoundTripError(f"the blur reference samples the shutter at {rman['settings'].get('shutter_time_points')} instants and the exports at "
                                 f"{len(want_offsets)} — compare like with like: re-render it with render_passes.py --blur-reference (motion steps follow the exports)")
        ref_frames = {r["frame"]: refman[0].parent / "raw" / r["files"]["blur_reference"]["file"] for r in rman["frames"]}
        ref_samples = rman["settings"]["samples"]
    plates_blurred = bool(rm["settings"].get("render_motion_blur"))
    integrate = prof["shutter_angle_deg"] > 0 and not args.ignore_subframes and (plates_blurred or bool(ref_frames))
    matte_source = ("the plates" if plates_blurred or not integrate else "the blur-reference render")
    offsets = list(want_offsets) if integrate else [0.0]
    weights = list(trapezoid_weights(len(offsets)))
    cam_by_frame = {f["frame"]: f for f in cam_rec["frames"]}
    sock_by_frame = {f["frame"]: f for f in sock_rec["frames"]}
    track_by_frame = {f["frame"]: max(abs(v) for v in f["channels"].values()) for f in track["frames"]}
    report = {"schema_note": "D7 round-trip report; conventions.json → roundtrip", "shot_id": shot, "profile": profile,
              "smoke_test_only": bm["smoke_test_only"], "resolution_percentage": scale,
              "reference": RT["reference"], "matte_source": matte_source,
              "plates_rendered_sharp": not plates_blurred,
              "sub_frame_samples_tested": bool(integrate),
              "sub_frame_note": ("the shutter-integrated re-projection is compared with the motion-blurred matte of the "
                                 "blur-reference render" if integrate and not plates_blurred else
                                 ("integrated against the plates' own blurred matte" if integrate else
                                  "NOT tested by this run: the plates are sharp and no blur reference was given, so only "
                                  "the centre sample is compared")),
              "head_geometry": exman["default_head_rest"], "head_geometry_deformed": dh, "time_offsets_frames": [float(o) for o in offsets], "time_weights": [float(x) for x in weights],
              "supersampling": SS, "gate_status_of_thresholds": RT["gate"]["status"],
              "exports": {"export_manifest_sha256": hashlib.sha256((ex / "export_manifest.json").read_bytes()).hexdigest()},  # identity by hash, never by path
              "frames": [], "negative_control": RT["negative_control"]}
    all_failed, ctrl_not_failed, rot_validated, pos_discriminating = [], [], [], []
    comp_rows = {r["frame"]: r for r in bm["bundles"]["COMPOSITE_BUNDLE"]["frames"]}
    for row in bm["bundles"]["HEAD_RENDER_BUNDLE"]["frames"]:
        frame = row["frame"]
        if frame not in cam_by_frame or frame not in sock_by_frame or frame not in track_by_frame:
            raise RoundTripError(f"frame {frame} rendered but not exported")
        parts = read_parts(rd / "HEAD_RENDER_BUNDLE" / row["file"])
        ref = parts["HEAD_HOLDOUT"][0][..., 0]
        if integrate and not plates_blurred:
            if frame not in ref_frames:
                raise RoundTripError(f"frame {frame} has no blur-reference render — render the same frames with "
                                     "render_passes.py --blur-reference, or pass --ignore-subframes")
            rp = read_parts(ref_frames[frame])
            if "L_HEAD.Combined" not in rp:
                raise RoundTripError(f"{ref_frames[frame].name}: L_HEAD.Combined missing — the blur reference must "
                                     "render the head layer (conventions → render_groups.blur_reference)")
            ref = rp["L_HEAD.Combined"][0][..., 3]
        h, w = ref.shape
        px = cam_by_frame[frame]["intrinsics"]["px_by_profile"][profile]
        if [round(v * scale / 100) for v in px["resolution_px"]] != [w, h]:
            raise RoundTripError(f"frame {frame}: holdout is {w}x{h}, profile {profile} at {scale} % is {px['resolution_px']} — "
                                 f"a scale that does not give whole pixels renders one size and is re-derived as another; "
                                 f"render_passes.py refuses such a scale, so this holdout predates that check or was not made by it")
        f = scale / 100.0
        fx_fy = [v * f for v in px["focal_length_px"]]
        cx_cy = [v * f for v in px["principal_point_px"]]
        cam_s = samples_of(cam_by_frame[frame], "extrinsic_matrix_4x4")
        sock_s = samples_of(sock_by_frame[frame], "matrix_4x4")
        head = head_at(deformed[frame - first], verts, want_offsets)
        cov = coverage_for_frame(head, faces, sock_s, cam_s, fx_fy, cx_cy, w, h, offsets, weights)
        hold, classified = holdout_coverage(rd / "COMPOSITE_BUNDLE" / comp_rows[frame]["file"], classes)
        exclude = (hold >= 0.5) & (cov >= 0.5)
        excl_frac = float(exclude.sum() / max(int((cov >= 0.5).sum()), 1))
        th = thresholds_for(shot, frame, scale)
        if excl_frac > th["body_over_head_excluded_fraction_max"]:
            # A wrong export puts the head over the wall or the body: most of it would be
            # "excluded" and little measured. Beyond the bound the frame FAILS on that alone
            # (found by the plain-vs-posed negative test, 2026-09-15); below it the exclusion is
            # a recorded shot finding and the remaining silhouette is measured.
            rec = {"frame": frame, "metrics": None, "thresholds": th, "failed": ["body_over_head_excluded_fraction"], "status": "FAIL",
                   "performance_track_max_abs_channel": track_by_frame[frame],
                   "body_over_head_excluded": {"pixels": int(exclude.sum()), "fraction_of_reprojected": excl_frac, **classified},
                   "controls": "not run — the frame failed before measurement"}
            report["frames"].append(rec)
            all_failed.append(frame)
            print(f"ROUNDTRIP_FRAME {frame} FAIL body_over_head_excluded={excl_frac:.3f} > {th['body_over_head_excluded_fraction_max']} — the re-projected head lies under body or environment")
            continue
        def measure(c):
            return metrics(c, ref, exclude)
        m = measure(cov)
        failed = gate(m, th)
        cov_c = coverage_for_frame(head, faces, sock_s, cam_s, fx_fy, cx_cy, w, h, [0.0]) if integrate else None
        plate = None
        if integrate and not plates_blurred:
            # The plates' own sharp matte against the centre sample: the only comparison of the
            # stretched render's head with the exports (ADR-0002 amendment 2026-09-25).
            m_p = metrics(cov_c, parts["HEAD_HOLDOUT"][0][..., 0], (hold >= 0.5) & (cov_c >= 0.5))
            p_failed = gate(m_p, th)
            plate = {"metrics": m_p, "gate_failed": p_failed, "status": "PASS" if not p_failed else "FAIL",
                     "time_stretch": rm["settings"].get("time_stretch"),
                     "note": "the centre sample against the plates' own sharp HEAD_HOLDOUT — the plates are rendered with the time stretched "
                             "so their vectors reach the shutter's ends, and the head must still be where the exports put it"}
            failed = failed + [f"plate_centre:{k}" for k in p_failed]
        nc = RT["negative_control"]
        shifted, shift_m = perturb_translation(sock_s, cam_s, fx_fy[0], nc["translation"]["screen_shift_px"])
        m_t = measure(coverage_for_frame(head, faces, shifted, cam_s, fx_fy, cx_cy, w, h, offsets, weights))
        # Scale control: a pure size error of +growth px on the effective radius, about the
        # silhouette's own centre — fx, fy scaled and the principal point moved so the centre
        # stays put (review round 2: scaling about the principal point moved an off-axis head by
        # 12 px and only re-tested the translation control).
        r_eff = math.sqrt(max(int(((cov >= 0.5) & ~exclude).sum()), 1) / math.pi)
        focal_scale = 1.0 + nc["scale"]["screen_growth_px"] / r_eff
        ys_, xs_ = np.mgrid[0:h, 0:w]
        wsum = float(cov.sum())
        centre = (float((xs_ * cov).sum() / wsum), float((ys_ * cov).sum() / wsum))
        cx_cy_s = [centre[0] - focal_scale * (centre[0] - cx_cy[0]), centre[1] - focal_scale * (centre[1] - cx_cy[1])]
        m_s = measure(coverage_for_frame(head, faces, sock_s, cam_s, [v * focal_scale for v in fx_fy], cx_cy_s, w, h, offsets, weights))
        m_r = measure(coverage_for_frame(head, faces, perturb_rotation(sock_s, nc["rotation"]["yaw_deg"]), cam_s, fx_fy, cx_cy, w, h, offsets, weights))
        # The rest head on the same frame: what the test measured before 2026-09-17. Reported,
        # never gated — where it fails and the deformed head passes, the frame's facial
        # deformation is visible in the silhouette and the deformed geometry is what saved it.
        m_rest = measure(coverage_for_frame(verts, faces, sock_s, cam_s, fx_fy, cx_cy, w, h, offsets, weights))
        t_failed, s_failed, r_failed = gate(m_t, th), gate(m_s, th), gate(m_r, th)
        rec = {"frame": frame, "metrics": m, "thresholds": {**th, "iou_min_resolved": iou_min_of(m, th)}, "failed": failed, "status": "PASS" if not failed else "FAIL",
               "performance_track_max_abs_channel": track_by_frame[frame],
               "rest_head_comparison": {"metrics": m_rest, "gate_failed": gate(m_rest, th),
                                        "note": "the rest head re-projected on this frame, reported only: failing here while the deformed head passes means the facial deformation is visible in the silhouette"},
               "body_over_head_excluded": {"pixels": int(exclude.sum()), "fraction_of_reprojected": excl_frac, **classified},
               "controls": {"translation": {"shift_m": shift_m, "screen_shift_px": nc["translation"]["screen_shift_px"], "metrics": m_t, "gate_failed": t_failed, "status": "VALIDATED" if t_failed else "NOT_VALIDATED"},
                            "scale": {"focal_scale": focal_scale, "screen_growth_px": nc["scale"]["screen_growth_px"], "principal_point_px_used": cx_cy_s, "metrics": m_s, "gate_failed": s_failed, "status": "VALIDATED" if s_failed else "NOT_VALIDATED"},
                            "rotation": {"yaw_deg": nc["rotation"]["yaw_deg"], "metrics": m_r, "gate_failed": r_failed, "status": "VALIDATED" if r_failed else "NOT_VALIDATED"}}}
        if plate is not None:
            rec["plate_centre_sample"] = plate
            # what the reference's own sample count can resolve on this frame's blurred contour
            q = reference_quantization_px(cov, ref_samples, exclude)
            rec["reference_quantization_px"] = {"value": q, "reference_samples": ref_samples, "target_px": RT["reference_quantization"]["target_px"]}
            if {"iou", "p95_boundary_px"} & set(failed) and q > RT["reference_quantization"]["target_px"]:
                n = samples_for_quantization(q * ref_samples, ref_samples)
                rec["failure_hint"] = (f"within the blur reference's own resolution: its {ref_samples} samples place this blurred contour only to "
                                       f"~{q:.2f} px (target {RT['reference_quantization']['target_px']} px) — re-render it with >= {n} samples "
                                       "(check_asset.sh plans this with --plan-reference-samples)")
        if integrate:
            m_c = measure(cov_c)
            delta = max(abs(m_c["centroid_px"] - m["centroid_px"]), abs(m_c["mean_abs_coverage_in_band"] - m["mean_abs_coverage_in_band"]))
            disc = delta > RT["positive_control"]["min_difference"]
            rec["positive_control_centre_only"] = {"metrics": m_c, "gate_failed": gate(m_c, th), "difference": delta,
                                                   "status": "DISCRIMINATING" if disc else "NOT_DISCRIMINATING",
                                                   "note": "integrated vs centre-only; NOT_DISCRIMINATING means the head moved too little across this frame's shutter for the sub-frame data to be tested here"}
            pos_discriminating.append((frame, disc))
        report["frames"].append(rec)
        if failed:
            all_failed.append(frame)
        if not t_failed or not s_failed:
            ctrl_not_failed.append(frame)
        rot_validated.append(bool(r_failed))
        print(f"ROUNDTRIP_FRAME {frame} {rec['status']} p95={m['p95_boundary_px']:.2f}px centroid={m['centroid_px']:.3f}px iou={m['iou']:.4f} band_mean_abs={m['mean_abs_coverage_in_band']:.4f} excluded={rec['body_over_head_excluded']['fraction_of_reprojected']:.4f} rest_head={'fails' if rec['rest_head_comparison']['gate_failed'] else 'passes'}{(' plate_centre=' + plate['status']) if plate else ''} | ctrl translation={'fails' if t_failed else 'DOES NOT FAIL'} scale={'fails' if s_failed else 'DOES NOT FAIL'} rotation={'fails' if r_failed else 'does not fail'}")
    report["status"] = "PASS" if not all_failed and not ctrl_not_failed else "FAIL"
    report["failed_frames"] = all_failed
    report["control_not_failing_frames"] = ctrl_not_failed
    report["rotation_control"] = "VALIDATED" if rot_validated and all(rot_validated) else "NOT_VALIDATED — the gate did not catch a 3° yaw on every frame; on a silhouette-symmetric head this control cannot discriminate (recorded, not an export defect)"
    if integrate:
        yes = [f for f, d in pos_discriminating if d]
        no = [f for f, d in pos_discriminating if not d]
        # Per-frame truth, summarised: a static frame cannot discriminate and says so; the
        # sub-frame data is tested on the frames listed as discriminating (review 2026-09-16:
        # the all-frames form read NOT_DISCRIMINATING whenever a static first frame was rendered).
        report["positive_control"] = (f"DISCRIMINATING on frames {yes}" if yes else "NOT_DISCRIMINATING on every frame — the sub-frame data is exercised but not tested (no frame moves across the shutter)") + (f"; not on {no} (no motion across the shutter)" if yes and no else "")
    if args.ignore_subframes:
        report["mode"] = "positive control run: centre sample only"
    out = rd / f"roundtrip_report.{profile}{'.centre_only' if args.ignore_subframes else ''}.json"
    out.write_text(json.dumps(report, indent=1, allow_nan=False) + "\n")
    if not args.ignore_subframes:
        bm["roundtrip"] = {"report": out.name, "status": report["status"], "script": RT["script"], "failed_frames": all_failed, "control_not_failing_frames": ctrl_not_failed,
                           "exports": report["exports"]}
        manifests[0].write_text(json.dumps(bm, indent=1) + "\n")
    if all_failed:
        hints = [r for r in report["frames"] if r["frame"] in all_failed and r.get("failure_hint")]
        if len(hints) == len(all_failed):
            raise RoundTripError(f"round-trip FAIL on frames {all_failed} — " + "; ".join(f"{r['frame']}: {r['failure_hint']}" for r in hints))
        raise RoundTripError(f"round-trip FAIL on frames {all_failed} — the export does not place the head where the render did")
    if ctrl_not_failed:
        raise RoundTripError(f"negative control did not fail on frames {ctrl_not_failed} — the metric is NOT VALIDATED at this resolution")
    print(f"ROUNDTRIP_OK {profile} {len(report['frames'])} frames rotation_control={report['rotation_control'][:13]} positive_control={report.get('positive_control', 'n/a (still)')} -> {out}")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    try:
        main(argv)
    except (RoundTripError, MatteError, OSError, ValueError, KeyError) as e:
        print(f"ROUNDTRIP_ERROR: {e}", file=sys.stderr)
        sys.exit(2)
