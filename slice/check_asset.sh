#!/usr/bin/env bash
# Run every slice gate on ONE .blend (the contractor's asset scene) — the same chain the
# placeholder passes. Usage, from the repository root:
#
#   slice/check_asset.sh <scene.blend> <output dir> [samples] [scale%] [SHOT]   (defaults 64, 25,
#   SHOT_001 — the criterion-3 gate needs ≥ 64 spp, measured: 8 and 16 spp fail it on the placeholder;
#   the scene must be the named shot's scene, i.e. built with scene_template.py --shot SHOT)
#
# Steps: check_scene → check_silhouette (no see-through hole at the head↔body seam, in the rest
# pose and at the slice's maximum head turn) → check_seam_margin (the head's overlap band lies
# inside the body neck on every frame — ADR-0002 D1 amendment 2026-09-22) → export the shot → check_exports → check_alembic →
# smoke render of the video frames slice/pick_frames.py chooses from the exports (the first frame,
# the fastest head turn, the widest open jaw) and the still (with the lighting probe) → split →
# composite (which applies the post-composite blur) → round-trip → blur-fidelity reference render
# and gate (video only).
#
# CHECK_ASSET_QUICK=1 — an intermediate run for the animator between deliveries: the shot's first
# video frame only, no still, no blur-fidelity reference render (one static frame cannot test a blur). It ends with ASSET_CHECK_QUICK_OK, never ASSET_CHECK_OK: the full
# run is what a delivery needs (contractor Q22, 2026-09-17: one CPU video frame takes ~100 s at
# 64 spp / 25 %).
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
run() { "$@" > "$OUT/last_step.log" 2>&1; rc=$?; grep -E "_OK|_ERROR|_NOT_APPLICABLE|checks_failed|ROUNDTRIP_FRAME|COMPOSITE_FRAME|BLUR_FIDELITY_FRAME|Traceback" "$OUT/last_step.log" | tail -n 6; if [ $rc -ne 0 ]; then echo "STEP FAILED (rc $rc) — full log: $OUT/last_step.log"; exit 2; fi; }
step "1 check_scene"; run blender -b "$BLEND" --python-exit-code 2 -P "$ROOT/slice/check_scene.py"
step "1b check_silhouette"; run blender -b "$BLEND" --python-exit-code 2 -P "$ROOT/slice/check_silhouette.py" -- --out "$OUT/silhouette"
step "1c check_seam_margin"; run blender -b "$BLEND" --python-exit-code 2 -P "$ROOT/slice/check_seam_margin.py" -- --out "$OUT/seam_margin"
step "2 export $SHOT"; run blender -b "$BLEND" --python-exit-code 2 -P "$ROOT/slice/export_shot.py" -- --shot "$SHOT" --out "$OUT/exports"
step "3 check_exports"; run "$PY" "$ROOT/slice/check_exports.py" "$OUT/exports"
step "4 check_alembic"; run "${B[@]}" -P "$ROOT/slice/check_alembic.py" -- --abc "$OUT/exports/proxies.abc" --meta "$OUT/exports/proxies.abc.meta.json"
VFRAMES="$("$PY" "$ROOT/slice/pick_frames.py" "$OUT/exports" 2>"$OUT/pick_frames.err")" || { echo "frame choice failed: $(tail -n 1 "$OUT/pick_frames.err")"; exit 2; }
rm -f "$OUT/pick_frames.err"
case "$VFRAMES" in "$FIRST"|"$FIRST",*) ;; *) echo "frame choice $VFRAMES does not start at the shot's first frame $FIRST"; exit 2;; esac
PROFILES="video still"
if [ "${CHECK_ASSET_QUICK:-}" = "1" ]; then VFRAMES="$FIRST"; PROFILES="video"; echo "QUICK run: first video frame only, no still — not a delivery check"; fi
step "5 render video frames $VFRAMES ($SAMPLES spp, $SCALE %)"; run blender -b "$BLEND" --python-exit-code 2 -P "$ROOT/slice/render_passes.py" -- --shot "$SHOT" --profile video --frames "$VFRAMES" --samples "$SAMPLES" --scale "$SCALE" --probe --out "$OUT/renders"
[ "$PROFILES" = "video" ] || { step "5 render still"; run blender -b "$BLEND" --python-exit-code 2 -P "$ROOT/slice/render_passes.py" -- --shot "$SHOT" --profile still --frames still --samples "$SAMPLES" --scale "$SCALE" --probe --out "$OUT/renders"; }
for prof in $PROFILES; do
  step "6 split $prof"; run "${B[@]}" -P "$ROOT/slice/split_bundles.py" -- "$OUT/renders/$prof" --exports "$OUT/exports"
  step "7 composite $prof"; run "${B[@]}" -P "$ROOT/slice/composite.py" -- "$OUT/renders/$prof"
  # The video profile is blurred after compositing (ADR-0002 D5 amendment 2026-09-22), so it owes
  # criterion 8: the same frames rendered WITH the shutter open are the ground truth the blur is
  # measured against. That reference is also the matte the round-trip integrates against now that
  # the plates are sharp, so it is rendered BEFORE the round-trip. The still profile has shutter 0.
  if [ "$prof" = "video" ] && [ "${CHECK_ASSET_QUICK:-}" != "1" ]; then
    # A reduced scale shrinks the motion too: on a slow shot the gate then cannot tell the blur
    # from no blur, and says so instead of passing quietly (NOT_APPLICABLE, printed and recorded).
    [ "$SCALE" -ge 100 ] && MAYBE="" || MAYBE="--may-be-non-discriminating"
    step "8 blur reference $VFRAMES"; run blender -b "$BLEND" --python-exit-code 2 -P "$ROOT/slice/render_passes.py" -- --shot "$SHOT" --profile video --frames "$VFRAMES" --samples "$SAMPLES" --scale "$SCALE" --blur-reference --out "$OUT/blur_reference"
    step "9 round-trip $prof"; run "${B[@]}" -P "$ROOT/slice/roundtrip.py" -- --exports "$OUT/exports" --renders "$OUT/renders/$prof" --blur-reference "$OUT/blur_reference/video"
    step "10 blur fidelity"; run "${B[@]}" -P "$ROOT/slice/check_blur_fidelity.py" -- --renders "$OUT/renders/video" --reference "$OUT/blur_reference/video" --out "$OUT/blur_fidelity" ${MAYBE:+$MAYBE}
  else
    step "9 round-trip $prof (centre sample only)"; run "${B[@]}" -P "$ROOT/slice/roundtrip.py" -- --exports "$OUT/exports" --renders "$OUT/renders/$prof"
  fi
done
if [ "$PROFILES" = "video" ]; then
  echo; echo "ASSET_CHECK_QUICK_OK — every gate passed on the first video frame of $BLEND, $SHOT ($SAMPLES spp / $SCALE %) — NOT a delivery check: run without CHECK_ASSET_QUICK before delivering"
  exit 0
fi
echo; echo "ASSET_CHECK_OK — every gate passed on $BLEND, $SHOT (smoke settings $SAMPLES spp / $SCALE %; thresholds PROVISIONAL)"
