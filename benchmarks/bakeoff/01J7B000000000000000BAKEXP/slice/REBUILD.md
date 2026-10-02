# Rebuild recipe — Phase 0.5 reference slice

Package: `benchmarks/bakeoff/01J7B000000000000000BAKEXP/slice/` in the git record (the light part) plus its offline part
on the archive disk, `<the archive disk>/package/01J7B000000000000000BAKEXP/slice/` (owner decision
2026-09-29). Master `01J7B000000000000000BAKEM1` v1, contract v5 (ADR-0002 with its amendments to 2026-09-29), channel vocabulary v2 (the gaze target point, amendment 2026-09-30). One file
table and one `package_hash` over both parts (`package_manifest.json`). This file is the D11 rebuild recipe: a stranger
with this package, the repository and the pinned toolchain must be able to rebuild a shot and re-render it.
(Rewritten 2026-09-29 for the delivered shots; the 2026-09-15 recipe described the placeholder at contract v1.)

## Contents

Per shot, `shots/<SHOT>/` — SHOT_001 v02, SHOT_002 v03 (accepted 2026-10-02; its renders aimed at the gaze point, `gaze_aim` TARGET_POINT), SHOT_003 v06:

| Path | Part | What |
|---|---|---|
| `shot_manifest.json` | record | brief §4E: difficulty, occlusion, identity-risk notes, the fourteen passes |
| `source/` | both | the delivered `.blend` (offline), the contractor's build scripts, `DELIVERY.json` (their sha256, the acceptance record) |
| `exports/` | both | the whole shot's exports (`export_shot.py`, 120 frames): socket, camera, joints, performance track, proxies. Re-exported 2026-09-30 at vocabulary v2 (the gaze target point per frame; `export_manifest.json → gaze`); the plates were NOT re-rendered — their `render_manifest → settings.gaze_aim` reads `NONE` (the pair-driven eyes) and the rebuild renders them that way; the default head's eyes turned by the aim would differ by ≤ 0.16° on every rendered frame (SHOT_001's named-target frames 1023–1027 are not in the package) |
| `renders/video/`, `renders/still/` | both | the conformant renders `check_asset.sh` chose (the first frame, the fastest head, the widest jaw; the still frame), split into HEAD_RENDER_BUNDLE and COMPOSITE_BUNDLE, the derived precomp, the round-trip reports, `raw/` |
| `qc/` | both | the blur-fidelity reference and report (criterion 8), silhouette, seam margin, the `check_asset.sh` log |
| `order_qc/` | both | the default head's order composite of each profile (`composite_order.py`) — where `t_comp` and `S_frame` come from |

`channel_reference/` — the channel reference renders of ADR-0002 D8 (`slice/channel_reference.py` on SHOT_001 v02's default head, 2026-10-02): `channel_reference.json` in the record, the 86 renders and two sheets offline. `warmup/warmup.json` — the worker warm-up measurement. Text files up to 512 KB are in the record; everything else is
offline at the same relative path. The full-range render of every frame is NOT in the package yet (owner, 2026-09-29:
before the bake-off starts; SHOT_002 v03 is in since 2026-10-02).

## Steps

1. **Toolchain** — exactly `../../../../slice/toolchain.lock.json`: Blender 5.2.1 LTS (build 9e2066aef7ef), OpenImageIO
   3.1.17, OpenColorIO 2.5.2; MPFB2 2.0.17 at commit 80919fa (the contractor's `LICENSES.md`), installed into an isolated
   profile by the rebuild itself. PINNED 2026-09-15.
2. **Environment** — `export OCIO=$PWD/ocio/studio-config-v4.0.0_aces-v2.0_ocio-v2.5.ocio` (vendored here; sha256 in
   the lock and in `package_manifest.json`). VENDORED.
3. **Verify the package** — `.venv/bin/python slice/package.py verify <pkg> --offline <offline>` must print
   `PACKAGE_VERIFIED` (without `--offline`: `PACKAGE_VERIFIED_LIGHT`, the offline files NOT CHECKED — what CI runs).
4. **Rebuild a shot from its source** — `.venv/bin/python slice/rebuild_from_package.py --pkg <pkg> --offline <offline>
   --shot SHOT_003 --out <fresh dir>`: scene template → the archived scripts (scanned; hashes against `DELIVERY.json`)
   `build_character.py` → `make_shot_00N.py` → `animate_shot_00N.py` → the rebuilt `.blend` against the archived one
   (content within `conventions.json → rebuild → cross_platform_tolerance`) → exports against the archived exports →
   the archived frames rendered again at the archived settings (`gaze_aim` included: `--exports` only when the archived plates were aimed) → split → composite → every bundle part against the
   archived render (`slice/compare_renders.py`), with the frames shifted as the negative control. Record:
   `<fresh dir>/rebuild_report.json`.
5. **Re-render and check a shot from scratch** — `CHECK_ASSET_STILL_SAMPLES=256 slice/check_asset.sh <shot .blend>
   <out> 64 100 <SHOT>` (both profiles conformant; must end `ASSET_CHECK_OK`), then the default head's order composite
   per profile: `composite_order.py default-head-inputs` and `compose --record-default-head-reproduction`.
6. **Package a shot** — `.venv/bin/python slice/package_add_shot.py --pkg <pkg> --offline <offline> --shot <SHOT> --run
   <out>/check --source-blend … --scripts … --record … --order-qc …` (`--replace` for a new version), then
   `.venv/bin/python slice/package.py hash <pkg> --offline <offline>` and update `../master.json → package_hash`
   (`tests/test_bakeoff_record.py` fails until it matches).

## Per-order composite (the consumer of this package, not a rebuild step)

`blender -b --python-exit-code 2 -P slice/composite_order.py -- compose --bundle <renders/<profile>> --head-layer <dir>
--shadow-multiply <dir> --order-id <id> --out <dir>` — refuses a bundle whose precomp reproduction or round-trip has not
PASSed; records `t_comp` and the bytes it reads per frame. It applies no motion blur yet (Phase 0.5 exit review, step 5).
