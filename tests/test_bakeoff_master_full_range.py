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


def test_a_shot_is_packaged_only_when_its_skin_tone_gate_is_the_probes():
    ok = {"roundtrip": {"status": "PASS"}, "blur_fidelity": {"status": "PASS"}, "skin_tone": {"status": "PASS", "method": "probe"}}
    assert mf.gates_not_passed(ok) == {}
    assert mf.gates_not_passed(dict(ok, skin_tone={"status": "PASS"})) == {"skin_tone": "PASS (first order)"}
    assert mf.gates_not_passed(dict(ok, skin_tone={"status": "VACUOUS", "method": "probe"})) == {}
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
