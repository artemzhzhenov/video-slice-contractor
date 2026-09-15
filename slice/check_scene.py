"""Reopen a template .blend headless and assert the structure the pass table depends on.

    blender -b <file.blend> -P slice/check_scene.py -- --json out.json

Exit 0 when every check holds; exit 1 with the failing checks listed. This is the test of
scene_template.py; it reads conventions.json so the two cannot drift apart silently."""
import argparse
import json
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
N = CONV["scene_naming"]

EXPECT_LAYER = {
    "L_BODY": {"C_HEAD": "exclude", "C_HAIR": "exclude", "C_HAND_FG": "indirect_only"},
    "L_BODYSHADOW": {"C_HEAD": "indirect_only", "C_HAIR": "indirect_only", "C_HAND_FG": "indirect_only"},
    "L_HEAD": {"C_BODY": "holdout", "C_HAND_FG": "indirect_only", "C_ENV": "holdout"},
    "L_FG": {"C_HEAD": "holdout", "C_HAIR": "holdout", "C_BODY": "holdout", "C_ENV": "holdout"},
}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--json", default="")
    args = p.parse_args(argv)
    scene = bpy.data.scenes.get("SLICE")
    fails = []
    ok = lambda cond, msg: None if cond else fails.append(msg)  # noqa: E731
    ok(scene is not None, "scene SLICE missing")
    if scene is None:
        print("\n".join(fails)); sys.exit(1)
    ok(scene.render.fps == CONV["fps"], f"fps {scene.render.fps}")
    ok(scene.frame_start >= 1001, f"frame_start {scene.frame_start}")
    ok(scene.render.engine == "CYCLES", f"engine {scene.render.engine}")
    ok(tuple(CONV["render_profiles"]["video"]["resolution"]) == (scene.render.resolution_x, scene.render.resolution_y), "resolution")
    ok(scene.render.film_transparent, "film_transparent off")
    ok(scene.render.image_settings.file_format == "OPEN_EXR_MULTILAYER", "not multilayer EXR")
    ok(scene.render.image_settings.color_depth == "16", "beauty depth not half")
    ok(scene.unit_settings.scale_length == 1.0, "unit scale")
    ok(not scene.cycles.use_adaptive_sampling and not scene.cycles.use_animated_seed, "sampling not deterministic")
    for c in N["collections"]:
        ok(c in bpy.data.collections, f"collection {c} missing")
    for m in N["materials"]:
        ok(m in bpy.data.materials, f"material {m} missing")
    for e in N["empties"]:
        ok(e in bpy.data.objects and bpy.data.objects[e].type == "EMPTY", f"empty {e} missing")
    ok(scene.camera is not None and scene.camera.name == N["camera"], "camera")
    ok([vl.name for vl in scene.view_layers] == N["view_layers"], f"view layers {[vl.name for vl in scene.view_layers]}")
    for vl in scene.view_layers:
        exp = EXPECT_LAYER.get(vl.name, {})
        for c in N["collections"]:
            lc = vl.layer_collection.children.get(c)
            if lc is None:
                fails.append(f"{vl.name}: {c} not in layer"); continue
            want = exp.get(c)
            ok(lc.exclude == (want == "exclude"), f"{vl.name}/{c} exclude={lc.exclude}")
            ok(lc.holdout == (want == "holdout"), f"{vl.name}/{c} holdout={lc.holdout}")
            ok(lc.indirect_only == (want == "indirect_only"), f"{vl.name}/{c} indirect_only={lc.indirect_only}")
        ok(not vl.use_pass_normal, f"{vl.name}: normal pass on (not in base set)")
    full = scene.view_layers["L_FULL"]; data = scene.view_layers["L_DATA"]
    ok(full.use_pass_cryptomatte_object and full.use_pass_cryptomatte_material, "L_FULL cryptomatte")
    ok(data.use_pass_z and data.use_pass_vector, "L_DATA z/vector")
    # Head is a shadow-caster only (ADR-0002 D2 amendment): checked on every object in C_HEAD/C_HAIR.
    for cname in ("C_HEAD", "C_HAIR"):
        for obj in bpy.data.collections[cname].all_objects:
            ok(obj.visible_shadow and obj.visible_camera and not obj.visible_diffuse and not obj.visible_glossy and not obj.visible_transmission,
               f"{obj.name}: ray visibility is not shadow-caster-only")
    rig = bpy.data.objects.get(N["rig"])
    ok(rig is not None and rig.type == "ARMATURE", "rig missing")
    if rig is not None:
        for b in N["bones"]["spine"] + [N["bones"]["neck"], N["bones"]["head"], N["bones"]["shoulder_l"], N["bones"]["shoulder_r"]]:
            ok(b in rig.pose.bones, f"bone {b} missing")
    sock = bpy.data.objects.get("SOCKET_HEAD")
    ok(sock is not None and sock.parent is rig and sock.parent_type == "BONE" and sock.parent_bone == N["bones"]["neck"], "SOCKET_HEAD not bone-parented to the neck")
    prox = bpy.data.collections.get(N["proxies_collection"])
    ok(prox is not None, "C_PROXIES missing")
    if prox is not None:
        names = {o.name for o in prox.objects}
        ok(set(N["proxies"]) <= names, f"proxies {names}")
        ok(all(o.hide_render for o in prox.objects), "a proxy is renderable")
    ctrl = bpy.data.objects.get(N["face_ctrl"])
    cmap = json.loads((ROOT / "slice" / "channel_map.json").read_text())
    ok(ctrl is not None and all(ch["channel"] in ctrl.keys() for ch in cmap["channels"]), "FACE_CTRL missing a channel property")
    # Socket boundary vertex group exists on the body placeholder.
    body_objs = [o for o in bpy.data.collections["C_BODY"].all_objects if o.type == "MESH"]
    ok(any(N["vertex_group_socket_boundary"] in o.vertex_groups for o in body_objs), "SOCKET_BOUNDARY vertex group missing on body")
    ok(scene.get("scene_linear") == CONV["colour"]["working_space"], f"scene linear is {scene.get('scene_linear')!r}, not {CONV['colour']['working_space']} — is $OCIO set to the vendored config?")
    report = {"blender": bpy.app.version_string, "device": scene.get("render_device"), "shutter_position_api": scene.get("shutter_position_api"),
              "view_transform": scene.get("view_transform"), "display_device": scene.get("display_device"), "scene_linear": scene.get("scene_linear"),
              "ocio_env": scene.get("ocio_config_env"), "checks_failed": fails}
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
