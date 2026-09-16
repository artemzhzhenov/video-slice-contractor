"""Compare two proxies.abc numerically within the declared cross-platform tolerance:

    blender -b --python-exit-code 2 -P slice/compare_alembic.py -- --a <A>/proxies.abc --b <B>/proxies.abc \\
        --meta <A>/proxies.abc.meta.json --tol 1e-5

The geometry hash in proxies.abc.meta.json rounds every vertex to 1e-6 m, so two caches that
differ by float noise (measured 1.3e-7 m across Linux CPU and macOS Metal, 2026-09-16) hash
differently although they are the same geometry. This script imports each cache into an empty
scene, evaluates every proxy object at every frame of the meta's range and every sub-frame
offset of slice/conventions.json, and requires the same objects, the same vertex counts and
every vertex position within --tol. Prints ALEMBIC_COMPARE_OK max_dev=… or
ALEMBIC_COMPARE_FAIL with the first offending sample; exit 2 on failure."""
import argparse
import json
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
OFFSETS = CONV["exports"]["sub_frame_offsets_frames"]


def sample(abc, names, frames):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.alembic_import(filepath=str(abc), as_background_job=False, set_frame_range=False)
    scene = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    out = {}
    missing = [n for n in names if bpy.data.objects.get(n) is None]
    if missing:
        raise SystemExit(f"ALEMBIC_COMPARE_FAIL {abc}: objects missing after import: {missing}")
    for frame in range(frames[0], frames[1] + 1):
        for off in OFFSETS:
            scene.frame_set(frame, subframe=off) if off >= 0 else scene.frame_set(frame - 1, subframe=1.0 + off)
            dg.update()
            for n in names:
                ev = bpy.data.objects[n].evaluated_get(dg)
                out[(n, frame, off)] = [tuple(ev.matrix_world @ v.co) for v in ev.data.vertices]
    return out


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.add_argument("--meta", required=True)
    p.add_argument("--tol", type=float, required=True)
    args = p.parse_args(argv)
    meta = json.load(open(args.meta))
    names, frames = meta["proxy_objects"], meta["frames"]
    A = sample(args.a, names, frames)
    B = sample(args.b, names, frames)
    max_dev, worst, n = 0.0, None, 0
    for key in A:
        pa, pb = A[key], B[key]
        if len(pa) != len(pb):
            print(f"ALEMBIC_COMPARE_FAIL {key}: vertex count {len(pa)} vs {len(pb)}")
            sys.exit(2)
        for i, (x, y) in enumerate(zip(pa, pb)):
            d = max(abs(x[k] - y[k]) for k in range(3))
            n += 1
            if d > max_dev:
                max_dev, worst = d, (key, i)
    if max_dev > args.tol:
        print(f"ALEMBIC_COMPARE_FAIL max_dev={max_dev:.3e} > tol {args.tol:g} at object={worst[0][0]} frame={worst[0][1]} offset={worst[0][2]} vertex={worst[1]}")
        sys.exit(2)
    print(f"ALEMBIC_COMPARE_OK objects={len(names)} samples={len(A)} vertices={n} max_dev={max_dev:.3e} tol={args.tol:g}")


if __name__ == "__main__":
    main()
