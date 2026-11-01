"""slice/skin_probe.py — which SKIN_PROBE_BUNDLE an order and the gate may use (ADR-0002 amendment 2026-10-31, the edge
2026-11-01; CI, no Blender: the bundle manifest alone)."""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slice import skin_probe as spb  # noqa: E402

P = spb.P


MASTER = [0.8, 0.55, 0.45]


def manifest():
    rows = [{"frame": f, "sha256": f"{f:064d}", "parts": [{"name": n} for n in P["parts"]]} for f in (1001, 1002)]
    return {"bundles": {P["bundle"]: {"frames": rows, "probe": {"edge": dict(P["edge"]), "albedo": [round(v, 6) for v in P["tone"]],
                                                                "master_albedo": list(MASTER)}}}}


def gated(bm, **over):
    """The bundle with the gate's record as check_skin_tone.record_in_bundles writes it beside this probe."""
    bm = copy.deepcopy(bm)
    bm["skin_tone"] = {"status": "PASS", "method": "probe", "probe_albedo": list(P["tone"]), "master_albedo": list(MASTER),
                       "supported_range": {"min": [0.2, 0.11, 0.07], "max": [0.9, 0.72, 0.62]},
                       "probe_bundle_sha256": spb.probe_fingerprint(bm)} | over
    return bm


def test_a_bundle_derived_by_the_conventions_rule_is_current():
    assert spb.derived_by_current_rule(manifest())


def test_a_bundle_derived_before_the_edge_is_not_current():
    old = manifest()
    for r in old["bundles"][P["bundle"]]["frames"]:
        r["parts"] = [{"name": n} for n in ("REST_BACK", "BOUNCE_BACK", "REST_FRONT", "BOUNCE_FRONT")]   # 2026-10-31
    del old["bundles"][P["bundle"]]["probe"]["edge"]
    assert not spb.derived_by_current_rule(old)


def test_a_bundle_whose_edge_was_found_by_other_thresholds_or_one_frame_of_other_parts_is_not_current():
    other = manifest()
    other["bundles"][P["bundle"]]["probe"]["edge"]["coverage_min"] = 0.99
    assert not spb.derived_by_current_rule(other)
    one = manifest()
    one["bundles"][P["bundle"]]["frames"][1]["parts"].pop()
    assert not spb.derived_by_current_rule(one)


def test_no_bundle_or_no_frames_is_not_current():
    assert not spb.derived_by_current_rule({"bundles": {}})
    empty = copy.deepcopy(manifest())
    empty["bundles"][P["bundle"]]["frames"] = []
    assert not spb.derived_by_current_rule(empty)


def test_a_layer_has_skin_only_with_a_pixel_more_skin_than_not():
    """SHOT_001's front plate carries the skin material in its cryptomatte but shows no skin on any frame: it is not a
    layer with skin (the 2026-11-01 derive counted 240 layers with skin on 120 frames, where 120 have any)."""
    import numpy as np
    assert not spb.has_skin(None)
    assert not spb.has_skin(np.zeros((4, 4), np.float32))
    assert not spb.has_skin(np.full((4, 4), 0.5, np.float32))
    one = np.zeros((4, 4), np.float32)
    one[2, 3] = 0.6
    assert spb.has_skin(one)


def test_a_bundle_whose_probe_is_not_at_the_conventions_tone_is_not_current():
    """Burst 6 review (Q79): the current rule is also the probe's tone — a bundle derived from a probe of another tone is
    not the conventions' probe."""
    other = manifest()
    other["bundles"][P["bundle"]]["probe"]["albedo"] = [0.3, 0.2, 0.1]
    assert not spb.derived_by_current_rule(other)


def test_the_probes_fingerprint_follows_its_frames_and_albedos_and_nothing_else():
    bm = manifest()
    fp = spb.probe_fingerprint(bm)
    assert len(fp) == 64 and spb.probe_fingerprint(copy.deepcopy(bm)) == fp
    moved = copy.deepcopy(bm)
    moved["bundles"][P["bundle"]]["frames"].reverse()
    assert spb.probe_fingerprint(moved) == fp, "the rows' order is not the probe"
    for change in (lambda b: b["bundles"][P["bundle"]]["frames"][1].update(sha256="f" * 64),
                   lambda b: b["bundles"][P["bundle"]]["probe"].update(albedo=[0.15, 0.08, 0.06]),
                   lambda b: b["bundles"][P["bundle"]]["probe"].update(master_albedo=[0.8, 0.55, 0.44])):
        b = copy.deepcopy(bm)
        change(b)
        assert spb.probe_fingerprint(b) != fp
    assert spb.probe_fingerprint({"bundles": {}}) is None


def test_the_gate_admits_a_re_tint_only_as_a_pass_of_the_probe_method_recorded_beside_this_probe():
    """Burst 6 review Q79-1 and finding 5 (2026-11-01): the record must have been written beside the bundle's probe as it
    is now; a VACUOUS gate admits nothing — derive refuses a render without measurable skin, so beside a probe it means
    skin the gate did not measure."""
    bm = manifest()
    assert spb.gate_refusal(gated(bm)) is None
    assert "NOT RUN" in spb.gate_refusal(bm)
    for status in ("VACUOUS", "FAIL", "NOT_JUDGED"):
        assert status in spb.gate_refusal(gated(bm, status=status))
    assert "probe method" in spb.gate_refusal(gated(bm, method=None))
    again = gated(bm)
    again["bundles"][P["bundle"]]["frames"][0]["sha256"] = "e" * 64          # derived again after the gate
    assert "another" in spb.gate_refusal(again)
    assert "albedo" in spb.gate_refusal(gated(bm, probe_albedo=[0.2, 0.11, 0.07]))
    assert "albedo" in spb.gate_refusal(gated(bm, master_albedo=[0.7, 0.55, 0.45]))
    old = gated(bm)
    del old["skin_tone"]["probe_bundle_sha256"]                               # a record written before 2026-11-01
    assert "another" in spb.gate_refusal(old)


def test_deriving_the_probe_again_retires_the_gates_record_beside_it_never_drops_it():
    bm = gated(manifest())
    rec = copy.deepcopy(bm["skin_tone"])
    spb.retire_gate_record(bm, "derived again")
    assert "skin_tone" not in bm and bm["skin_tone_retired"] == [rec | {"retired": "derived again"}]
    spb.retire_gate_record(bm, "derived again")
    assert len(bm["skin_tone_retired"]) == 1, "nothing to retire: nothing added"


def test_an_orders_probe_frames_are_the_bundles_rows():
    assert spb.probe_frames(manifest()) == {1001: f"{1001:064d}", 1002: f"{1002:064d}"}


def test_a_probe_chunk_whose_frames_show_skin_and_measure_none_of_it_is_named():
    """Burst 6 review Q79-3 (2026-11-01): the guard refused only a probe with no measured layer at all, so a chunk rendered
    off by a frame passed where the skin was small. Each chunk with skin must measure some; a chunk with no skin re-tints
    nothing; a render without chunks is one."""
    rows = [{"frame": 1001, "direct_light_mismatch": {"BACK": 0.5, "FRONT": "NO_SKIN"}},
            {"frame": 1002, "direct_light_mismatch": {"BACK": None, "FRONT": "NO_SKIN"}},
            {"frame": 1003, "direct_light_mismatch": {"BACK": None, "FRONT": None}},
            {"frame": 1004, "direct_light_mismatch": {"BACK": "NO_SKIN", "FRONT": "NO_SKIN"}}]
    chunks = [{"chunk": "1001-1002", "frames": [1001, 1002]}, {"chunk": "1003-1003", "frames": [1003, 1003]},
              {"chunk": "1004-1004", "frames": [1004, 1004]}]
    assert spb.unmeasured_chunks(rows, chunks) == ["1003-1003"]
    assert spb.unmeasured_chunks(rows, None) == [], "one render: 1001 measured"
    assert spb.unmeasured_chunks(rows[1:3], None) == ["1002-1003"]


def test_a_skin_is_re_tintable_only_when_every_hero_skin_material_is_the_bodys_plain_colour():
    """Burst 6 review finding 7 (2026-11-01): the probe sets every hero skin material to one tone, so the light the head
    throws on the body is weighted by the body's albedo — wrong if the master's head skin is another colour, or scatters
    under its surface. The three master files read 2026-11-01: the head's material is the body's."""
    body = [0.8, 0.55, 0.45]
    toned = {"HERO_SKIN_BODY": body, "HERO_SKIN_HEAD": body}
    sss = {"HERO_SKIN_BODY": 0.0, "HERO_SKIN_HEAD": 0.0}
    assert spb.material_status(0.0, False, body, toned, sss) == "RE-TINTABLE"
    assert spb.material_status(0.0, True, body, toned, sss) != "RE-TINTABLE"
    assert spb.material_status(0.1, False, body, toned, sss) != "RE-TINTABLE"
    assert "HERO_SKIN_HEAD" in spb.material_status(0.0, False, body, dict(toned, HERO_SKIN_HEAD=[0.7, 0.5, 0.4]), sss)
    assert "HERO_SKIN_HEAD" in spb.material_status(0.0, False, body, toned, dict(sss, HERO_SKIN_HEAD=0.2))
    assert "HERO_SKIN_HEAD" in spb.material_status(0.0, False, body, dict(toned, HERO_SKIN_HEAD="TEXTURED"), sss)
