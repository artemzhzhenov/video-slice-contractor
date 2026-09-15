"""Re-import proxies.abc into an empty Blender scene and prove it carries per-frame geometry:

    blender -b --python-exit-code 2 -P slice/check_alembic.py -- --abc <exports>/proxies.abc --meta <exports>/proxies.abc.meta.json

Asserts every proxy object named in the meta file exists after import and that at least one
proxy's vertex positions differ between the first and last frame (the placeholder rig sways the
spine for exactly this reason). Exit 1 with the failures otherwise."""
import argparse
import json
import sys

import bpy


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--abc", required=True)
    p.add_argument("--meta", required=True)
    args = p.parse_args(argv)
    meta = json.load(open(args.meta))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.alembic_import(filepath=args.abc, as_background_job=False, set_frame_range=False)
    fails = []
    names = {o.name for o in bpy.data.objects}
    for want in meta["proxy_objects"]:
        if want not in names:
            fails.append(f"{want} not in imported objects {sorted(names)}")
    scene = bpy.context.scene
    f0, f1 = meta["frames"]
    moved = False
    dg = bpy.context.evaluated_depsgraph_get()
    for name in meta["proxy_objects"]:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            continue
        scene.frame_set(f0); dg.update()
        ev = obj.evaluated_get(dg)
        a = [tuple(round(c, 5) for c in (ev.matrix_world @ v.co)) for v in ev.data.vertices]
        scene.frame_set(f1); dg.update()
        ev = obj.evaluated_get(dg)
        b = [tuple(round(c, 5) for c in (ev.matrix_world @ v.co)) for v in ev.data.vertices]
        if not a:
            fails.append(f"{name}: no vertices after import")
        if a != b:
            moved = True
    if not moved:
        fails.append("no proxy vertex moved between the first and last frame — the cache carries no animation")
    print(json.dumps({"imported": sorted(names), "checks_failed": fails}, indent=1))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
