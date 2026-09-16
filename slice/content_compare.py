"""Numeric comparison of two JSON trees within a declared absolute tolerance — the cross-platform
rule of slice/conventions.json → rebuild.cross_platform_tolerance. Plain Python, no Blender.

    .venv/bin/python slice/content_compare.py <a.json> <b.json> [--tol 1e-5] [--max-report 20]

Used by slice/accept_delivery.py on the canonical content dumps of slice/blend_content_hash.py
(--dump) when the two content hashes differ, and by slice/rebuild_shot.compare_exports on the
export JSON files. Two trees are EQUAL WITHIN TOLERANCE when they have the same shape, every
non-numeric leaf is identical and every numeric leaf pair differs by at most `tol`. The largest
deviation and the first differing paths are reported; nothing is rounded or clamped."""
import argparse
import json
import math
import sys


def compare(a, b, tol, path="", out=None):
    """Returns {"equal": bool, "max_dev": float, "count": int, "differences": [(path, a, b), ...]}."""
    if out is None:
        out = {"equal": True, "max_dev": 0.0, "count": 0, "differences": []}

    def diff(p, x, y):
        out["equal"] = False
        if len(out["differences"]) < 50:
            out["differences"].append((p, x, y))

    if isinstance(a, bool) or isinstance(b, bool):  # bool is an int subclass — keep it exact
        if a != b:
            diff(path, a, b)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        out["count"] += 1
        if not (math.isfinite(a) and math.isfinite(b)):
            if not (a == b or (math.isnan(a) and math.isnan(b))):
                diff(path, a, b)
        else:
            d = abs(a - b)
            out["max_dev"] = max(out["max_dev"], d)
            if d > tol:
                diff(path, a, b)
    elif isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                diff(f"{path}/{k}", a.get(k, "<missing>"), b.get(k, "<missing>"))
            else:
                compare(a[k], b[k], tol, f"{path}/{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diff(f"{path}/len", len(a), len(b))
        for i, (x, y) in enumerate(zip(a, b)):
            compare(x, y, tol, f"{path}[{i}]", out)
    else:
        if a != b:
            diff(path, a, b)
    return out


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--tol", type=float, required=True)
    p.add_argument("--max-report", type=int, default=20)
    args = p.parse_args(argv)
    res = compare(json.load(open(args.a)), json.load(open(args.b)), args.tol)
    for path, x, y in res["differences"][: args.max_report]:
        print(f"DIFF {path}: {x!r} vs {y!r}")
    verdict = "CONTENT_COMPARE_OK" if res["equal"] else "CONTENT_COMPARE_FAIL"
    print(f"{verdict} numbers={res['count']} max_dev={res['max_dev']:.3e} tol={args.tol:g} differences={len(res['differences'])}")
    return 0 if res["equal"] else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
