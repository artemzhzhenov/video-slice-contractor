"""The master's full-range render (owner 2026-10-30: its hours in the 220, the gates' coverage (c)): the chunks it is
rendered in, the frames its gates measure, and the check that lets a finished chunk be skipped on a resume."""
import hashlib
import json

import pytest

from bakeoff.stages import master_full_range as mf


def test_a_shot_is_cut_into_contiguous_chunks_that_cover_it_once():
    assert mf.chunks(1001, 1120, 30) == [(1001, 1030), (1031, 1060), (1061, 1090), (1091, 1120)]
    assert mf.chunks(1001, 1065, 30) == [(1001, 1030), (1031, 1060), (1061, 1065)]
    with pytest.raises(mf.FullRangeError):
        mf.chunks(1001, 1120, 0)


def test_the_gated_frames_are_the_packages_picked_frames_and_every_tenth_from_the_first():
    got = mf.gated_frames([1001, 1094, 1101], 1001, 1120, 10)
    assert got == [1001, 1011, 1021, 1031, 1041, 1051, 1061, 1071, 1081, 1091, 1094, 1101, 1111]
    assert got == sorted(set(got))


def test_a_picked_frame_outside_the_shot_is_refused():
    with pytest.raises(mf.FullRangeError):
        mf.gated_frames([1001, 1121], 1001, 1120, 10)


def make_chunk(d, frames, groups=("beauty", "data")):
    raw = d / "video" / "raw"
    raw.mkdir(parents=True)
    rows = []
    for f in frames:
        row = {"frame": f, "files": {}, "seconds": {g: 1.0 for g in groups}}
        for g in groups:
            p = raw / f"{g}.{f:04d}.exr"
            p.write_bytes(f"{g}{f}".encode())
            row["files"][g] = {"file": p.name, "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        rows.append(row)
    (d / "video" / "render_manifest.video.json").write_text(json.dumps({"shot_id": "SHOT_001", "profile": "video", "frames": rows}))
    return raw


def test_a_chunk_is_done_only_when_its_manifest_names_exactly_its_frames_and_every_file_matches(tmp_path):
    d = tmp_path / "1001-1003"
    raw = make_chunk(d, [1001, 1002, 1003])
    assert mf.chunk_verified(d, [1001, 1002, 1003])
    assert not mf.chunk_verified(d, [1001, 1002, 1003, 1004])        # another range
    (raw / "data.1002.exr").write_bytes(b"data1002-changed")            # a file that is not the one rendered
    assert not mf.chunk_verified(d, [1001, 1002, 1003])
    (raw / "data.1002.exr").unlink()
    assert not mf.chunk_verified(d, [1001, 1002, 1003])


def test_an_interrupted_chunk_has_no_manifest_and_is_not_done(tmp_path):
    d = tmp_path / "1001-1003"
    make_chunk(d, [1001, 1002, 1003])
    (d / "video" / "render_manifest.video.json").unlink()   # render_passes writes it last
    assert not mf.chunk_verified(d, [1001, 1002, 1003])
    assert not mf.chunk_verified(tmp_path / "missing", [1001])


def chunk_with(d, frames, probe=False, samples=64):
    make_chunk(d, frames)
    mp = d / "video" / "render_manifest.video.json"
    m = json.loads(mp.read_text())
    m.update({"settings": {"samples": samples, "resolution_percentage": 100}, "device": "METAL", "source_scene": {"sha256": "aa"}, "probe": None})
    if probe:
        p = d / "video" / "raw" / f"lighting_probe.{frames[0]:04d}.exr"
        p.write_bytes(b"probe")
        m["probe"] = {"frame": frames[0], "file": p.name, "bytes": 5, "sha256": hashlib.sha256(b"probe").hexdigest()}
    mp.write_text(json.dumps(m))
    return d


def test_the_chunks_merge_into_one_render_of_the_shot_by_hard_links(tmp_path):
    a = chunk_with(tmp_path / "c" / "1001-1002", [1001, 1002], probe=True)
    b = chunk_with(tmp_path / "c" / "1003-1004", [1003, 1004])
    dst = tmp_path / "renders"
    m = mf.merge_chunks([a, b], dst)
    assert [r["frame"] for r in m["frames"]] == [1001, 1002, 1003, 1004]
    assert m["probe"]["frame"] == 1001 and [c["frames"] for c in m["assembled_from_chunks"]] == [[1001, 1002], [1003, 1004]]
    assert json.loads((dst / "video" / "render_manifest.video.json").read_text()) == m
    for name in ("beauty.1003.exr", "lighting_probe.1001.exr"):
        src = (b if "1003" in name else a) / "video" / "raw" / name
        assert (dst / "video" / "raw" / name).stat().st_ino == src.stat().st_ino   # the same file, not a copy
    assert mf.chunk_verified(dst, [1001, 1002, 1003, 1004])


def test_chunks_that_differ_in_anything_but_their_frames_do_not_merge(tmp_path):
    a = chunk_with(tmp_path / "c" / "1001-1002", [1001, 1002], probe=True)
    b = chunk_with(tmp_path / "c" / "1003-1004", [1003, 1004], samples=16)
    with pytest.raises(mf.FullRangeError, match="settings"):
        mf.merge_chunks([a, b], tmp_path / "r1")


def test_a_gap_a_second_probe_or_no_probe_does_not_merge(tmp_path):
    a = chunk_with(tmp_path / "c" / "1001-1002", [1001, 1002], probe=True)
    gap = chunk_with(tmp_path / "c" / "1004-1005", [1004, 1005])
    with pytest.raises(mf.FullRangeError, match="gap"):
        mf.merge_chunks([a, gap], tmp_path / "r1")
    two = chunk_with(tmp_path / "c" / "1003-1004", [1003, 1004], probe=True)
    with pytest.raises(mf.FullRangeError, match="probe"):
        mf.merge_chunks([a, two], tmp_path / "r2")
    none = chunk_with(tmp_path / "c2" / "1001-1002", [1001, 1002])
    with pytest.raises(mf.FullRangeError, match="probe"):
        mf.merge_chunks([none], tmp_path / "r3")


def test_skin_probe_chunks_merge_without_a_lighting_probe_and_refuse_one(tmp_path):
    a = chunk_with(tmp_path / "c" / "1001-1002", [1001, 1002])
    b = chunk_with(tmp_path / "c" / "1003-1004", [1003, 1004])
    m = mf.merge_chunks([a, b], tmp_path / "probe_renders", lighting_probe=False)
    assert m["probe"] is None and [r["frame"] for r in m["frames"]] == [1001, 1002, 1003, 1004]
    lit = chunk_with(tmp_path / "c2" / "1001-1002", [1001, 1002], probe=True)
    with pytest.raises(mf.FullRangeError, match="lighting probe"):
        mf.merge_chunks([lit, b], tmp_path / "r2", lighting_probe=False)


def test_a_skin_tone_gate_of_the_first_order_is_kept_aside_and_judged_again(tmp_path):
    """ADR-0002 amendment 2026-10-31: a gate measured on the first-order re-tint — passed or failed — is renamed, never
    deleted, and its step and the shot's gate summary are no longer DONE; a gate of the probe method is left alone."""
    from bakeoff.stages import run as rn
    sd = tmp_path / "SHOT_002"
    write(sd / "run/skin_tone/check_skin_tone.json", json.dumps({"status": "PASS"}).encode())
    write(sd / "run/skin_tone/master/renders/video/raw/beauty.1121.exr", b"truth")
    write(sd / "full_range_gates.json", json.dumps({"skin_tone": {"status": "PASS"}}).encode())
    steps = rn.Steps(sd)
    steps.mark("skin_tone", 1.0, [sd / "run/skin_tone/check_skin_tone.json"])
    assert mf.retire_first_order_gate(sd, steps) is True
    assert not (sd / "run/skin_tone").exists() and (sd / "run/skin_tone.first_order/master/renders/video/raw/beauty.1121.exr").exists()
    assert not (sd / "full_range_gates.json").exists() and (sd / "full_range_gates.first_order.json").exists()
    assert not steps.done("skin_tone") and "skin_tone" not in rn.Steps(sd).rec
    write(sd / "run/skin_tone/check_skin_tone.json", json.dumps({"status": "PASS", "method": "probe"}).encode())
    assert mf.retire_first_order_gate(sd, rn.Steps(sd)) is False and (sd / "run/skin_tone").exists()
    assert mf.retire_first_order_gate(tmp_path / "SHOT_001", rn.Steps(tmp_path / "SHOT_001")) is False   # nothing measured yet


def test_a_skin_probe_derived_by_an_older_rule_is_derived_again_and_its_gate_judged_again(tmp_path):
    """The edge (owner 2026-11-01, decision 13 (A)): a SKIN_PROBE_BUNDLE derived before it — other parts — is derived again
    from the same renders, and the gate measured on it is run again; one derived by the rule now is left alone."""
    from bakeoff.stages import run as rn
    from slice import skin_probe as spb
    sd = tmp_path / "SHOT_001"
    rv = sd / "run/renders/video"
    old = {"bundles": {spb.P["bundle"]: {"frames": [{"frame": 1001, "parts": [{"name": n} for n in ("REST_BACK", "BOUNCE_BACK", "REST_FRONT", "BOUNCE_FRONT")]}],
                                         "probe": {}}}}
    write(rv / "bundle_manifest.video.json", json.dumps(old).encode())
    write(rv / "SKIN_PROBE_BUNDLE/skin_probe.1001.exr", b"P")
    steps = rn.Steps(sd)
    steps.mark("skin_probe", 1.0, [rv / "SKIN_PROBE_BUNDLE"])
    steps.mark("skin_tone", 1.0, [sd / "skin_tone.log"])
    write(sd / "skin_tone.log", b"")
    assert mf.retire_older_probe(rv, steps) is True
    assert not steps.done("skin_probe") and not steps.done("skin_tone")
    assert (rv / "SKIN_PROBE_BUNDLE/skin_probe.1001.exr").exists(), "derive --replace puts the new bundle in place whole"
    now = {"bundles": {spb.P["bundle"]: {"frames": [{"frame": 1001, "parts": [{"name": n} for n in spb.P["parts"]]}],
                                         "probe": {"edge": spb.P["edge"], "albedo": list(spb.P["tone"])}}}}
    write(rv / "bundle_manifest.video.json", json.dumps(now).encode())
    steps.mark("skin_probe", 1.0, [rv / "SKIN_PROBE_BUNDLE"])
    assert mf.retire_older_probe(rv, steps) is False and steps.done("skin_probe")
    assert mf.retire_older_probe(tmp_path / "SHOT_002/run/renders/video", rn.Steps(tmp_path / "SHOT_002")) is False   # nothing derived yet


def test_a_still_is_rendered_again_only_when_its_shot_file_or_gaze_aim_is_not_the_full_range_videos():
    """The stills (owner «поехали» 2026-11-01): the still's probe is rendered now, as the full-range video was; a still
    from another shot file or without the video's gaze aim (SHOT_001 and SHOT_003's, rendered before the gaze amendment)
    would not pair with it — skin_probe.py derive refuses other settings."""
    gaze = {"mode": "TARGET_POINT", "track_sha256": "ab"}
    video = {"source_scene": {"sha256": "s1"}, "settings": {"gaze_aim": gaze, "samples": 64}}
    assert mf.still_render_reason({"source_scene": {"sha256": "s1"}, "settings": {"gaze_aim": dict(gaze), "samples": 256}}, video) is None
    assert "gaze" in mf.still_render_reason({"source_scene": {"sha256": "s1"}, "settings": {"samples": 256}}, video)
    assert "shot file" in mf.still_render_reason({"source_scene": {"sha256": "s0"}, "settings": {"gaze_aim": gaze}}, video)


def test_the_still_replaces_the_packages_still_bundle_and_nothing_else(tmp_path):
    pkg, off, st = tmp_path / "pkg", tmp_path / "off", tmp_path / "still_run"
    sh = "shots/SHOT_001"
    keep = [write(pkg / sh / "renders/video/bundle_manifest.video.json", b"V"), write(off / sh / "renders/video/raw/beauty.1001.exr", b"V"),
            write(off / sh / "exports/camera.json", b"C"), write(pkg / sh / "qc/full_range_gates.json", b"{}")]
    old = [write(pkg / sh / "renders/still/bundle_manifest.still.json", b"old"), write(off / sh / "renders/still/raw/beauty.1050.exr", b"old"),
           write(off / sh / "renders/still/COMPOSITE_BUNDLE/composite.1050.exr", b"old")]
    write(st / "renders/still/bundle_manifest.still.json", b"{}")
    write(st / "renders/still/render_manifest.still.json", b"{}")
    write(st / "renders/still/raw/beauty.1050.exr", b"N" * 1000)
    write(st / "renders/still/SKIN_PROBE_BUNDLE/skin_probe.1050.exr", b"P" * 100)   # the probe's derived parts go in
    write(st / "renders/still/last_step.log", b"log")
    write(st / "probe_renders/still/raw/skin_probe.1050.exr", b"raw probe")          # its raw render stays in the run
    retire = tmp_path / "versions" / "oldhash"
    counts = mf.replace_still(pkg, off, "SHOT_001", st / "renders/still", retire)
    assert all(p.exists() for p in keep)
    assert (retire / sh / "renders/still/raw/beauty.1050.exr").read_bytes() == b"old", "the older version's offline files are retired, never deleted"
    assert not (off / sh / "renders/still/COMPOSITE_BUNDLE/composite.1050.exr").exists(), "a file the new still does not hold is not left behind"
    assert (pkg / sh / "renders/still/bundle_manifest.still.json").read_bytes() == b"{}"
    assert (off / sh / "renders/still/raw/beauty.1050.exr").read_bytes() == b"N" * 1000
    assert (off / sh / "renders/still/SKIN_PROBE_BUNDLE/skin_probe.1050.exr").exists()
    assert not [q for d in (pkg, off) for q in d.rglob("skin_probe.1050.exr") if q.parent.name == "raw"], "the probe's raw render stays in the run"
    assert not (pkg / sh / "renders/still/last_step.log").exists() and counts["offline"] == 2


def probe_bundle(path, shas):
    """A bundle manifest with a SKIN_PROBE_BUNDLE of the conventions' rule, its rows by sha256."""
    from slice import skin_probe as spb
    bm = {"bundles": {spb.P["bundle"]: {"frames": [{"frame": 1001 + i, "sha256": s, "parts": [{"name": n} for n in spb.P["parts"]]}
                                                   for i, s in enumerate(shas)],
                                        "probe": {"edge": spb.P["edge"], "albedo": list(spb.P["tone"]), "master_albedo": [0.8, 0.55, 0.45]}}}}
    return write(path, json.dumps(bm).encode())


def gate_record(status="PASS"):
    from slice import skin_probe as spb
    return {"status": status, "method": "probe", "master_albedo": [0.8, 0.55, 0.45], "probe_albedo": list(spb.P["tone"]),
            "supported_range": {"min": [0.2, 0.11, 0.07], "max": [0.9, 0.72, 0.62]}, "relative_error_max": 0.03,
            "relative_error_p99_max": 0.04, "tones": {}, "scale_percent": 25, "frames_gated": 1, "frames_in_bundle": 1, "coverage": ""}


def test_a_shot_is_packaged_only_with_its_still_derived_and_its_gate_recorded_beside_its_probe(tmp_path):
    from bakeoff.stages import run as rn
    from slice.check_skin_tone import record_in_bundles
    st = tmp_path / "SHOT_001" / "still"
    assert mf.still_ready(st) is False                                              # no still made yet
    bundle = probe_bundle(st / "renders/still/bundle_manifest.still.json", ["a" * 64])
    steps = rn.Steps(st)
    steps.mark("skin_probe", 1.0, [bundle])
    assert mf.still_ready(st) is False, "derived but the gate's record not yet in its bundle"
    record_in_bundles(st / "renders", ["still"], gate_record(), tmp_path / "gate")
    steps.mark("skin_tone_record", 0.0, [bundle])
    assert mf.still_ready(st) is True
    probe_bundle(bundle, ["b" * 64])                                               # the probe derived again, the record not
    bm = json.loads(bundle.read_text())
    bm["skin_tone"] = json.loads(json.dumps(gate_record())) | {"probe_bundle_sha256": "0" * 64}
    bundle.write_text(json.dumps(bm))
    assert mf.still_ready(st) is False, "the record vouches for another probe"


def test_a_gate_record_not_written_beside_the_bundles_probe_sends_its_step_back(tmp_path):
    """Burst 6 review Q79-1 (2026-11-01): a record written before the binding (no fingerprint) or beside another probe —
    the step that wrote it is no longer DONE, so the gate (or the still's record) runs again; a bound record is left alone."""
    from bakeoff.stages import run as rn
    from slice.check_skin_tone import record_in_bundles
    sd = tmp_path / "SHOT_003"
    bp = probe_bundle(sd / "run/renders/video/bundle_manifest.video.json", ["a" * 64, "b" * 64])
    steps = rn.Steps(sd)
    assert mf.retire_unbound_gate(bp, steps, "skin_tone") is False, "the step never ran: nothing to send back"
    write(sd / "skin_tone.log", b"")
    steps.mark("skin_tone", 1.0, [sd / "skin_tone.log"])
    record_in_bundles(sd / "run/renders", ["video"], gate_record(), tmp_path / "gate")
    assert mf.retire_unbound_gate(bp, steps, "skin_tone") is False and steps.done("skin_tone")
    bm = json.loads(bp.read_text())
    del bm["skin_tone"]["probe_bundle_sha256"]                                     # as written before 2026-11-01
    bp.write_text(json.dumps(bm))
    assert mf.retire_unbound_gate(bp, steps, "skin_tone") is True and not steps.done("skin_tone")


def test_a_shot_is_packaged_only_when_its_video_bundles_gate_vouches_for_its_probe(tmp_path):
    from bakeoff.stages import run as rn
    from slice.check_skin_tone import record_in_bundles
    sd = tmp_path / "SHOT_002"
    assert "full_range_gates.json" in mf.shot_not_ready(sd)
    ok = {"roundtrip": {"status": "PASS"}, "blur_fidelity": {"status": "PASS"}, "skin_tone": {"status": "PASS", "method": "probe"}}
    write(sd / "full_range_gates.json", json.dumps(dict(ok, roundtrip={"status": "FAIL"})).encode())
    assert "roundtrip" in mf.shot_not_ready(sd)
    write(sd / "full_range_gates.json", json.dumps(ok).encode())
    vb = probe_bundle(sd / "run/renders/video/bundle_manifest.video.json", ["a" * 64])
    assert "still" in mf.shot_not_ready(sd)
    st = sd / "still"
    sb = probe_bundle(st / "renders/still/bundle_manifest.still.json", ["c" * 64])
    record_in_bundles(st / "renders", ["still"], gate_record(), tmp_path / "gate")
    rn.Steps(st).mark("skin_tone_record", 0.0, [sb])
    assert "NOT RUN" in mf.shot_not_ready(sd), "the video bundle carries no gate record"
    record_in_bundles(sd / "run/renders", ["video"], gate_record(), tmp_path / "gate")
    assert mf.shot_not_ready(sd) is None
    probe_bundle(vb, ["d" * 64])
    bm = json.loads(vb.read_text())
    bm["skin_tone"] = gate_record() | {"probe_bundle_sha256": "0" * 64}
    vb.write_text(json.dumps(bm))
    assert "another" in mf.shot_not_ready(sd)


def test_a_new_package_version_moves_the_bake_offs_views_and_master_inputs_of_the_old_one_aside(tmp_path):
    """The views (symlinks into the package) and the master's per-shot order inputs (the shadow denominator, the still's
    render context) are made once from the package and not checked against it again; made from the old version they would
    point at retired files or the old frames. A new version moves them aside, never deleting them; they are made again
    from the new one on first use."""
    runs = tmp_path / "bakeoff"
    write(runs / "views/SHOT_003/renders/video/bundle_manifest.video.json", b"old view")
    write(runs / "master/SHOT_003/video/denominator/denominator_manifest.json", b"3 frames")
    write(runs / "geometry_cache/SHOT_001/x.abc", b"kept")
    moved = mf.retire_package_derivatives(runs, "abcdef0123456789")
    assert sorted(p.name for p in moved) == ["master.package_abcdef012345", "views.package_abcdef012345"]
    assert not (runs / "views").exists() and not (runs / "master").exists()
    assert (runs / "master.package_abcdef012345/SHOT_003/video/denominator/denominator_manifest.json").read_bytes() == b"3 frames"
    assert (runs / "geometry_cache/SHOT_001/x.abc").exists()
    assert mf.retire_package_derivatives(runs, "abcdef0123456789") == [], "nothing left to move"


def test_a_shot_is_packaged_only_when_its_skin_tone_gate_is_the_probes():
    ok = {"roundtrip": {"status": "PASS"}, "blur_fidelity": {"status": "PASS"}, "skin_tone": {"status": "PASS", "method": "probe"}}
    assert mf.gates_not_passed(ok) == {}
    assert mf.gates_not_passed(dict(ok, skin_tone={"status": "PASS"})) == {"skin_tone": "PASS (first order)"}
    assert mf.gates_not_passed(dict(ok, skin_tone={"status": "VACUOUS", "method": "probe"})) == {"skin_tone": "VACUOUS"}, \
        "VACUOUS is not a pass (burst 6 review finding 5): the gated frames measured none of the skin the bundle has"
    assert mf.gates_not_passed(dict(ok, roundtrip={"status": "FAIL"})) == {"roundtrip": "FAIL"}


def write(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def test_the_full_range_replaces_the_packages_video_bundle_and_its_gates_and_nothing_else(tmp_path):
    pkg, off, run = tmp_path / "pkg", tmp_path / "off", tmp_path / "run"
    sh = "shots/SHOT_001"
    keep = [write(pkg / sh / "renders/still/bundle_manifest.still.json", b"{}"), write(off / sh / "renders/still/raw/beauty.1060.exr", b"S"),
            write(off / sh / "exports/camera.json", b"C"), write(pkg / sh / "qc/silhouette/report.json", b"{}"),
            write(pkg / sh / "order_qc/video/order_composite_manifest.json", b"{}")]
    old = [write(pkg / sh / "renders/video/bundle_manifest.video.json", b"old"), write(off / sh / "renders/video/raw/beauty.1001.exr", b"old"),
           write(off / sh / "qc/blur_reference/video/raw/blur_reference.1001.exr", b"old"), write(pkg / sh / "qc/skin_tone/compare.json", b"old")]
    big_manifest = b"{" + b" " * (600 * 1024) + b"}"                     # over the light limit: a manifest stays light anyway
    write(run / "renders/video/bundle_manifest.video.json", big_manifest)
    write(run / "renders/video/render_manifest.video.json", b"{}")
    write(run / "renders/video/raw/beauty.1002.exr", b"B" * 1000)
    write(run / "blur_reference/video/raw/blur_reference.1011.exr", b"R")
    write(run / "blur_fidelity/blur_fidelity_report.json", b"{}")
    write(run / "skin_tone/check_skin_tone.json", b"{}")
    write(run / "skin_tone/compare.json", b"{}")
    write(run / "skin_tone/master/renders/video/raw/beauty.1001.exr", b"truth")   # the truths stay in the run
    write(run / "renders/video/SKIN_PROBE_BUNDLE/skin_probe.1002.exr", b"P" * 100)   # the probe's derived parts go in
    write(run / "probe_renders/video/raw/skin_probe.1002.exr", b"raw probe")       # its raw render stays in the run
    summary = write(tmp_path / "full_range_gates.json", b"{}")
    retire = tmp_path / "versions" / "oldhash"
    counts = mf.replace_video(pkg, off, "SHOT_001", run, summary, retire)
    assert all(p.exists() for p in keep)
    assert not any(p.exists() and p.read_bytes() == b"old" for p in old)          # gone, or the new version's
    assert not (off / sh / "renders/video/raw/beauty.1001.exr").exists()          # a frame the run does not hold is not left behind
    assert (pkg / sh / "renders/video/bundle_manifest.video.json").read_bytes() == big_manifest
    assert (off / sh / "renders/video/raw/beauty.1002.exr").read_bytes() == b"B" * 1000
    assert (off / sh / "qc/blur_reference/video/raw/blur_reference.1011.exr").exists()
    assert (pkg / sh / "qc/skin_tone/check_skin_tone.json").exists() and not (pkg / sh / "qc/skin_tone/master").exists()
    assert (pkg / sh / "qc/full_range_gates.json").exists()
    assert (off / sh / "renders/video/SKIN_PROBE_BUNDLE/skin_probe.1002.exr").exists()
    assert not list(pkg.rglob("probe_renders")) and not list(off.rglob("probe_renders"))
    assert counts == {"light": 6, "offline": 3}
    # the earlier version's offline files are moved aside, not deleted (its light part is in git)
    assert (retire / sh / "renders/video/raw/beauty.1001.exr").read_bytes() == b"old"
    assert (retire / sh / "qc/blur_reference/video/raw/blur_reference.1001.exr").read_bytes() == b"old"


def test_a_new_package_version_is_pinned_in_the_master_record_and_nothing_else_there_changes(tmp_path):
    """2026-11-01: the package's version 85ba5341 left master.json pinning 490e9807 — the master record pins the package
    as hashed (tests/test_bakeoff_record.py), so packaging writes it."""
    rec = {"master_id": "M", "shots": ["SHOT_001"], "package_hash": "a" * 64, "toolchain": {"dcc": "Blender"}}
    m = write(tmp_path / "master.json", (json.dumps(rec, indent=2, ensure_ascii=False) + "\n").encode())
    pm = write(tmp_path / "package_manifest.json", json.dumps({"package_hash": "b" * 64}).encode())
    assert mf.pin_package(m, pm) == ("a" * 64, "b" * 64)
    assert json.loads(m.read_text()) == dict(rec, package_hash="b" * 64)
    assert m.read_text() == json.dumps(dict(rec, package_hash="b" * 64), indent=2, ensure_ascii=False) + "\n"


def test_the_packages_picked_frames_are_its_frames_until_it_holds_the_full_range_then_its_gate_summarys(tmp_path, monkeypatch):
    """2026-11-01: once the package held the full-range video (85ba5341), `gate` compared pick_frames with all 120 frames and
    refused every shot — the picked frames are then the ones its gate summary records."""
    from bakeoff.stages import run as rn
    light = tmp_path / "slice"
    monkeypatch.setattr(rn, "LIGHT", light)
    fr = mf.CONV["shots"]["SHOT_001"]["frame_range"]
    rm = light / "shots/SHOT_001/renders/video/render_manifest.video.json"
    write(rm, json.dumps({"frames": [{"frame": f} for f in (1001, 1094, 1101)]}).encode())
    assert mf.package_picked_frames("SHOT_001") == [1001, 1094, 1101]
    write(rm, json.dumps({"frames": [{"frame": f} for f in range(fr["start"], fr["end"] + 1)]}).encode())
    with pytest.raises(mf.FullRangeError, match="full_range_gates"):
        mf.package_picked_frames("SHOT_001")
    write(light / "shots/SHOT_001/qc/full_range_gates.json", json.dumps({"picked_frames": [1001, 1094, 1101]}).encode())
    assert mf.package_picked_frames("SHOT_001") == [1001, 1094, 1101]
