"""slice/measurements/mouth_corner_view.py — which teeth the camera sees, split front / lateral (owner, 2026-11-03,
after burst 8: the incisors and the canines of both rows stay light, the arch darkens only behind the canines). A
synthetic mouth: three camera-facing quads per row, the lower row standing 6 mm behind the upper (as on the default
head). Upper: U0 at the row's front, U1 10 mm behind it (a canine), U2 15 mm behind (behind the canine). Lower: L0 at
its row's front, L1 10 mm behind it, L2 18 mm behind. The upper row carries teeth_shade (U0 1.0, U1 0.2, U2 0.1), the
lower none (full albedo).

The split by default counts each face's depth from its own row's front (front within 12 mm, 16 mm of the middle): U0,
U1, L0, L1 front, U2, L2 lateral — U2 dark, L2 light. With `--front-ref common --front-mm 8 --half-width-mm 12` (the
split of 2026-11-02, the burst-8 records) the depth is from the front of both rows: U1 and L1 lateral, U1 dark. Every
teeth hit's shade is binned by its kind, so the dimmed canine in front (0.2) is read off the record."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "slice" / "measurements" / "mouth_corner_view.py"

BUILD = r'''
import math, sys
import bpy
out = sys.argv[sys.argv.index("--") + 1]
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
sc = bpy.context.scene
sc.name = "SLICE"
sc.frame_start, sc.frame_end = 1, 1
# the head: a backdrop behind the teeth, facing the camera (skin_front)
hm = bpy.data.meshes.new("HERO_HEAD")
hm.from_pydata([(-0.3, 0.2, -0.3), (0.3, 0.2, -0.3), (0.3, 0.2, 0.3), (-0.3, 0.2, 0.3)], [], [(0, 3, 2, 1)]); hm.update()
sc.collection.objects.link(bpy.data.objects.new("HERO_HEAD", hm))
def row(name, quads, shades):
    v, f = [], []
    for (x0, x1, y, z0, z1) in quads:
        i = len(v)
        v += [(x0, y, z0), (x0, y, z1), (x1, y, z1), (x1, y, z0)]
        f.append((i, i + 1, i + 2, i + 3))
    me = bpy.data.meshes.new(name); me.from_pydata(v, [], f); me.update()
    if shades is not None:
        a = me.attributes.new("teeth_shade", "FLOAT", "POINT")
        for k, s in enumerate(shades):
            for j in range(4):
                a.data[4 * k + j].value = s
    sc.collection.objects.link(bpy.data.objects.new(name, me))
row("HERO_TEETH_UPPER", [(-0.004, 0.004, -0.050, 0.006, 0.014), (0.006, 0.014, -0.040, 0.006, 0.014),
                         (-0.014, -0.006, -0.035, 0.006, 0.014)], [1.0, 0.2, 0.1])
row("HERO_TEETH_LOWER", [(-0.004, 0.004, -0.044, -0.014, -0.006), (0.006, 0.014, -0.034, -0.014, -0.006),
                         (-0.014, -0.006, -0.026, -0.014, -0.006)], None)
cd = bpy.data.cameras.new("CAM"); cam = bpy.data.objects.new("CAM", cd); sc.collection.objects.link(cam)
cam.location = (0.0, -1.0, 0.0); cam.rotation_euler = (math.radians(90), 0.0, 0.0)
sc.camera = cam
bpy.ops.wm.save_as_mainfile(filepath=out)
print("SYNTH_OK")
'''


def run(tmp, *extra):
    script = tmp / "build.py"
    script.write_text(BUILD)
    blend = tmp / "mouth.blend"
    if not blend.exists():
        r = subprocess.run(["blender", "-b", "--factory-startup", "--python-exit-code", "2", "-P", str(script), "--", str(blend)],
                           capture_output=True, text=True, timeout=600)
        assert r.returncode == 0 and "SYNTH_OK" in r.stdout, r.stdout[-1500:] + r.stderr[-1500:]
    out = tmp / f"corners{'_'.join(extra)}.json"
    r = subprocess.run(["blender", "-b", str(blend), "--factory-startup", "--python-exit-code", "2", "-P", str(TOOL), "--",
                        "--frames", "1", "--out", str(out), "--step", "4", *extra], capture_output=True, text=True, timeout=600)
    assert r.returncode == 0 and "MOUTH_CORNER_VIEW" in r.stdout, r.stdout[-1500:] + r.stderr[-1500:]
    return json.loads(out.read_text())


@pytest.mark.skipif(shutil.which("blender") is None, reason="Blender not installed")
def test_each_row_from_its_own_front_puts_the_canines_in_front(tmp_path):
    rec = run(tmp_path)
    assert rec["front_ref"] == "row" and rec["front_mm"] == 12.0 and rec["half_width_mm"] == 16.0
    assert rec["teeth_split"] == {"HERO_TEETH_UPPER": {"front": [0, 1], "lateral": [2]},
                                  "HERO_TEETH_LOWER": {"front": [0, 1], "lateral": [2]}}
    c = rec["frames"][0]["counts"]
    assert c["teeth_front"] > 0 and c["teeth_lateral_dark"] > 0 and c["teeth_lateral_light"] > 0, c
    bins = rec["frames"][0]["shade_bins"]
    assert bins["front 0.2-0.3"] > 0 and bins["front 0.9-1.0"] > 0, bins
    assert bins["lateral 0.1-0.2"] == c["teeth_lateral_dark"] and bins["lateral 0.9-1.0"] == c["teeth_lateral_light"], bins
    assert sum(v for k, v in bins.items() if k.startswith("front")) == c["teeth_front"], bins
    assert rec["totals"]["teeth_front"] == c["teeth_front"]


@pytest.mark.skipif(shutil.which("blender") is None, reason="Blender not installed")
def test_the_common_front_reproduces_the_split_of_2026_11_02(tmp_path):
    rec = run(tmp_path, "--front-ref", "common", "--front-mm", "8", "--half-width-mm", "12")
    assert rec["front_ref"] == "common"
    assert rec["teeth_split"] == {"HERO_TEETH_UPPER": {"front": [0], "lateral": [1, 2]},
                                  "HERO_TEETH_LOWER": {"front": [0], "lateral": [1, 2]}}
    bins = rec["frames"][0]["shade_bins"]
    assert bins["lateral 0.2-0.3"] > 0 and bins["lateral 0.1-0.2"] > 0, bins
    assert rec["frames"][0]["counts"]["teeth_lateral_dark"] == bins["lateral 0.2-0.3"] + bins["lateral 0.1-0.2"]
