"""slice/skin_probe.py — which SKIN_PROBE_BUNDLE an order and the gate may use (ADR-0002 amendment 2026-10-31, the edge
2026-11-01; CI, no Blender: the bundle manifest alone)."""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slice import skin_probe as spb  # noqa: E402

P = spb.P


def manifest():
    rows = [{"frame": f, "parts": [{"name": n} for n in P["parts"]]} for f in (1001, 1002)]
    return {"bundles": {P["bundle"]: {"frames": rows, "probe": {"edge": dict(P["edge"])}}}}


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
