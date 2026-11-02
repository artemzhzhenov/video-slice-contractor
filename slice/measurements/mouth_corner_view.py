"""What the shot camera sees in and around the mouth, pixel by pixel (owner, 2026-11-02, after burst 7: on the default
head v04.2's laughter "the jaw still shows at the corners, from the cheeks' side"). Our own measurement; runs under
Blender on a shot file and changes nothing in it:

    blender -b SHOT_001_v03.blend --python-exit-code 2 -P slice/measurements/mouth_corner_view.py -- \
        --frames 1085-1110 --out corners.json [--maps <dir> --map-frames 1094,1106] [--step 3]

Per frame, one ray per `step`-th pixel of a 4K window around the mouth (the teeth's bounding-box centre, half 0.05 m
wide — the close-up of scripts/owner_preview/closeup.py --bbox --half 0.05 --width 3840), from the camera, past every
object the camera does not render. The first rendered surface is counted by kind:
- `skin_back` — HERO_HEAD struck from behind: the skin's inner side, seen where the corners fold (the cheek slits);
- `teeth` — HERO_TEETH_UPPER / LOWER, split by where the struck face lies on the teeth at rest (the base mesh, the
  head's frame: +X left/right, -Y forward): `front` when its centre is within `--front-mm` of the arch's front and
  within `--half-width-mm` of the middle, else `lateral` — the arch's sides, which the owner saw as grey plates at the
  corners; the face index of the evaluated mesh is the base mesh's (no modifier changes the teeth's topology — checked);
- `tongue`, `sack` (HERO_MOUTH_SACK, the dark mouth), `skin_front`, `other`.
The darkened teeth (owner, 2026-11-02, Q88: v04.3 darkens the arch behind the incisors): each teeth hit also reads the
teeth's POINT attribute `teeth_shade` (the factor their material multiplies the base colour by, 1 = full albedo) at the
struck point, interpolated over the struck face (mathutils.interpolate.poly_3d_calc on the evaluated face), and a
lateral hit is counted `teeth_lateral_light` when the shade is above `--light-shade` (0.3, the contractor's own split
in Q87), else `teeth_lateral_dark`; `teeth_lateral` stays their sum. A mesh without the attribute is at full albedo by
construction (its material multiplies nothing) and counts at 1.0 — recorded per object in `teeth_shade`.
The counts are rays (pixels / step²), comparable between files on the same shot and frames. The split of the teeth is
an ENGINEERING JUDGMENT (front 8 mm, half-width 12 mm: a 7-9-year-old's canines stand ~13-15 mm from the middle; the
arch here is 39 mm wide and 43 mm deep), recorded with its bins (`teeth_bins`), so another split can be read off."""
import argparse
import json
import struct
import sys
import zlib
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.interpolate import poly_3d_calc

COL = {"skin_front": (235, 200, 190), "skin_back": (220, 30, 30), "teeth_front": (255, 255, 255),
       "teeth_lateral_light": (255, 170, 0), "teeth_lateral_dark": (130, 70, 20), "tongue": (240, 120, 150), "sack": (30, 30, 160), "other": (120, 200, 120),
       "none": (0, 0, 0)}


def frames_arg(s):
    if "-" in s and "," not in s:
        a, b = (int(x) for x in s.split("-"))
        return list(range(a, b + 1))
    return [int(x) for x in s.split(",")]


def write_png(path, rows):
    w, h = len(rows[0]) // 3, len(rows)
    raw = b"".join(b"\x00" + bytes(r) for r in rows)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--maps")
    ap.add_argument("--map-frames", default="")
    ap.add_argument("--step", type=int, default=3)
    ap.add_argument("--front-mm", type=float, default=8.0)
    ap.add_argument("--half-width-mm", type=float, default=12.0)
    ap.add_argument("--light-shade", type=float, default=0.3)
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
    sc = bpy.data.scenes["SLICE"]
    cam = sc.camera
    W, H = 3840, 2160
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, 100
    head = bpy.data.objects["HERO_HEAD"]
    teeth_names = [n for n in ("HERO_TEETH_UPPER", "HERO_TEETH_LOWER") if n in bpy.data.objects]
    # each teeth face's centre at rest, in the head's frame
    rest = {}
    front_y = min(min((head.matrix_world.inverted() @ (bpy.data.objects[n].matrix_world @ v.co)).y
                      for v in bpy.data.objects[n].data.vertices) for n in teeth_names)
    for n in teeth_names:
        o = bpy.data.objects[n]
        m = head.matrix_world.inverted() @ o.matrix_world
        rest[n] = [m @ (sum((o.data.vertices[i].co for i in p.vertices), Vector()) / len(p.vertices)) for p in o.data.polygons]
    shade_attr = {n: ("teeth_shade" in bpy.data.objects[n].data.attributes
                      and bpy.data.objects[n].data.attributes["teeth_shade"].domain == "POINT") for n in teeth_names}
    rec = {"rule": __doc__.split("\n\n")[0].replace("\n", " "), "source": bpy.data.filepath, "shot": sc.get("shot_id"),
           "step": a.step, "front_mm": a.front_mm, "half_width_mm": a.half_width_mm, "light_shade": a.light_shade,
           "teeth_shade": {n: "POINT attribute read" if v else "absent — full albedo, counted at 1.0" for n, v in shade_attr.items()},
           "default_head_version": head.get("default_head_version", "v04.1 or a child"), "frames": []}
    map_frames = set(frames_arg(a.map_frames)) if a.map_frames else set()
    if a.maps:
        Path(a.maps).mkdir(parents=True, exist_ok=True)
    for f in frames_arg(a.frames):
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        for n in teeth_names:
            if len(bpy.data.objects[n].evaluated_get(dg).data.polygons) != len(rest[n]):
                sys.exit(f"MOUTH_CORNER_ERROR {n}: the evaluated faces differ from the base mesh")
        obs = [bpy.data.objects[n] for n in teeth_names]
        p = sum((o.matrix_world @ (sum((Vector(v) for v in o.evaluated_get(dg).bound_box), Vector()) / 8) for o in obs), Vector()) / len(obs)
        c = world_to_camera_view(sc, cam, p)
        right = cam.matrix_world.to_3x3() @ Vector((1, 0, 0))
        hx = abs(world_to_camera_view(sc, cam, p + right * 0.05).x - c.x)
        hy = hx * W / H
        x0, x1, y0, y1 = int((c.x - hx) * W), int((c.x + hx) * W), int((c.y - hy) * H), int((c.y + hy) * H)
        tr, br, bl, tl = [cam.matrix_world @ v for v in cam.data.view_frame(scene=sc)]
        origin = cam.matrix_world.translation
        counts, bins, rows = {}, {}, []
        for py in range(y1, y0, -a.step):
            row = bytearray()
            for px in range(x0, x1, a.step):
                u, v = (px + 0.5) / W, (py + 0.5) / H
                d = (bl + (br - bl) * u + (tl - bl) * v - origin).normalized()
                o, kind = origin.copy(), "none"
                for _ in range(16):
                    hit, loc, nrm, idx, ob, _m = sc.ray_cast(dg, o, d)
                    if not hit:
                        break
                    if ob.hide_render or not ob.visible_camera or any(cl.name == "C_PROXIES" for cl in ob.users_collection):
                        o = loc + d * 1e-4
                        continue
                    n = ob.name
                    if n == "HERO_HEAD":
                        kind = "skin_back" if nrm.dot(d) > 0 else "skin_front"
                    elif n in rest:
                        q = rest[n][idx]
                        depth, half = (q.y - front_y) * 1000, abs(q.x) * 1000
                        kind = "teeth_front" if depth <= a.front_mm and half <= a.half_width_mm else "teeth_lateral"
                        if kind == "teeth_lateral":
                            shade = 1.0
                            if shade_attr[n]:
                                me = ob.evaluated_get(dg).data
                                vi = list(me.polygons[idx].vertices)
                                wts = poly_3d_calc([ob.matrix_world @ me.vertices[i].co for i in vi], loc)
                                vals = me.attributes["teeth_shade"].data
                                shade = sum(w * vals[i].value for w, i in zip(wts, vi))
                            kind += "_light" if shade > a.light_shade else "_dark"
                        key = f"{n[11:].lower()} depth {int(depth // 4) * 4}-{int(depth // 4) * 4 + 4} mm, |x| {int(half // 4) * 4}-{int(half // 4) * 4 + 4} mm"
                        bins[key] = bins.get(key, 0) + 1
                    elif n == "HERO_TONGUE":
                        kind = "tongue"
                    elif n == "HERO_MOUTH_SACK":
                        kind = "sack"
                    else:
                        kind = "other"
                    break
                counts[kind] = counts.get(kind, 0) + 1
                row += bytes(COL[kind])
            rows.append(row)
        counts["teeth_lateral"] = counts.get("teeth_lateral_light", 0) + counts.get("teeth_lateral_dark", 0)
        rec["frames"].append({"frame": f, "window_px": [x0, y0, x1, y1], "counts": counts, "teeth_bins": bins})
        if a.maps and f in map_frames:
            write_png(Path(a.maps) / f"corners_{f}.png", rows)
    tot = {}
    for fr in rec["frames"]:
        for k, v in fr["counts"].items():
            tot[k] = tot.get(k, 0) + v
    rec["totals"] = tot
    rec["worst"] = {k: max(((fr["counts"].get(k, 0), fr["frame"]) for fr in rec["frames"]), default=(0, None))
                    for k in ("teeth_lateral", "teeth_lateral_light", "skin_back")}
    Path(a.out).write_text(json.dumps(rec, indent=1) + "\n")
    print("MOUTH_CORNER_VIEW " + json.dumps({"frames": len(rec["frames"]), "teeth_lateral": tot.get("teeth_lateral", 0),
                                             "teeth_lateral_light": tot.get("teeth_lateral_light", 0),
                                             "skin_back": tot.get("skin_back", 0), "teeth_front": tot.get("teeth_front", 0),
                                             "sack": tot.get("sack", 0), "worst": rec["worst"]}))


main()
