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


def test_without_the_owners_local_bound_the_gate_measures_but_does_not_judge():
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
