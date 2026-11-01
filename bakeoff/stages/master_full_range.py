"""The master's full-range render — every video frame of the three shots into the package (owner 2026-09-29: before the
bake-off, cost first; 2026-10-30: «считаем эти часы в лимит, в лимит 220», the gates' coverage «идем по пути С»). The
plates on every frame; the gates that need a render of their own — the round-trip against the blur reference, the blur
fidelity, the skin-tone truths — on the package's picked frames (slice/pick_frames.py: the first, the fastest turn, the
widest jaw) and every 10th frame from the shot's first, the record saying so. Plain Python driving Blender, every
Blender call through bakeoff/ledger.py as `bakeoff_master_full_range`:

    python3 bakeoff/checkpoint.py --experiment benchmarks/bakeoff/01J7B000000000000000BAKEXP --stage bakeoff_master_full_range
    python3 bakeoff/stages/master_full_range.py render [--shot SHOT_001 ...] [--chunk 30]
    python3 bakeoff/stages/master_full_range.py probe [--shot ...] [--chunk 30]
    python3 bakeoff/stages/master_full_range.py gate [--shot ...]
    python3 bakeoff/stages/master_full_range.py all [--shot ...]          # render, probe, then gate, shot by shot
    python3 bakeoff/ledger.py --experiment … --stage bakeoff_master_full_range --job "… package" -- \
        python3 bakeoff/stages/master_full_range.py package [--shot ...]

render — the plates as the package's were made (slice/check_asset.sh step 5: 64 spp, 100 %, the lighting probe, the
gaze aimed at the exported point — ADR-0002 amendment 2026-09-30, which every new render follows), on the master's own
shot file from the package (its sha256 the package's render manifest's), in chunks of --chunk frames, each its own
render_passes.py call into <out>/<shot>/chunks/<first>-<last>: an interrupted run loses at most one chunk. A chunk whose
render manifest names exactly its frames and whose every file has the recorded size and sha256 is skipped; anything else
in its directory is an unfinished chunk and is rendered again.

probe — the master's skin probe (ADR-0002 amendment 2026-10-31; the owner: «поехали», 2026-10-31): a copy of the
shot file with every hero skin material at skin_tone.probe.tone (slice/skin_probe.py set-tone), its two skin layers
rendered exactly as the plates were (render_passes.py --skin-probe, no lighting probe) into <out>/<shot>/skin_probe/
chunks/<first>-<last>, resumable as the plates are.

gate — per shot, the chunks merged into one render (hard links, one render configuration checked), then
slice/check_asset.sh's chain from its step 6: split, composite (derived parts, precomp reproduction, the post-composite
blur), the blur reference's plan, the skin probe's chunks merged and SKIN_PROBE_BUNDLE derived (slice/skin_probe.py),
the blur reference's render, the round-trip, the blur fidelity, and the skin-tone gate — the last four on the gated
frames (`--frames`); the package's picked frames must be pick_frames.py's on these exports. A skin-tone gate measured
before the probe (the first-order re-tint) is moved aside and measured again; a SKIN_PROBE_BUNDLE derived by an older rule
(before the edge, 2026-11-01) is derived again from the same renders and its gate run again. Writes
<out>/<shot>/full_range_gates.json.

package — the package's new version: each shot's video bundle and its gate records replaced (the heavy files APFS-cloned
into the offline part), the exports, the still, the scene checks, the source and order_qc (the default head's order
composites on the earlier bundle's frames: a measurement of t_comp, recorded as such) kept; hashed and verified."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bakeoff.stages import run as rn  # noqa: E402
from slice.skin_probe import derived_by_current_rule  # noqa: E402

STAGE = "bakeoff_master_full_range"
OUT = Path("<the archive disk>/runs/master_full_range_2026-10-30")
CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
PROBE = CONV["skin_tone"]["probe"]
SAMPLES, SCALE, EVERY = 64, 100, 10


class FullRangeError(RuntimeError):
    pass


def chunks(start, end, size):
    if size < 1:
        raise FullRangeError(f"chunk size {size}")
    return [(a, min(a + size - 1, end)) for a in range(start, end + 1, size)]


def gated_frames(picked, start, end, every=EVERY):
    """The frames the gates with a render of their own measure: the package's picked frames and every `every`th from the
    shot's first (owner 2026-10-30, option (c))."""
    bad = [f for f in picked if not start <= f <= end]
    if bad:
        raise FullRangeError(f"picked frames {bad} lie outside the shot {start}-{end}")
    return sorted(set(picked) | set(range(start, end + 1, every)))


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def chunk_verified(d, frames, profile="video"):
    """True when <d>/<profile>/render_manifest.<profile>.json names exactly `frames` and every file it lists is there with
    its recorded size and sha256. render_passes.py writes the manifest after the last frame, so an interrupted chunk has none."""
    mp = Path(d) / profile / f"render_manifest.{profile}.json"
    if not mp.exists():
        return False
    m = json.loads(mp.read_text())
    if [r["frame"] for r in m["frames"]] != list(frames):
        return False
    for r in m["frames"]:
        for rec in r["files"].values():
            p = mp.parent / "raw" / rec["file"]
            if not p.exists() or p.stat().st_size != rec["bytes"] or sha256(p) != rec["sha256"]:
                return False
    return True


def merge_chunks(chunk_dirs, dst, profile="video", lighting_probe=True):
    """One render of the shot from its chunks, as slice/split_bundles.py reads a render: <dst>/<profile>/
    render_manifest.<profile>.json with every chunk's frames in order and raw/ hard links to the chunks' files (one volume:
    nothing is copied, the chunks stay as rendered). Every field but the frames and the probe must be the same in every
    chunk — one render configuration — exactly one chunk carries the lighting probe (none, for the skin probe's chunks:
    lighting_probe=False), and the frames run on without a gap or a repeat. The manifest lists the chunks it was assembled
    from."""
    out = Path(dst) / profile
    if out.exists():
        raise FullRangeError(f"{out} exists — the merge is done once, before the bundles are split into it")
    mans = [(Path(d), json.loads((Path(d) / profile / f"render_manifest.{profile}.json").read_text())) for d in chunk_dirs]
    same = lambda m: {k: v for k, v in m.items() if k not in ("frames", "probe")}  # noqa: E731
    for d, m in mans[1:]:
        diff = sorted(k for k in set(same(m)) | set(same(mans[0][1])) if same(m).get(k) != same(mans[0][1]).get(k))
        if diff:
            raise FullRangeError(f"{d.name} differs from {mans[0][0].name} in {diff} — not one render configuration")
    probes = [(d, m["probe"]) for d, m in mans if m.get("probe")]
    if lighting_probe and len(probes) != 1:
        raise FullRangeError(f"{len(probes)} chunks carry the lighting probe — exactly one must (the shot's first)")
    if not lighting_probe and probes:
        raise FullRangeError(f"{probes[0][0].name} carries a lighting probe — the skin probe's chunks render none")
    frames = [r["frame"] for _, m in mans for r in m["frames"]]
    if frames != list(range(frames[0], frames[0] + len(frames))):
        raise FullRangeError(f"the chunks' frames {frames[0]}-{frames[-1]} have a gap or a repeat")
    (out / "raw").mkdir(parents=True)
    links = [(d / profile / "raw" / rec["file"]) for d, m in mans for r in m["frames"] for rec in r["files"].values()]
    if lighting_probe:
        links.append(probes[0][0] / profile / "raw" / probes[0][1]["file"])
    for src in links:
        os.link(src, out / "raw" / src.name)
    merged = dict(mans[0][1], frames=[r for _, m in mans for r in m["frames"]], probe=probes[0][1] if lighting_probe else None,
                  assembled_from_chunks=[{"chunk": d.name, "frames": [m["frames"][0]["frame"], m["frames"][-1]["frame"]],
                                          "render_manifest_sha256": sha256(d / profile / f"render_manifest.{profile}.json")}
                                         for d, m in mans])
    (out / f"render_manifest.{profile}.json").write_text(json.dumps(merged, indent=1) + "\n")
    return merged


REPLACED = ("renders/video", "qc/blur_reference", "qc/blur_fidelity", "qc/skin_tone", "qc/full_range_gates.json")


def is_light(p):
    """slice/package_add_shot.py's split, except that the manifests a package's shot entry is derived from stay light
    whatever their size (slice/package.py reads them from the light part; 120 frames' bundle manifest is ≈ 2 MB)."""
    from slice.package_add_shot import is_light as light
    return light(p) or (p.suffix == ".json" and p.name.startswith(("bundle_manifest.", "render_manifest.")))


def place(src, dst_light, dst_off, counts):
    """A light file copied into the package, a heavy one CLONED into its offline part (APFS: no second copy of ≈ 100 GB a
    shot). macOS `cp -c` copies silently across volumes, so the two must be one volume; the clone is read back."""
    if is_light(src):
        dst = dst_light
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        counts["light"] += 1
    else:
        dst = dst_off
        dst.parent.mkdir(parents=True, exist_ok=True)
        if os.stat(src).st_dev != os.stat(dst.parent).st_dev:
            raise FullRangeError(f"{src} and the offline package are on different volumes: a clone would be a copy")
        subprocess.run(["cp", "-c", str(src), str(dst)], check=True)
        counts["offline"] += 1
    if sha256(dst) != sha256(src):
        raise FullRangeError(f"{dst} differs from its source {src}")


def replace_video(pkg, off, shot, run, summary, retire):
    """A new version of one shot in the package: its video bundle and the gates measured on it (the blur reference and
    fidelity, the skin-tone records — its truth renders stay in the run) replaced by the full-range run's, and the run's
    gate summary added; the exports, the still, the scene checks, the source and order_qc are kept as they are. The earlier
    version's offline files are moved under `retire` (same relative paths; one volume, a rename), never deleted — its light
    part is in git."""
    pkg, off, run, retire = Path(pkg), Path(off), Path(run), Path(retire)
    rel = Path("shots") / shot
    for r in REPLACED:
        p = off / rel / r
        if p.exists():
            dst = retire / rel / r
            if dst.exists():
                raise FullRangeError(f"{dst} exists — this version was retired before")
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.rename(p, dst)
        p = pkg / rel / r
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    counts = {"light": 0, "offline": 0}
    for src_dir, dst_rel in ((run / "renders" / "video", "renders/video"), (run / "blur_reference", "qc/blur_reference"),
                             (run / "blur_fidelity", "qc/blur_fidelity")):
        for p in sorted(src_dir.rglob("*")):
            if p.is_file() and p.name not in (".DS_Store", "last_step.log"):
                r = rel / dst_rel / p.relative_to(src_dir)
                place(p, pkg / r, off / r, counts)
    for name in ("check_skin_tone.json", "compare.json"):
        place(run / "skin_tone" / name, pkg / rel / "qc/skin_tone" / name, off / rel / "qc/skin_tone" / name, counts)
    place(Path(summary), pkg / rel / "qc/full_range_gates.json", off / rel / "qc/full_range_gates.json", counts)
    return counts


def env():
    # as slice/check_asset.sh renders the package's plates
    return dict(rn.env(), CYCLES_METAL_DISABLE_BINARY_ARCHIVES="1")


def book(cmd, log, job):
    """One Blender call through the ledger; a non-zero exit stops the run (the ledger books it either way)."""
    cmd = [sys.executable, str(ROOT / "bakeoff" / "ledger.py"), "--experiment", str(rn.EXP), "--stage", STAGE, "--job", job, "--"] + [str(c) for c in cmd]
    t0 = time.time()
    with open(log, "w") as fh:
        rc = subprocess.call(cmd, stdout=fh, stderr=subprocess.STDOUT, env=env(), cwd=str(ROOT))
    if rc != 0:
        tail = Path(log).read_text().strip().splitlines()[-3:]
        raise FullRangeError(f"{Path(log).name}: exit {rc} — {' | '.join(tail)}")
    return round(time.time() - t0, 2)


def exports_view(shot, out):
    """The package's exports for one shot as one tree (light part + offline part), symlinked."""
    from slice.rebuild_from_package import view as make_view
    dst = out / shot / "exports"
    if not dst.exists():
        make_view(rn.LIGHT, rn.OFF, f"shots/{shot}/exports", dst)
    return dst


def package_render_manifest(shot):
    return json.loads((rn.LIGHT / "shots" / shot / "renders" / "video" / "render_manifest.video.json").read_text())


def render(shots, size, out):
    for shot in shots:
        fr = CONV["shots"][shot]["frame_range"]
        blend = rn.master_file(shot)
        want = package_render_manifest(shot)["source_scene"]["sha256"]
        if rn.sha256(blend) != want:
            raise FullRangeError(f"{blend.name}: not the shot file the package's plates were rendered from ({want[:12]})")
        exports = exports_view(shot, out)
        for a, b in chunks(fr["start"], fr["end"], size):
            d = out / shot / "chunks" / f"{a}-{b}"
            frames = list(range(a, b + 1))
            if chunk_verified(d, frames):
                print(f"CHUNK_DONE {shot} {a}-{b} (verified, skipped)", flush=True)
                continue
            if d.exists():
                if out.resolve() not in d.resolve().parents:
                    raise FullRangeError(f"{d} is not under {out}")
                shutil.rmtree(d)   # an unfinished chunk: its frames are rendered again
            d.mkdir(parents=True)
            cmd = [rn.BLENDER, "-b", blend, "--python-exit-code", "2", "-P", ROOT / "slice" / "render_passes.py", "--",
                   "--shot", shot, "--profile", "video", "--frames", f"{a}-{b}", "--samples", SAMPLES, "--scale", SCALE,
                   "--exports", exports, "--out", d] + (["--probe"] if a == fr["start"] else [])
            s = book(cmd, d / "render.log", f"{STAGE} {shot} plates {a}-{b}")
            if not chunk_verified(d, frames):
                raise FullRangeError(f"{shot} {a}-{b}: rendered, but its manifest or files do not verify")
            print(f"CHUNK_OK {shot} {a}-{b} {s:.0f}s", flush=True)
    print("FULL_RANGE_RENDER_OK " + " ".join(shots), flush=True)


def probe(shots, size, out):
    """The master's skin probe per shot: the probe's shot file once, then its two skin layers in chunks, as render()."""
    for shot in shots:
        fr = CONV["shots"][shot]["frame_range"]
        blend = rn.master_file(shot)
        want = package_render_manifest(shot)["source_scene"]["sha256"]
        if rn.sha256(blend) != want:
            raise FullRangeError(f"{blend.name}: not the shot file the package's plates were rendered from ({want[:12]})")
        exports = exports_view(shot, out)
        sd, pd = out / shot, out / shot / "skin_probe"
        pblend = pd / f"{shot}_skin_probe.blend"
        steps = rn.Steps(sd)
        if not steps.done("probe_tone"):
            pd.mkdir(parents=True, exist_ok=True)
            tone = ",".join(str(v) for v in PROBE["tone"])
            s = book([rn.BLENDER, "-b", blend, "--python-exit-code", "2", "-P", ROOT / "slice" / "skin_probe.py", "--", "set-tone", "--tone", tone,
                      "--out", pblend], pd / "set_tone.log", f"{STAGE} {shot} skin probe tone")
            steps.mark("probe_tone", s, [pblend], tone=PROBE["tone"], master_sha256=want)
        for a, b in chunks(fr["start"], fr["end"], size):
            d = pd / "chunks" / f"{a}-{b}"
            frames = list(range(a, b + 1))
            if chunk_verified(d, frames):
                print(f"PROBE_CHUNK_DONE {shot} {a}-{b} (verified, skipped)", flush=True)
                continue
            if d.exists():
                if out.resolve() not in d.resolve().parents:
                    raise FullRangeError(f"{d} is not under {out}")
                shutil.rmtree(d)   # an unfinished chunk: its frames are rendered again
            d.mkdir(parents=True)
            cmd = [rn.BLENDER, "-b", pblend, "--python-exit-code", "2", "-P", ROOT / "slice" / "render_passes.py", "--",
                   "--shot", shot, "--profile", "video", "--frames", f"{a}-{b}", "--samples", SAMPLES, "--scale", SCALE,
                   "--exports", exports, "--skin-probe", "--out", d]
            s = book(cmd, d / "render.log", f"{STAGE} {shot} skin probe {a}-{b}")
            if not chunk_verified(d, frames):
                raise FullRangeError(f"{shot} skin probe {a}-{b}: rendered, but its manifest or files do not verify")
            print(f"PROBE_CHUNK_OK {shot} {a}-{b} {s:.0f}s", flush=True)
    print("FULL_RANGE_PROBE_OK " + " ".join(shots), flush=True)


def retire_first_order_gate(sd, steps):
    """A skin-tone gate measured on the first-order re-tint, passed or failed (before ADR-0002 amendment 2026-10-31), is
    moved aside — <run>/skin_tone.first_order, the shot's summary full_range_gates.first_order.json — never deleted; its
    step is to run again. True when one was moved."""
    sd = Path(sd)
    old, chk = sd / "run" / "skin_tone", sd / "run" / "skin_tone" / "check_skin_tone.json"
    if not old.exists() or (chk.exists() and json.loads(chk.read_text()).get("method") == "probe"):
        return False
    for src, dst in ((old, sd / "run" / "skin_tone.first_order"), (sd / "full_range_gates.json", sd / "full_range_gates.first_order.json")):
        if src.exists():
            if dst.exists():
                raise FullRangeError(f"{dst} exists — a first-order gate was moved aside before")
            os.rename(src, dst)
    steps.unmark("skin_tone")
    return True


def retire_older_probe(rv, steps):
    """A SKIN_PROBE_BUNDLE derived by an older rule (slice/skin_probe.derived_by_current_rule — before the edge, owner
    2026-11-01) is derived again from the same renders and the skin-tone gate measured on it is run again: both steps
    are no longer DONE; the bundle stays in place until derive --replace puts the new one there whole. True when so."""
    bp = Path(rv) / "bundle_manifest.video.json"
    if not steps.done("skin_probe") or not bp.exists() or derived_by_current_rule(json.loads(bp.read_text())):
        return False
    steps.unmark("skin_probe")
    steps.unmark("skin_tone")
    return True


def gates_not_passed(summary):
    """The gates of one shot's summary that bar it from the package: {gate: status}; the skin-tone gate counts only when
    measured between the master and its probe (ADR-0002 amendment 2026-10-31)."""
    bad = {k: summary[k]["status"] for k, ok in (("roundtrip", ("PASS",)), ("skin_tone", ("PASS", "VACUOUS")), ("blur_fidelity", ("PASS",)))
           if summary[k]["status"] not in ok}
    if "skin_tone" not in bad and summary["skin_tone"].get("method") != "probe":
        bad["skin_tone"] = f"{summary['skin_tone']['status']} (first order)"
    return bad


def blender(*args):
    return [rn.BLENDER, "-b", "--python-exit-code", "2", "-P", *args]


def gate(shots, size, out):
    """Per shot, after its chunks: the chain slice/check_asset.sh runs from its step 6 on, the gates with a render of their
    own on the gated frames (owner 2026-10-30, option (c)). Steps recorded in <out>/<shot>/steps.json, skipped when done."""
    from slice.pick_frames import pick
    for shot in shots:
        fr = CONV["shots"][shot]["frame_range"]
        sd = out / shot
        run = sd / "run"
        steps = rn.Steps(sd)
        blend, exports = rn.master_file(shot), sd / "exports"
        parts = chunks(fr["start"], fr["end"], size)
        for a, b in parts:
            if not chunk_verified(sd / "chunks" / f"{a}-{b}", list(range(a, b + 1))):
                raise FullRangeError(f"{shot} {a}-{b}: the chunk is not rendered and verified — run render first")
            if not chunk_verified(sd / "skin_probe" / "chunks" / f"{a}-{b}", list(range(a, b + 1))):
                raise FullRangeError(f"{shot} {a}-{b}: the skin probe's chunk is not rendered and verified — run probe first")
        if retire_first_order_gate(sd, steps):
            print(f"FIRST_ORDER_GATE_MOVED_ASIDE {shot}: run/skin_tone.first_order — measured again with the probe", flush=True)
        rv = run / "renders" / "video"
        if not steps.done("merge"):
            run.mkdir(parents=True, exist_ok=True)
            if not (run / "exports").exists():
                (run / "exports").symlink_to(exports.resolve(), target_is_directory=True)
            merge_chunks([sd / "chunks" / f"{a}-{b}" for a, b in parts], run / "renders")
            steps.mark("merge", 0.0, [rv / "render_manifest.video.json"])
        picked = pick(exports)
        package_frames = sorted(r["frame"] for r in package_render_manifest(shot)["frames"])
        if picked != package_frames:
            raise FullRangeError(f"{shot}: pick_frames gives {picked}, the package holds {package_frames}")
        g = gated_frames(picked, fr["start"], fr["end"])
        gs = ",".join(map(str, g))
        job = f"{STAGE} {shot}"
        chain = [
            ("split", blender(ROOT / "slice/split_bundles.py", "--", rv, "--exports", run / "exports")),
            ("composite", blender(ROOT / "slice/composite.py", "--", rv)),
            ("plan", blender(ROOT / "slice/roundtrip.py", "--", "--exports", run / "exports", "--renders", rv, "--plan-reference-samples",
                             "--min-samples", SAMPLES, "--frames", gs)),
        ]
        for name, cmd in chain:
            if not steps.done(name):
                s = book(cmd, sd / f"{name}.log", f"{job} {name}")
                steps.mark(name, s, [sd / f"{name}.log"])
        if not steps.done("probe_merge"):
            merge_chunks([sd / "skin_probe" / "chunks" / f"{a}-{b}" for a, b in parts], run / "probe_renders", lighting_probe=False)
            steps.mark("probe_merge", 0.0, [run / "probe_renders" / "video" / "render_manifest.video.json"])
        if retire_older_probe(rv, steps):
            for name in ("skin_probe.log", "skin_tone.log"):
                if (sd / name).exists():                     # the older rule's logs kept beside, never overwritten
                    os.replace(sd / name, sd / name.replace(".", ".older_rule.", 1))
            print(f"SKIN_PROBE_OLDER_RULE {shot}: {PROBE['bundle']} derived again, its gate run again", flush=True)
        if not steps.done("skin_probe"):
            again = ["--replace"] if (rv / PROBE["bundle"]).exists() else []    # an older rule's, or a derive that died before its mark
            s = book(blender(ROOT / "slice/skin_probe.py", "--", "derive", rv, run / "probe_renders" / "video", *again), sd / "skin_probe.log", f"{job} skin_probe")
            steps.mark("skin_probe", s, [sd / "skin_probe.log", rv / PROBE["bundle"]])
        ref_samples = json.loads((rv / "reference_plan.video.json").read_text())["samples"]
        chain = [
            ("blur_reference", [rn.BLENDER, "-b", blend, "--python-exit-code", "2", "-P", ROOT / "slice/render_passes.py", "--", "--shot", shot,
                                "--exports", run / "exports", "--profile", "video", "--frames", gs, "--samples", ref_samples, "--scale", SCALE,
                                "--blur-reference", "--out", run / "blur_reference"]),
            ("roundtrip", blender(ROOT / "slice/roundtrip.py", "--", "--exports", run / "exports", "--renders", rv,
                                  "--blur-reference", run / "blur_reference" / "video", "--frames", gs)),
            ("blur_fidelity", blender(ROOT / "slice/check_blur_fidelity.py", "--", "--renders", rv, "--reference", run / "blur_reference" / "video",
                                      "--out", run / "blur_fidelity")),
            ("skin_tone", [sys.executable, ROOT / "slice/check_skin_tone.py", "--blend", blend, "--shot", shot, "--renders", run / "renders",
                           "--out", run / "skin_tone", "--frames", gs, "--profiles", "video"]
                          # measured before and not judged (the owner's p99 bound was not set): judged again, not rendered again
                          + (["--recompare"] if any((run / "skin_tone" / n).exists() for n in ("compare.json", "compare.older_rule.json")) else [])),
        ]
        for name, cmd in chain:
            if not steps.done(name):
                s = book(cmd, sd / f"{name}.log", f"{job} {name}" + (f" ({ref_samples} spp)" if name == "blur_reference" else ""))
                steps.mark(name, s, [sd / f"{name}.log"])
        bm = json.loads((rv / "bundle_manifest.video.json").read_text())
        fid = json.loads((run / "blur_fidelity" / "blur_fidelity_report.json").read_text())
        summary = {"shot": shot, "frames": [fr["start"], fr["end"]], "gated_frames": g, "picked_frames": picked,
                   "rule": "the plates on every frame; the round-trip against the blur reference, the blur fidelity and the skin-tone "
                           "truths on the package's picked frames (slice/pick_frames.py) and every 10th frame from the shot's first — "
                           "owner 2026-10-30: «идем по пути С»",
                   "blur_reference_samples": ref_samples, "roundtrip": bm["roundtrip"], "skin_tone": bm["skin_tone"],
                   "blur_fidelity": {k: fid.get(k) for k in ("status", "frames")}, "steps_seconds": {k: v["seconds"] for k, v in steps.rec.items()}}
        (sd / "full_range_gates.json").write_text(json.dumps(summary, indent=1) + "\n")
        print(f"FULL_RANGE_GATES_OK {shot}: round-trip {bm['roundtrip']['status']} on {len(g)} of {fr['end'] - fr['start'] + 1} frames, "
              f"skin tone {bm['skin_tone']['status']}, blur fidelity {fid.get('status')}", flush=True)


def package(shots, out):
    """The package's new version: per shot, only when its three gates passed, the video bundle and its gate records
    replaced (replace_video); then the package hashed and verified with its offline part (slice/package.py). Run it
    under bakeoff/ledger.py: it reads every file of the new bundles twice (the clone's check, the hash)."""
    previous = json.loads((rn.LIGHT / "package_manifest.json").read_text())["package_hash"]
    retire = rn.OFF.parent / "versions" / previous[:12]
    for shot in shots:
        sd = out / shot
        summ = sd / "full_range_gates.json"
        if not summ.exists():
            raise FullRangeError(f"{shot}: no full_range_gates.json — run gate first")
        g = json.loads(summ.read_text())
        bad = gates_not_passed(g)
        if bad:
            raise FullRangeError(f"{shot}: gates {bad} — not packaged")
        counts = replace_video(rn.LIGHT, rn.OFF, shot, sd / "run", summ, retire)
        print(f"VIDEO_REPLACED {shot}: {counts['light']} light files, {counts['offline']} offline (cloned)", flush=True)
    for cmd in ("hash", "verify"):
        r = subprocess.run([sys.executable, str(ROOT / "slice" / "package.py"), cmd, str(rn.LIGHT), "--offline", str(rn.OFF)],
                           capture_output=True, text=True)
        print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "", flush=True)
        if r.returncode != 0:
            raise FullRangeError(f"package.py {cmd}: exit {r.returncode} — {r.stderr.strip()[-500:]}")
    print("FULL_RANGE_PACKAGED " + " ".join(shots), flush=True)


def main(argv):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--shot", action="append", choices=sorted(CONV["shots"]))
    r.add_argument("--chunk", type=int, default=30)
    r.add_argument("--out", default=str(OUT))
    g = sub.add_parser("gate")
    g.add_argument("--shot", action="append", choices=sorted(CONV["shots"]))
    g.add_argument("--chunk", type=int, default=30)
    g.add_argument("--out", default=str(OUT))
    pr = sub.add_parser("probe")
    pr.add_argument("--shot", action="append", choices=sorted(CONV["shots"]))
    pr.add_argument("--chunk", type=int, default=30)
    pr.add_argument("--out", default=str(OUT))
    al = sub.add_parser("all", help="render, probe, then gate, shot by shot: a fault in the chain shows after one shot, not three")
    al.add_argument("--shot", action="append", choices=sorted(CONV["shots"]))
    al.add_argument("--chunk", type=int, default=30)
    al.add_argument("--out", default=str(OUT))
    k = sub.add_parser("package")
    k.add_argument("--shot", action="append", choices=sorted(CONV["shots"]))
    k.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    if a.cmd == "render":
        render(a.shot or sorted(CONV["shots"]), a.chunk, Path(a.out))
    elif a.cmd == "probe":
        probe(a.shot or sorted(CONV["shots"]), a.chunk, Path(a.out))
    elif a.cmd == "gate":
        gate(a.shot or sorted(CONV["shots"]), a.chunk, Path(a.out))
    elif a.cmd == "all":
        for shot in a.shot or sorted(CONV["shots"]):
            render([shot], a.chunk, Path(a.out))
            probe([shot], a.chunk, Path(a.out))
            gate([shot], a.chunk, Path(a.out))
    else:
        package(a.shot or sorted(CONV["shots"]), Path(a.out))


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (FullRangeError, rn.RunError, OSError) as e:
        print(f"FULL_RANGE_ERROR {e}", file=sys.stderr)
        sys.exit(2)
