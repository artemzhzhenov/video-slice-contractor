"""How different two faces are, as one number: the synthetic set's distinctness rule (owner, 2026-10-24 — every child
differs from the default head and from every other child by at least RULE_MM). Runs under Blender; opens each file in
turn (a character or shot file of the slice: same head topology as the default head, or the run stops):

    blender -b --python-exit-code 2 -P slice/measurements/face_shape_distance.py -- \
        --default character_v04_1.blend --subjects subject_01_character.blend subject_02_character.blend ... \
        [--json report.json]

Each head's HERO_HEAD is taken with every FACE_CTRL channel at 0, at the file's first frame, in the socket's contract
frame (C·socket⁻¹: X the character's left, Y up, Z forward). The FACE is fixed once, on the default head: the vertices
whose normal points forward (z > 0.3), in the front 60 % of the head's depth, from 5 mm above the chin up to 35 mm
above the eyes' centre — about 1600 vertices. For a pair of heads the per-vertex displacement over the face is taken,
its mean is removed (a translation is not a different face), and the root mean square of what is left is the
distance. Vertex to vertex — every child shares the default head's topology — so no definition of where a nose or a
cheek ends enters the number. Nose, eye spacing and face width are described elsewhere (the contractor's face_measure
v2); they are not the rule."""
import argparse
import itertools
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from slice import socketspace as ss  # noqa: E402

CMAP = json.loads((ROOT / "slice" / "channel_map.json").read_text())
RULE_MM = 2.0


def head(path):
    bpy.ops.wm.open_mainfile(filepath=str(path))
    ctrl = bpy.data.objects.get("FACE_CTRL")
    if ctrl is not None:
        ctrl.animation_data_clear()
        for ch in CMAP["channels"]:
            ctrl[ch["channel"]] = 0.0
        ctrl.update_tag()
    sc = bpy.data.scenes["SLICE"] if "SLICE" in bpy.data.scenes else bpy.context.scene
    sc.frame_set(sc.frame_start)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    T = Matrix(ss.C) @ bpy.data.objects["SOCKET_HEAD"].evaluated_get(dg).matrix_world.inverted()
    o = bpy.data.objects["HERO_HEAD"].evaluated_get(dg)
    me = o.to_mesh()
    M = T @ o.matrix_world
    v = np.array([(M @ x.co)[:] for x in me.vertices])
    n = np.array([(M.to_3x3() @ x.normal).normalized()[:] for x in me.vertices])
    o.to_mesh_clear()
    eyes = [T @ bpy.data.objects[k].evaluated_get(dg).matrix_world.translation for k in ("HERO_EYE_L", "HERO_EYE_R")]
    return v, n, (eyes[0].y + eyes[1].y) / 2


def face_mask(v0, n0, eye_y):
    """The FACE of the docstring, fixed on the default head."""
    chin = v0[:, 1].min()
    return (n0[:, 2] > 0.3) & (v0[:, 1] > chin + 0.005) & (v0[:, 1] < eye_y + 0.035) & (v0[:, 2] > np.percentile(v0[:, 2], 40))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--default", required=True)
    ap.add_argument("--subjects", nargs="+", required=True)
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)
    v0, n0, eye_y = head(a.default)
    face = face_mask(v0, n0, eye_y)
    heads = {"default": v0}
    for p in a.subjects:
        v, _, _ = head(p)
        if v.shape != v0.shape:
            raise SystemExit(f"FACE_DISTANCE_FAIL {p}: {len(v)} head vertices, the default head has {len(v0)} — not the same topology")
        heads[Path(p).stem.replace("_character", "")] = v
    pairs = []
    for x, y in itertools.combinations(heads, 2):
        d = heads[y][face] - heads[x][face]
        d -= d.mean(0)
        r = np.linalg.norm(d, axis=1)
        rms = float(np.sqrt((r ** 2).mean())) * 1e3
        pairs.append({"a": x, "b": y, "rms_mm": round(rms, 3), "p95_mm": round(float(np.percentile(r, 95)) * 1e3, 2),
                      "max_mm": round(float(r.max()) * 1e3, 2), "pass": rms >= RULE_MM})
    rec = {"rule": __doc__.split("\n\n")[0].replace("\n", " "), "rule_mm": RULE_MM, "face_vertices": int(face.sum()),
           "definition": __doc__.split("\n\n")[2].replace("\n", " "), "default": a.default, "pairs": pairs,
           "failing": [f"{p['a']}–{p['b']} {p['rms_mm']} mm" for p in pairs if not p["pass"]]}
    if a.json:
        Path(a.json).write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n")
    for p in pairs:
        print(f"FACE_DISTANCE {p['a']:>12s} {p['b']:<12s} {p['rms_mm']:6.3f} mm {'PASS' if p['pass'] else 'FAIL'}")
    print(f"FACE_DISTANCE_{'OK' if not rec['failing'] else 'FAIL'} rule >= {RULE_MM} mm over {rec['face_vertices']} face vertices; failing: {rec['failing'] or 'none'}")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:])
