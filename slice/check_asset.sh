#!/usr/bin/env bash
# Run every slice gate on ONE .blend (the contractor's asset scene) — the same chain the
# placeholder passes. Usage, from the repository root:
#
#   slice/check_asset.sh <scene.blend> <output dir> [samples] [scale%] [SHOT]   (defaults 64, 25,
#   SHOT_001 — the criterion-3 gate needs ≥ 64 spp, measured: 8 and 16 spp fail it on the placeholder;
#   the scene must be the named shot's scene, i.e. built with scene_template.py --shot SHOT)
#
# Steps: check_scene → export the shot → check_exports → check_alembic → smoke render of one
# video frame and the still (with the lighting probe) → split → composite → round-trip.
# Every step prints its own verdict; the script stops at the first failure with exit 2.
# Needs Blender 5.2.1 on PATH and the vendored OCIO config (set here).
set -u
BLEND="${1:?scene.blend}"; OUT="${2:?output dir}"; SAMPLES="${3:-64}"; SCALE="${4:-25}"; SHOT="${5:-SHOT_001}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export OCIO="$ROOT/benchmarks/bakeoff/01J7B000000000000000BAKEXP/slice/ocio/studio-config-v4.0.0_aces-v2.0_ocio-v2.5.ocio"
export CYCLES_METAL_DISABLE_BINARY_ARCHIVES=1
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY=python3
B=(blender -b --python-exit-code 2)
mkdir -p "$OUT"
FIRST="$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['shots'][sys.argv[2]]['frame_range']['start'])" "$ROOT/slice/conventions.json" "$SHOT" 2>"$OUT/shot_lookup.err")" || { echo "shot lookup failed for $SHOT (slice/conventions.json → shots): $(tail -n 1 "$OUT/shot_lookup.err")"; exit 2; }
rm -f "$OUT/shot_lookup.err"
step() { echo; echo "=== $1"; }
echo "=== 0 environment"
command -v blender >/dev/null || { echo "blender is not on PATH — install Blender 5.2.1 LTS (REBUILD.md step 1)"; exit 2; }
blender --version 2>/dev/null | head -n 1
"$PY" -c "import jsonschema, numpy" 2>/dev/null || { echo "Python deps missing for $PY — run:  python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt   (or: python3 -m pip install -r requirements-dev.txt)"; exit 2; }
[ -f "$OCIO" ] || { echo "vendored OCIO config missing at $OCIO"; exit 2; }
echo "python: $PY; OCIO: $(basename "$OCIO")"
run() { "$@" > "$OUT/last_step.log" 2>&1; rc=$?; grep -E "_OK|_ERROR|checks_failed|ROUNDTRIP_FRAME|COMPOSITE_FRAME|Traceback" "$OUT/last_step.log" | tail -n 6; if [ $rc -ne 0 ]; then echo "STEP FAILED (rc $rc) — full log: $OUT/last_step.log"; exit 2; fi; }
step "1 check_scene"; run blender -b "$BLEND" --python-exit-code 2 -P "$ROOT/slice/check_scene.py"
step "2 export $SHOT"; run blender -b "$BLEND" --python-exit-code 2 -P "$ROOT/slice/export_shot.py" -- --shot "$SHOT" --out "$OUT/exports"
step "3 check_exports"; run "$PY" "$ROOT/slice/check_exports.py" "$OUT/exports"
step "4 check_alembic"; run "${B[@]}" -P "$ROOT/slice/check_alembic.py" -- --abc "$OUT/exports/proxies.abc" --meta "$OUT/exports/proxies.abc.meta.json"
step "5 render video frame $FIRST ($SAMPLES spp, $SCALE %)"; run blender -b "$BLEND" --python-exit-code 2 -P "$ROOT/slice/render_passes.py" -- --shot "$SHOT" --profile video --frames "$FIRST" --samples "$SAMPLES" --scale "$SCALE" --probe --out "$OUT/renders"
step "5 render still"; run blender -b "$BLEND" --python-exit-code 2 -P "$ROOT/slice/render_passes.py" -- --shot "$SHOT" --profile still --frames still --samples "$SAMPLES" --scale "$SCALE" --probe --out "$OUT/renders"
for prof in video still; do
  step "6 split $prof"; run "${B[@]}" -P "$ROOT/slice/split_bundles.py" -- "$OUT/renders/$prof" --exports "$OUT/exports"
  step "7 composite $prof"; run "${B[@]}" -P "$ROOT/slice/composite.py" -- "$OUT/renders/$prof"
  step "8 round-trip $prof"; run "${B[@]}" -P "$ROOT/slice/roundtrip.py" -- --exports "$OUT/exports" --renders "$OUT/renders/$prof"
done
echo; echo "ASSET_CHECK_OK — every gate passed on $BLEND, $SHOT (smoke settings $SAMPLES spp / $SCALE %; thresholds PROVISIONAL)"
