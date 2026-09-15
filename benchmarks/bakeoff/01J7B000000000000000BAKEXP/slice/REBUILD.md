# Rebuild recipe — Phase 0.5 reference slice (2026-09-15; assets pending)

Package: `benchmarks/bakeoff/01J7B000000000000000BAKEXP/slice/`. Master `01J7B000000000000000BAKEM1`
v1, contract v1 (ADR-0002). This file is the D11 rebuild recipe; a stranger with this directory
and the pinned toolchain must be able to re-render one shot. Each step below is filled in as the
step exists; a step that is not yet executable says so.

1. Toolchain — install exactly the versions in `../../../../slice/toolchain.lock.json`:
   Blender 5.2.1 LTS (build 9e2066aef7ef), OpenImageIO 3.1.17, OpenColorIO 2.5.2. On macOS:
   `brew install --cask blender && brew install openimageio opencolorio`, then confirm the
   versions match the lock. PINNED 2026-09-15.
2. Environment — `export OCIO=$PWD/ocio/studio-config-v4.0.0_aces-v2.0_ocio-v2.5.ocio` (vendored
   in this package; sha256 in the lock and in `package_manifest.json`). VENDORED.
3. Scene — from the repository root:
   `blender -b --python-exit-code 2 -P slice/scene_template.py -- --out <pkg>/template.blend --shot SHOT_001`
   then `blender -b <pkg>/template.blend --python-exit-code 2 -P slice/check_scene.py` must exit 0.
   EXECUTABLE — last run 2026-09-15, zero failed checks (`slice/measurements/check_scene.json`).
4. Assets — character, default head, hair, environment: NOT YET DELIVERED (rigger burst 1).
5. Animation and performance track — NOT YET DELIVERED (burst 2). The export step already runs
   on the placeholder rig: `blender -b <pkg>/template.blend --python-exit-code 2 -P slice/export_shot.py -- --shot SHOT_001 --out <pkg>/shots/SHOT_001/exports`,
   then `.venv/bin/python slice/check_exports.py <pkg>/shots/SHOT_001/exports` and
   `blender -b --python-exit-code 2 -P slice/check_alembic.py -- --abc … --meta …` must exit 0.
   EXECUTABLE — last run 2026-09-15, zero failed checks on all three.
6. Render — from the repository root, per profile:
   `blender -b <pkg>/template.blend --python-exit-code 2 -P slice/render_passes.py -- --shot SHOT_001 --profile video --frames all --probe --out <pkg>/shots/SHOT_001/renders`
   and `--profile still` (frames from `slice/state_map.json`). Then
   `blender -b --python-exit-code 2 -P slice/split_bundles.py -- <pkg>/shots/SHOT_001/renders/<profile> --exports <pkg>/shots/SHOT_001/exports`
   writes the two bundles, and
   `blender -b --python-exit-code 2 -P slice/composite.py -- <pkg>/shots/SHOT_001/renders/<profile>`
   derives HEAD_SHADOW_MULTIPLY, SKIN_ID and the precomp pair and writes the reproduction report;
   `blender -b --python-exit-code 2 -P slice/roundtrip.py -- --exports <pkg>/shots/SHOT_001/exports --renders <pkg>/shots/SHOT_001/renders/<profile>`
   runs the D7 round-trip and records its status in the bundle manifest.
   EXECUTABLE — smoke-verified 2026-09-15 at 10 % / 8 samples on the placeholder scene; a
   conformant render (100 %, profile samples) of the placeholder is ~6 min per video frame on
   this machine (`slice/measurements/test_frame.json`), so full-range renders wait for the
   real asset and the render-time decision in PROJECT_STATE.
7. Package — `.venv/bin/python slice/package.py hash <pkg>` writes `package_manifest.json`
   (sha256 + bytes per file, per-shot entries from the export and bundle manifests, toolchain and
   OCIO hash from the lock, `package_hash`); `.venv/bin/python slice/package.py verify <pkg>`
   recomputes and exits 2 on any missing / added / changed file. EXECUTABLE — CI verifies this
   directory as committed; the placeholder's regenerable content (template, exports, renders) is
   not committed and is not in the committed manifest — it is rebuilt by step 8 into a fresh
   directory until the real asset is archived here.
8. Verify — precomp reproduction (`precomp_report.####.json`, step 6), round-trip
   (`roundtrip_report.<profile>.json`, step 6) and the test-rebuild of one shot:
   `.venv/bin/python slice/rebuild_shot.py --pkg <pkg> --shot SHOT_001 --out <fresh dir> [--smoke 64 10] [--frames 1001-1010]`
   runs steps 3, 5, 6 (including the round-trip) and 7 into `<fresh dir>`, records every step
   in `rebuild_report.json` (also on failure), and compares with the archive: export files must
   hash-identically (`proxies.abc` through its geometry hash — the Alembic header carries a
   write date); render parts are compared by pixel SHA-1 and the differing ones listed (Metal
   is not bit-exact). An archive with nothing to compare gives `NOT COMPARED` and exit 2
   unless `--no-archive` is passed and recorded; render settings must equal the archive's.
   The record is `<fresh dir>/rebuild_report.json`; copying it to
   `slice/measurements/rebuild_SHOT_001.json` (absolute scratch paths replaced by `<scratch>`)
   is a manual step of this recipe. EXECUTABLE — last run 2026-09-15 at smoke settings, second
   run against the first.

Per-order composite (not a rebuild step; the consumer of this package):
`blender -b --python-exit-code 2 -P slice/composite_order.py -- compose --bundle <pkg>/shots/SHOT_001/renders/<profile> --head-layer <dir> --shadow-multiply <dir> --order-id <id> --out <dir>`
— refuses a bundle whose precomp reproduction or round-trip has not PASSed.
