"""slice/check_skin_tone.py — the verdict of the skin-tone gate (ADR-0002 amendment 2026-09-29, C4, amended 2026-10-31:
the re-tint between the master and its probe, the mean and the 99th percentile over blocks; CI, no Blender)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slice import check_skin_tone as cst  # noqa: E402


def res(e, e0, p99=None):
    return {"frames": {1338: {"darkest": {"BODY_BEAUTY": {"relative_error": e, "relative_error_p99": e if p99 is None else p99,
                                                          "no_retint_relative_error": e0, "blocks": 773}}}}}


def test_a_re_tint_within_the_bound_passes_only_when_no_re_tint_would_fail():
    assert cst.verdict(res(0.012, 3.2), lim99=0.05)[0] == "PASS"
    assert cst.verdict(res(0.25, 3.2), lim99=0.05)[0] == "FAIL", "the 2D gain's error on very dark skin"
    status, over, blind = cst.verdict(res(0.001, 0.002), lim99=0.05)
    assert status == "FAIL" and blind, "a tone the master already has proves nothing: the negative control must fail the bound"


def test_a_local_defect_fails_the_gate_though_the_mean_passes():
    status, over, _ = cst.verdict(res(0.02, 3.2, p99=0.38), lim99=0.05)
    assert status == "FAIL" and over == [(1338, "darkest", "BODY_BEAUTY", "p99", 0.38)]


def test_without_the_owners_local_bound_the_gate_measures_but_does_not_judge(monkeypatch):
    monkeypatch.setitem(cst.G, "relative_error_p99_max", None)
    assert cst.verdict(res(0.012, 3.2), lim99=None)[0] == "NOT_JUDGED"


def test_no_body_skin_in_view_is_vacuous_not_a_pass():
    assert cst.verdict({"frames": {1001: {"darkest": {}}}}, lim99=0.05)[0] == "VACUOUS"


def test_the_gate_tones_span_light_to_dark_and_the_bounds_are_declared():
    g = cst.G
    assert g["relative_error_max"] == 0.03 and set(g["tones"]) == {"lightest", "middle", "darkest"}
    assert all(g["tones"]["darkest"][i] < g["tones"]["middle"][i] < g["tones"]["lightest"][i] for i in range(3))
    assert "relative_error_p99_max" in g and g["block_px"] == 4 and 0 < g["block_min_skin_px"] <= 16 and g["min_skin_blocks"] > 0
    assert "probe" not in g["tones"] and "master" not in g["tones"], "the probe's and the master's renders are not truths"


@pytest.mark.parametrize("lim99", [0.05, None])
def test_the_verdict_reads_the_conventions_bounds_by_default(lim99, monkeypatch):
    monkeypatch.setitem(cst.G, "relative_error_p99_max", lim99)
    assert cst.verdict(res(0.012, 3.2))[0] == ("PASS" if lim99 else "NOT_JUDGED")


def test_the_owners_bound_on_the_99th_percentile_is_set_and_judges_a_local_defect():
    """Owner, 2026-11-01 (decision 14 (a)): 0.04, set from the gate with the edge on the three shots — the worst case
    0.0302 (SHOT_003 1291, the darkest tone, the body); the edge line before the fix measured 0.04–0.40."""
    assert cst.G["relative_error_p99_max"] == 0.04
    assert cst.verdict(res(0.006, 3.0, p99=0.0302))[0] == "PASS"
    assert cst.verdict(res(0.0035, 3.4, p99=0.404))[0] == "FAIL", "SHOT_001's edge line at the darkest tone, 2026-11-01"


def bundles(tmp_path, probes):
    """A run's renders/<profile>/bundle_manifest.<profile>.json per profile, each with its own SKIN_PROBE_BUNDLE (rows by
    sha256), or none."""
    import json
    renders = tmp_path / "renders"
    for prof, shas in probes.items():
        d = renders / prof
        d.mkdir(parents=True)
        bm = {"bundles": {}}
        if shas:
            bm["bundles"][cst.PROBE["bundle"]] = {"frames": [{"frame": 1001 + i, "sha256": s} for i, s in enumerate(shas)],
                                                  "probe": {"albedo": list(cst.PROBE["tone"]), "master_albedo": [0.8, 0.55, 0.45]}}
        (d / f"bundle_manifest.{prof}.json").write_text(json.dumps(bm))
    return renders


def record(status):
    return {"status": status, "method": "probe", "master_albedo": [0.8, 0.55, 0.45], "probe_albedo": list(cst.PROBE["tone"]),
            "supported_range": {"min": [0.2, 0.11, 0.07], "max": [0.9, 0.72, 0.62]} if status == "PASS" else None,
            "relative_error_max": 0.03, "relative_error_p99_max": 0.04, "tones": cst.G["tones"], "scale_percent": 25,
            "frames_gated": 2, "frames_in_bundle": 120, "coverage": "2 of 120"}


def test_the_gates_record_in_each_bundle_carries_the_fingerprint_of_that_bundles_probe(tmp_path):
    """Burst 6 review Q79-1 (2026-11-01): an order re-tints only beside the probe the record was written beside."""
    import json
    from slice import skin_probe as spb
    renders = bundles(tmp_path, {"video": ["a" * 64, "b" * 64], "still": ["c" * 64], "bare": []})
    cst.record_in_bundles(renders, ["video", "still", "bare"], record("PASS"), tmp_path / "gate")
    bm = {p: json.loads((renders / p / f"bundle_manifest.{p}.json").read_text()) for p in ("video", "still", "bare")}
    assert spb.gate_refusal(bm["video"]) is None and spb.gate_refusal(bm["still"]) is None
    assert bm["video"]["skin_tone"]["probe_bundle_sha256"] != bm["still"]["skin_tone"]["probe_bundle_sha256"]
    assert bm["bare"]["skin_tone"]["probe_bundle_sha256"] is None and spb.gate_refusal(bm["bare"]) is not None


@pytest.mark.parametrize("status", ["FAIL", "NOT_JUDGED", "VACUOUS"])
def test_a_gate_that_does_not_pass_writes_its_verdict_over_the_old_pass_and_stops(status, tmp_path):
    """Burst 6 review Q79-1: the probe derived again, its gate run again and failed — the bundle must not keep the PASS
    of the probe before; a VACUOUS gate is not a pass (finding 5)."""
    import json
    renders = bundles(tmp_path, {"video": ["a" * 64]})
    cst.record_in_bundles(renders, ["video"], record("PASS"), tmp_path / "gate")
    with pytest.raises(cst.SkinToneError, match=status if status != "FAIL" else "over the bound"):
        cst.conclude(record(status), renders, ["video"], tmp_path / "gate", worst=(0.05, 0.4) if status != "VACUOUS" else None,
                     over=[(1338, "darkest", "BODY_BEAUTY", "mean", 0.05)] if status == "FAIL" else [], blind=[])
    bm = json.loads((renders / "video" / "bundle_manifest.video.json").read_text())
    assert bm["skin_tone"]["status"] == status and bm["skin_tone"]["supported_range"] is None


def test_a_passing_gate_is_recorded_and_returns(tmp_path):
    import json
    renders = bundles(tmp_path, {"video": ["a" * 64]})
    cst.conclude(record("PASS"), renders, ["video"], tmp_path / "gate", worst=(0.006, 0.03), over=[], blind=[])
    assert json.loads((renders / "video" / "bundle_manifest.video.json").read_text())["skin_tone"]["status"] == "PASS"


def test_the_shared_edge_is_summed_up_beside_the_verdict_and_never_judges_it():
    """Burst 6 review (Q79, edge): the gate's mask (skin > 0.5, the layer opaque) leaves the front plate's edge on
    transparency out; its error is recorded per case and summed up — the owner sets a bound, if any (2026-11-01)."""
    r = res(0.006, 3.0, p99=0.03)
    case = r["frames"][1338]["darkest"]["BODY_BEAUTY"]
    case["shared"] = {"px": 900, "relative_error": 0.019, "relative_error_p99": 0.14}
    r["frames"][1338]["middle"] = {"FOREGROUND_PLATE": dict(case, shared={"px": 300, "relative_error": 0.007, "relative_error_p99": 0.2})}
    assert cst.shared_summary(r) == {"cases": 2, "px": 1200, "worst_mean": 0.019, "worst_p99": 0.2, "judged": False}
    assert cst.verdict(r)[0] == "PASS", "the edge's numbers are not the verdict's"
    assert cst.shared_summary(res(0.006, 3.0)) == {"cases": 0, "px": 0, "worst_mean": None, "worst_p99": None, "judged": False}
