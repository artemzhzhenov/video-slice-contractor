"""Which objects are the default head's eyes (conventions → scene_naming.eyes → resolution). Blender side only.

The asset's eyes when the scene has them, the placeholder template's when it has only those; both sets, or neither, is an
error — never a silent pick (found 2026-10-02: template eyes named like the asset's survived a character build)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
E = json.loads((ROOT / "slice" / "conventions.json").read_text())["scene_naming"]["eyes"]


class EyesError(RuntimeError):
    pass


def eye_objects(objects):
    """objects: bpy.data.objects. Returns (the two eye objects, "ASSET" | "TEMPLATE")."""
    asset = [objects.get(n) for n in E["objects"]]
    tmpl = [objects.get(n) for n in E["template_objects"]]
    has_a, has_t = any(o is not None for o in asset), any(o is not None for o in tmpl)
    if has_a and has_t:
        raise EyesError(f"both the asset's eyes {E['objects']} and the template's {E['template_objects']} are in the scene — "
                        "a character build must remove the template's PLACEHOLDER_* objects")
    eyes, kind = (asset, "ASSET") if has_a else (tmpl, "TEMPLATE")
    if any(o is None for o in eyes):
        raise EyesError(f"the default head has no eye objects ({E['objects']} or, in the template, {E['template_objects']}) — "
                        "the gaze target point (vocabulary v2) is derived from them and aimed at them")
    return eyes, kind
