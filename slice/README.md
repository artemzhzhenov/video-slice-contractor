# Phase 0.5 slice — tooling

Agent-owned pipeline share of the reference slice (owner decision 2026-09-15, proposal §7
Option B). Everything here is FREE work: no render farm, no asset purchase, no external call.
Authority: ADR-0002 → `docs/experiments/phase-0-5-slice-brief.md` → `…-proposal.md` → this.

| File | What it is |
|---|---|
| `conventions.json` | Every convention the scripts read: fps, frame ranges, resolutions, colour, EXR, alpha declaration per pass, scene naming, head lighting rule. Fixed items cite ADR-0002 D6; TD-set items are marked PROVISIONAL. |
| `toolchain.lock.json` | Pinned Blender / OIIO / OCIO / ACES config versions with hashes. Written by `pin_toolchain.sh`; a version not in this file is not the slice's toolchain. Pinned 2026-09-15: **Blender 5.2.1 LTS** (not the 4.x the proposal assumed — API differences are handled in the scripts and noted below), OIIO 3.1.17, OCIO 2.5.2, ACES studio config v4.0.0. |
| `pin_toolchain.sh` | Regenerates the lock from what is installed. Run deliberately; a diff is a toolchain change. |
| `scene_template.py` | Builds the scene skeleton headless: collections, materials, six view layers with exclusion / holdout / indirect-only, pass flags, render and output settings, socket empties, camera, `PLACEHOLDER_*` geometry. |
| `check_scene.py` | Reopens a template `.blend` and asserts the structure against `conventions.json`. Exit 1 lists what drifted. |
| `render_test_frame.py` | One 4K frame, two render groups (beauty with blur, data without), wall-clock and channel types recorded. A machine baseline, explicitly not `S_frame`. |
| `socketspace.py` | The one piece of maths every exporter shares: Blender world → socket space (right-handed, +Y up, +Z forward, +X anatomical left), relative to `SOCKET_SPACE_ROOT`. Two conversions, on purpose: the **similarity** `C·T·C⁻¹` for the socket (its local frame becomes socket-oriented — identity at rest) and the **left-multiply** `C·T` for the camera and the bones (their own local frames are kept: camera −Z forward, bone +Y along the bone). Quaternion (x, y, z, w) with w ≥ 0; the measured scale is reported and a scale or mirror violation raises. Pure Python, unit-tested in CI. |
| `channel_map.json` | Channel vocabulary v1 — 26 project-owned channels with ranges and semantics (proposal §5); maps a rig control to a channel, linearly. The placeholder rig uses one custom property per channel on `FACE_CTRL`; a real rig maps its own controls here. |
| `state_map.json` | The fifteen states as frame windows per shot with editorial labels and the three still frames — PROVISIONAL (proposal §5); the animator's burst finalises the windows. |
| `export_shot.py` | Exports one shot's `HEAD_RENDER_BUNDLE` data (ADR-0002 D5 rows 6, 7, 8, 11, 12): `camera.json` (per-frame intrinsics with fx/fy and a sign-verified principal point, extrinsics with sub-frame samples), `socket.json` and `joints.json` (sub-frame samples), `socket_boundary.json` (ordered rings on head and body, rest gap, the first PROVISIONAL envelope), `lighting_ref.json`, `performance_track.json` (validates against `schemas/performance_track.json`), `proxies.abc` + meta with the `abc_to_socket` matrix, `proxies_rest.obj`, `default_head_rest.obj` (every renderable mesh of `C_HEAD` ∪ `C_HAIR` in the socket's local frame — what the round-trip re-projects and the head technology's envelope reference), `export_manifest.json` with sha256 per file and the root matrix everything is relative to. `camera.json` carries pixel intrinsics per render profile (`px_by_profile`): the still's principal point is not the video's. Asserts the scene's units, fps, shutter and pixel aspect against `conventions.json` before exporting; cleans the output directory first. |
| `check_exports.py` | Validates an export directory outside Blender with load-bearing checks: file set and manifest hashes, no NaN token, schema, frame coverage, sub-frame offsets and that the samples are actually distinct, measured scale, proper rotations, frame-to-frame continuity (jumps and hemisphere flips fail), intrinsics-constant flag vs data, joints complete and proper, boundary rings equal and coincident at rest, lighting present, Alembic and OBJ non-empty, track socket rows equal to the socket file's centre samples. |
| `check_alembic.py` | Re-imports `proxies.abc` into an empty Blender and proves it carries per-frame geometry. |
| `render_passes.py` | Renders one shot for one profile in two groups — beauty layers with the profile's shutter, `L_DATA` with blur off — as raw multilayer EXRs per frame, plus the lighting probe (chrome and grey balls at the socket, hero excluded) on request; writes `render_manifest.<profile>.json` with settings, device, per-frame seconds and bytes, hashes. Never saves the scene. `--samples/--scale` overrides mark the output `smoke_test_only`. |
| `split_bundles.py` | Splits the raw EXRs into `HEAD_RENDER_BUNDLE/holdout.####.exr` and `COMPOSITE_BUNDLE/composite.####.exr` through the OpenImageIO API under Blender's Python, parts named and typed per `conventions.json → bundles` (half for beauty, float for cryptomatte, depth, vectors), `cryptomatte/*` manifests carried onto every `CRYPTO_*` part and re-parsed as JSON, `slice:alpha` / `slice:pass` on every part; re-reads every written part and requires exact equality with the source after the declared quantization; records `bytes_per_frame` and a pixel SHA-1 per part in `bundle_manifest.<profile>.json`; copies the HEAD_RENDER plus files (exports, probe). |
| `composite.py` | Derives `HEAD_SHADOW_MULTIPLY` (shadowed ÷ body with a declared epsilon, clipped fraction reported), `SKIN_ID` / `SKIN_ID_HEAD` / `SKIN_ID_BODY` from the material cryptomatte, `PRECOMP_BACK` / `PRECOMP_FRONT`, and runs the precomp-reproduction test (ADR-0002 §Validation 3) — `FRONT over (HEAD over BACK)` against the full render, error fractions inside and outside a 2-px boundary band, PROVISIONAL tolerances — writing `derived.####.exr` and `precomp_report.####.json`. |
| `camera_model.py` | Pinhole intrinsics from Blender camera data (fit rules, shift signs, per-profile pixel values) and the projection, pure Python, unit-tested in CI. Used by the exporter and the round-trip. |
| `matte_metrics.py` | The round-trip's rasteriser (4×4 supersampled box coverage), the edge band shared with `composite.py`, and the silhouette metrics (p95 symmetric boundary distance, centroid, IoU, band coverage difference) — numpy only, unit-tested on synthetic mattes in CI. |
| `roundtrip.py` | **D7 round-trip test.** Loads no scene: places `default_head_rest.obj` by `socket.json`, sees it through `camera.json`, integrates 9 samples across the shutter (slerp between the exported sub-frame samples), rasterises, and compares with `HEAD_HOLDOUT`. PROVISIONAL gate from `conventions.json → roundtrip` (1 px p95 / 0.5 px centroid / IoU 0.995 at profile resolution; STRESS window looser), exit 2 on FAIL. Runs the negative controls on every frame: a 5-px screen shift of the socket MUST fail the gate (else the metric is NOT VALIDATED and the script exits 2); a 3° yaw is reported VALIDATED / NOT_VALIDATED. `--ignore-subframes` is the positive control. Writes `roundtrip_report.<profile>.json` and the status into the bundle manifest. |
| `composite_order.py` | **Per-order composite entry point.** `FINAL = PRECOMP_FRONT over (HEAD_LAYER over (BODY_BEAUTY × SHADOW_MULTIPLY_ORDER))` from a head technology's `head.####.exr` (premultiplied, colour declared) and `shadow.####.exr`; refuses to run on a bundle whose precomp reproduction or round-trip has not PASSed; gates on the layer filling `HEAD_HOLDOUT`; never substitutes the default head's multiply. `default-head-inputs` writes the master's own head layer and multiply in the same layout, so the entry point is checked against `DEFAULT_HEAD_BEAUTY`. `order_composite_manifest.json` carries input hashes and `fallbacks: []`. |
| `package.py` | Content-addressed package (D11): `hash` writes `package_manifest.json` with sha256 + bytes of every file, per-shot entries derived from the export and bundle manifests (their hashes re-checked against disk — stale files refuse to package), toolchain and OCIO from the lock (hash verified), `package_hash`; `verify` recomputes and fails on any missing / added / changed file. CI verifies the committed package. |
| `rebuild_shot.py` | Test-rebuild of one shot from the archived source (REBUILD.md step 8): runs every step into a fresh directory, records each step's exit code and wall-clock, then compares the fresh exports with the archive's by hash (must be identical) and the render bundle parts by pixel SHA-1 (identical / differing counted and listed). |
| `check_asset.sh` | One command for a delivered scene: check_scene → export → check_exports → check_alembic → smoke render (64 spp / 25 %, the criterion-3 gate needs ≥ 64 spp) → split → composite → round-trip; stops at the first failing gate. The contractor's self-check and our acceptance (`contractor/burst-1/ACCEPTANCE.md`). |
| `accept_delivery.py` | ACCEPTANCE item 5 as one command: MPFB2 from the declared git ref (or zip), built and installed into an isolated Blender profile under the run directory (extensions, config, scripts, datafiles; version and commit verified against LICENSES.md); the judging tools (slice/, schemas/, scripts/, the OCIO config) fingerprinted before the build and re-checked after it, byte-code caches under those trees deleted before the fingerprint and required absent after the build (Blender's embedded Python ignores `PYTHONDONTWRITEBYTECODE`, so a planted `.pyc` is caught by presence); the template from `scene_template.py` at the commit named in REPORT.md; the contractor's `build_character.py` copied into the run directory with every sibling file (all recorded by sha256), scanned by logical line of code tokens, comments and docstrings removed, for the module and operator forms of what a rebuild never needs (opening or appending another `.blend`, processes, network, file-copy modules, dynamic imports, `exec`/`eval`, `wm` operators resolved at run time; bare words like a `socket` variable are not hits — measured on `scene_template.py`, whose only hit is its legitimate `read_factory_settings`; a hit blocks unless `--allow-scan-hits`, which caps the verdict at PARTIAL) and run there (must print `BUILD_OK`; the delivered file must be unchanged afterwards; the rebuilt bytes must differ from the delivered ones); the template script's content must exist in this repository's history; `check_scene` on both files; `check_asset.sh` on both; the shot's exports of both compared by `rebuild_shot.compare_exports` with the cross-platform tolerance (non-identical JSON/OBJ files numerically, `proxies.abc` by `compare_alembic.py`); `blend_content_hash.py` on both, and when the hashes differ the original-order dumps compared within the same tolerance, differing objects and fields named. Measured on the contractor's v01 (Linux CPU build vs macOS Metal rebuild): every number within 3.6e-7, verdict OK. Verdict `ACCEPTANCE_REBUILD_OK` (exit 0; needs a git MPFB2 source at the declared commit and the asset check) / `_PARTIAL` (exit 3: asset check skipped, or MPFB2 not installed / commit unverifiable) / `_FAIL` (exit 2) / 64 usage error; `acceptance_report.json` with every step's exit code and log. Not a sandbox: a script that assembles an operator name at run time, opens the delivery and saves it as the rebuilt file passes every automated check (bytes differ, content equal by construction); the copied scripts' sha256 are recorded and a human reads them. Tested on the placeholder: identity build with a test-double MPFB2 from a local git repo and the asset check → OK without touching the user's Blender profile; no asset check or zip source → PARTIAL; tampered delivery → FAIL naming the object; a script opening another `.blend` → FAIL before running; an obfuscated byte copy → FAIL; a script overwriting the delivery → FAIL; a script planting a file under `schemas/` → FAIL by the fingerprint, a planted `.pyc` under `scripts/` → FAIL by presence (both Blender-gated, local evidence); no `BUILD_OK` → FAIL; MPFB2 version or commit mismatch → FAIL; another shot's scene → FAIL at export; usage errors → 64. |
| `blend_content_hash.py` | Content hash of a `.blend` scene (what it means, not its bytes): canonicalised mesh geometry (ties between coincident vertices broken by their neighbours), vertex groups, shape keys, armature bones with full orientation, pose-bone constraints and IK, object constraints and modifiers with their RNA parameters, custom properties with their limits, materials' nodes and packed textures by sha256, animation curves and **drivers**; per-object hashes in a JSON so a difference is located. Tested: two template builds hash equal; a moved vertex, a renamed bone, a driver, a constraint, a bone roll, a hard limit or a swapped texture each change it and are located. Gaps found by the contractor's review (Q12) closed 2026-09-16. `mesh_data` (2026-09-16, hash rule version): per-mesh {hash, collections, objects, materials}, the hash over geometry, shape keys and every user's vertex groups but not transform, parent or pose — measured: a neck pose key moves the socket children's object hashes and leaves `mesh_data` intact, a vertex-group change moves the mesh entry; this is the burst-2 "character unchanged" rule. `--dump` writes the content in Blender's own vertex order (order-sensitive, not what is hashed) for the cross-machine numeric comparison — the canonical order flips under float noise for near-tied vertices; machine-derived scene props `render_device` and `ocio_config_env` are excluded from the hash (2026-09-16). |
| `check_states.py` + `state_requirements.json` | Burst-2 gate "states reached" (contractor/burst-2/ACCEPTANCE.md item 3), from the exports only: per state window of `state_map.json`, channel peaks, head angle to the camera (socket +Z vs the direction to the camera, socket space), angular velocity against the animator-declared T (`head_angular_velocity_threshold_deg_s` in state_map.json — NOT_EVALUATED until declared, verdict at most PARTIAL), a hold / endpoints / range rule per state, the strong-light colour ratio from `lighting_ref.json`, and a freeze rule over the whole shot (> 12 frames with no channel, socket position or rotation change). Human items (hand fraction, shadow picture, liveliness) are listed, never evaluated. Verdict STATES_OK / PARTIAL / FAIL with the window, rule and measured value. Tested on synthetic exports (meeting every minimum → OK with T, PARTIAL without; flat → FAIL by freeze and every peak; no turn → SHOT_002 profile/turn/hold FAIL) and on the placeholder: SHOT_002 and SHOT_003 FAIL, SHOT_001 passes — the SHOT_001 minimums were written from the template's own test ramps, so SHOT_001 is the weakest window of this gate and the acting judgement there is the owner's. |
| `content_compare.py` | Numeric comparison of two JSON trees within the declared absolute tolerance (`conventions.json` → `rebuild.cross_platform_tolerance`, 1e-5, MEASURED basis): same shape, identical non-numeric leaves, every number within the tolerance; reports the largest deviation and the first differing paths. Used on export JSON files and on the content dumps. CI-tested. |
| `compare_alembic.py` | Two `proxies.abc` compared numerically under Blender: every proxy object at every frame and sub-frame offset, every vertex within the tolerance (the meta's geometry hash rounds at 1e-6 and flips under cross-machine float noise). `ALEMBIC_COMPARE_OK max_dev=…` or FAIL naming object, frame, offset, vertex. |
| `cryptomatte.py` | Pure-Python id decoding (hex → the float32 the rank channels carry, per the Cryptomatte spec), unit-tested in CI. |
| `measurements/` | JSON outputs of the scripts above, committed; renders and placeholder exports are not (`.gitignore`). |

## How the pass table maps to Blender

- **Head is a shadow-caster only** (ADR-0002 D2 amendment): object ray visibility on every
  object in `C_HEAD` / `C_HAIR` — camera on, shadow on, diffuse / glossy / transmission off.
  This is what makes `L_BODYSHADOW` (head and hair `indirect_only`) a pure shadow layer and the
  precomp reproducible.
- **`L_BODY`** excludes head and hair (pass 1). **`L_HEAD`** holds out everything else (pass 2
  cross-check). **`L_FG`** renders only `C_HAND_FG` (pass 4). **`L_FULL`** carries object and
  material cryptomatte (passes 2, 10). **`L_DATA`** carries Z and Vector and is rendered in a
  second invocation with motion blur off (passes 5, 14) — motion blur is a scene setting, not a
  per-layer one, so this split is a render-script step, not a scene flag.
- Bundles (`HEAD_RENDER_BUNDLE` / `COMPOSITE_BUNDLE`) are split from Blender's per-frame
  multilayer EXR by the packaging script (next step), not by Blender.

## Verified on this machine (Blender 5.2.1 LTS, Apple M4) — 2026-09-15

- Multilayer EXR output is selected through `image_settings.media_type = "MULTI_LAYER_IMAGE"`;
  setting `file_format` directly is rejected. VERIFIED FACT on 5.2.1.
- Cycles renders on Metal headless: device `Apple M4 (GPU - 10 cores)` enumerated and used.
- The vendored ACES studio config loads through `$OCIO`: scene-linear `ACEScg`, view
  `ACES 2.0 - SDR 100 nits (Rec.709)`, display `sRGB - Display` (`measurements/check_scene.json`).
  Blender warns that a sequencer colourspace `sRGB` is not found under this config; harmless for
  the slice (no sequencer use) and recorded here so it is not rediscovered.
- `scene.render.motion_blur_position` is the shutter-position API on this version.
- `check_scene.py` passes on the built template with zero failed checks.
- Exporters (2026-09-15): `export_shot.py` on the placeholder template exports SHOT_001 (120
  frames); `check_exports.py` and `check_alembic.py` pass. Socket at f1001 is the identity
  quaternion at (0, 1.42, 0); sub-frame samples differ monotonically across the shutter at a
  moving frame (f1030: quaternion y 0.08405 / 0.08516 / 0.08626), so the sub-frame data is real,
  not a copied centre sample. Alembic re-import shows proxy vertices moving between the first
  and last frame.
- Found and fixed on the first export: a child parented to a bone takes its rest relation from
  the pose current at parenting time; a pose left on the last keyframe baked a 0.2 rad yaw into
  the socket at f1001. The template now returns to the first frame before any bone parenting.
- Found by the 2026-09-15 adversarial review and fixed the same day: the camera extrinsic was
  converted as a similarity, which re-labels the camera's local axes and made the exported
  camera look along socket +Y (re-projection error 146 860 px); the principal point had both
  signs inverted; hard min/max on the `FACE_CTRL` properties clamped animated values before the
  exporter could reject them; the root matrix relating the Alembic to the JSON was in no file.
  All four are now covered by tests (`tests/test_socketspace.py`, `tests/test_slice_exports.py`)
  and by `check_exports.py`.

- One 4K frame rendered headless on Metal (`measurements/test_frame.json`, 64 samples, no
  denoise, placeholder scene): beauty group of five layers with blur **273.6 s**, data layer
  without blur **74.1 s** — about **55 s per beauty-equivalent** on Apple M4 before any
  character, hair or real lighting exists. The proposal's 60–180 s assumption was for a
  24 GB workstation GPU; on this machine it is the floor, not the range. MACHINE BASELINE,
  not `S_frame`. Output on placeholders: 111 MB per frame for the six layers (ZIP).
- Pixel types VERIFIED on the written EXR: every `Combined` part is half; the six cryptomatte
  parts, `Depth` (one channel) and `Vector` (four channels) are full float inside the
  half-float multilayer file — the ADR-0002 D6 half/float split holds without any extra step.
- `Vector` renders on the data layer with motion blur off. `Combined` is written for `L_DATA`
  even with `use_pass_combined` off — harmless; the packaging split drops it.

Still INDEPENDENT OBSERVATION: `indirect_only` producing shadow without camera contribution
(checked visually once real geometry exists; a pixel test is part of the precomp-reproduction
script); Vector availability with blur ON (not needed by the pipeline, so not tested).

## Verified on this machine — render and bundles (2026-09-15)

- Both profiles render headless through `render_passes.py` (smoke: 10 %, 8 samples): video with
  a 180° centred shutter, still at 3840 × 3840 with shutter 0 at the state map's still frame;
  the data group renders with blur off and yields `Depth` and `Vector`. Previews through the
  ACES display look as expected (placeholder head on body, hand plate, key from upper left;
  probe balls show the key reflection).
- `write_still` does not substitute `#` padding on 5.2.1; the file name is built explicitly.
- **Determinism is measured, not achieved** (review 2026-09-15): with seed 0, adaptive sampling
  and denoising off, two renders of the same frame on Cycles/Metal differ — `L_FULL`, `L_HEAD`,
  `L_FG`, `Depth` identical, `L_BODY` / `L_BODYSHADOW` max error 1.95e-3, `Vector` 1.1e-5.
  EXR headers also carry render time and date. Consequences: `render_passes.py` asserts and
  records the determinism settings; `split_bundles.py` records a pixel SHA-1 per part as the
  reproducibility token, and the file sha256 is an integrity token only. Whether bit-exactness
  is reachable on Metal, or is a CPU-only property, is measured on the real asset (proposal
  §8 risk 9) and recorded — never claimed.
- Blender writes the `cryptomatte/<id>/{name,hash,conversion,manifest}` attributes on the
  first part of the multilayer file, not on the crypto parts; the split copies them onto every
  `CRYPTO_*` part and keeps Blender's channel names there, because a Cryptomatte reader matches
  channels by the manifest's `name`. The first split had silently dropped them.
- **`oiiotool --attrib` parses its value**: a JSON manifest `{"a":"b",…}` is stored as the
  single token `a` (verified with `exrinfo` on the written file), while `oiiotool --info` on the
  same file still prints the full string it was given. All EXR writing in this pipeline therefore
  goes through the OpenImageIO Python API under Blender's Python; `oiiotool` is used to inspect.
- Occluders (the hand) are shadow-only (`indirect_only`) in both body plates, so `PRECOMP_BACK`
  ⊕ head ⊕ `PRECOMP_FRONT` does not lay the occluder over itself at soft edges.
- The data group renders with motion blur AND depth of field off; a still profile with DoF
  keeps DoF only on the beauty group.
- `oiiotool` writes float by default: the split passes `-d half|float` per part and checks the
  written type — the first split silently promoted every beauty part to float. `--stats` is a
  standalone op; after other ops `--printstats` is the one that prints.

## Verified on this machine — compositor (2026-09-15, placeholder scene, 64 samples at 10 %)

- `SKIN_ID_HEAD` decoded from the material cryptomatte equals `HEAD_HOLDOUT` to six digits
  (mean coverage 0.036477 both) — the placeholder head is entirely `HERO_SKIN_HEAD`, so the two
  decodings must be the same matte, and they are.
- `HEAD_SHADOW_MULTIPLY` lies in [0.62, 1], mean 0.9955; clipped fraction 4e-5.
- Precomp reproduction (criterion 3) is a **gate**: `composite.py` exits 2 when the fraction of
  pixels outside the boundary band within 1e-3 falls below the declared threshold (0.995,
  PROVISIONAL). On the placeholder smoke frame the value is above the threshold; the numbers
  live in `precomp_report.####.json`, not here, so they cannot go stale.
- **Measured cause of the residual** (review 2026-09-15): per-layer Monte Carlo noise is ~0 —
  with the same seed and identical geometry the shadowed body plate equals the full render
  bit-exactly on 99.98 % of pixels away from the head. Every pixel with error > 1e-3 has
  fractional head or occluder alpha: the residual is two separately filtered layers meeting at
  an edge, plus half quantization. The band is therefore the union of the head edge and the
  occluder edge, and the first draft's "noise floor" line was removed as wrong.
- `HEAD_HOLDOUT` (and the default head layer `L_HEAD`) is the head's **unoccluded** silhouette —
  the occluder is shadow-only in `L_HEAD`, as in the body plates. Otherwise the hand cut the head
  once in `L_HEAD` and `PRECOMP_FRONT over` cut it again, doubling the attenuation on every
  partial-alpha pixel where they overlap (worst pixel error 0.80 → 0.39 once fixed). The
  visible, occluded coverage is the object cryptomatte in the COMPOSITE bundle.
- Every written part carries the working-space declaration (`colorInteropID` from the raw
  render) and `bundle_manifest` records `working_space: ACEScg`; the other raw header attributes
  (render time, cycles.*, camera, frame) are listed by name as not carried.

- **D7 round-trip (2026-09-15)**, on a template whose `SOCKET_SPACE_ROOT` is translated
  (0.3, −0.2, 0.05) m and yawed 25° so every `root⁻¹` term is live, rendered at 100 % / 16 spp
  (`measurements/roundtrip_SHOT_001_posed.{video,still}.json`): frame 1001 (video, 9 shutter
  samples) and the still (frame 1050, 3840×3840) both PASS — p95 boundary distance 0.25 px
  (the resolution of the upsampled iso-contour, i.e. the contours coincide; max 0.5 px),
  centroid 0.005 px (video) / 0.006 px (still), IoU 0.9999, band coverage difference
  0.018–0.021 against a gate of 0.05. Negative controls on both profiles: the 5-px translation
  fails the gate (VALIDATED: p95 5.0 px, centroid 4.9 px), the 5-px focal growth fails it
  (VALIDATED: p95 5.4 px still / 7.0 px video with the collar, IoU 0.975, centroid ≤ 0.26 px —
  a size error the centroid barely sees, which is why the gate has four metrics), and the 3° yaw
  sits on the threshold: band 0.053 on the still (VALIDATED) and 0.050 on the video frame
  (NOT_VALIDATED, the gate is strict), through the faceting of the 48-segment placeholder
  sphere alone — a rotation-symmetric silhouette would not respond at all, so this control is
  not validated by the placeholder; the real head validates it. The positive control reads
    NOT_DISCRIMINATING: the placeholder's head does not move enough across one shutter for the
  sub-frame samples to change the matte — the code path is exercised, the data is not yet
  tested; the real asset's fast-turn window is where it must read DISCRIMINATING. The plain
  template's export against the posed render FAILS (wrong export detected); an aborted run
  leaves `ERROR` in the bundle manifest, never a stale PASS. Review round 2 replaced the
  integer-valued binary-mask boundary distance (which sat on its own 1 px threshold) with the
  distance between 0.5 iso-contours of the ×4 bilinearly upsampled coverages, and gated the band
  coverage difference against its measured floor.
- **`HEAD_HOLDOUT` and the body**: `C_BODY` and `C_ENV` hold the head out in `L_HEAD` (only
  `C_HAND_FG` is shadow-only), so where the body or environment is in front of the head the
  holdout IS cut. The round-trip excludes pixels where such an object's cryptomatte coverage
  meets the re-projected head and reports the fraction (placeholder at 4K: 1 422 px of 404 k on
  the video frame, 138 of 454 k on the still — the seam edge). The exclusion is bounded at half
  of the re-projected head: the plain template's export against the posed render lands the
  head on the wall, which would have excluded everything and measured nothing — beyond the
  bound the frame FAILS before any metric. The export classifies every
  render-visible object as head / occluder / holdout, and a cryptomatte name with coverage that
  the export did not classify is an error. A real shot where that fraction is not ~0 is a shot-design
  finding, recorded per frame. The rest head is re-projected against every frame: frames whose
  performance track exceeds |0.2| on any channel are flagged `deformed_beyond_gate_calibration`
  (reported only, no consumer yet) and gated like every other frame; separate thresholds for
  deformed frames are calibrated on the real asset.
- **Found by the round-trip on the still**: `camera.json` carried one pixel principal point,
  the video frame's; the still profile (3840×3840) has another. Fixed with `px_by_profile`.
- **Found by the root-posed template**: the placeholder body and hand were not parented to the
  rig, so a moved root left them behind (boundary rest gap 0.42 m). Both are now the rig's
  children, as a skinned body is. The placeholder head is also truncated at the body ring: a
  head that dips inside the body is held out by `C_BODY` in `L_HEAD`, and `HEAD_HOLDOUT` would
  no longer be the head's own silhouette. The first truncation welded the sphere's lowest ring
  outward onto a 0.14 m neck — a flared collar seen edge-on that dropped the precomp gate's
  inside-band fraction to 0.890 (< 0.9 floor). The neck now has the sphere's own ring radius
  (0.099 m at z 1.411, ring 18 of 24) so the weld moves nothing and the body has no cap:
  inside-band 0.923, max error 0.293 on the 64-spp smoke frame (was 0.927 / 0.385 with the
  sphere inside the body). At 8 spp the same frame fails the gate (inside-band 0.855): the
  criterion-3 gate needs the smoke count of 64 spp or more, never 8.
- **Per-order composite (2026-09-15)** on the 10 % / 64 spp smoke frame
  (`measurements/order_composite_smoke.json`, recorded by the tool with
  `--record-default-head-reproduction`): with the default head's own layer and multiply as
  inputs, FINAL reproduces `DEFAULT_HEAD_BEAUTY` within 1e-3 on 99.995 % of pixels outside the
  2-px band (max error 0.293, inside-band@5e-2 0.923 — the compositor's own figures), unfilled
  fraction 0.0; a second run with the same idempotency key is a verified no-op and a different
  order in the same directory is refused; a head layer shifted by 8 px fails the fill gate, a
  shadow map scaled ×255 fails the range gate, and in both cases nothing but a `FAIL` manifest
  is left in the output directory (frames are staged); a missing shadow multiply is an error.
- **Metal crash, once (2026-09-15)**: the first test-rebuild died with SIGSEGV inside
  `MTLBinaryArchive serializeToURL` on Cycles' shader-compile thread while the probe's materials
  compiled (`template.crash.txt`, frames 1001–1010 of the beauty group had already rendered).
  Cycles exposes `CYCLES_METAL_DISABLE_BINARY_ARCHIVES`; `rebuild_shot.py` sets it for every
  step and records it in the report. The archive is a shader cache, not a render result.
- **Rebuild (2026-09-15)**: `rebuild_shot.py` twice in a row at smoke settings (64 spp, 10 %,
  frames 1001–1010), the second run comparing against the first as its archive
  (`measurements/rebuild_SHOT_001.json`). Two findings on the way: the head OBJ differed
  between runs only in face order (bmesh leaves it unspecified — faces are now written in
  canonical order), and `proxies.abc` carries its write date and the source `.blend` path in
  the Alembic header, so it can never be byte-identical — its meta file now carries a hash of
  the evaluated proxy geometry at every sub-frame sample, and that is what the rebuild compares.
  A rebuild that finds nothing to compare is `NOT COMPARED`, never a pass (`--no-archive`).
  Measured B against A under identical render settings: 10 of 11 export files byte-identical
  and the Alembic identical by geometry hash; video bundle parts 97 identical / 43 differing,
  still 10 / 4 — the differing parts are the four Cycles-sampled passes per frame
  (DEFAULT_HEAD_BEAUTY, BODY_BEAUTY, BODY_SHADOW_RAW and MOTION_VECTORS, which is filtered
  over samples like a beauty pass) plus FOREGROUND_PLATE on three frames of ten; cryptomatte,
  DEPTH and the holdouts were bit-identical on every frame in this run (an earlier pair of runs
  had HEAD_HOLDOUT differ on one frame — which passes are bit-exact varies between runs, which is
  the point). The report's status says what was proven — exports reproducible, renders compared
  with the count of differing parts — not
  "PASS". Differing parts are listed and counted, not gated:
  an image tolerance for Metal's non-determinism does not exist yet and none is invented.
  Metal is not bit-exact; the per-part pixel SHA-1 is the reproducibility token and the list of
  differing parts is in the report.

- **Contractor questions (2026-09-15)** changed three placeholder assumptions: the socket is
  bone-parented to `head`, not `neck` (the socket carries the whole head pose; `neck` only held
  on the placeholder because its head bone never moved on its own); the ring lives on exactly
  one render-visible mesh of `C_HEAD` (the shell) and further head meshes are allowed; hair
  transparency is an OPEN round-trip item (`conventions.json → roundtrip.hair_transparency`).
  `check_scene.py` also rejects hard min/max on the 26 `FACE_CTRL` channel properties (a hard
  limit clamps animation silently) and requires the soft limits to equal `channel_map.json`.

## Not here yet (next steps, in order)

The rigger/animator's bursts replace `PLACEHOLDER_*` and the
`FACE_CTRL` keys without renaming; the bone names in `conventions.json` and the property
names in `channel_map.json` are the contract they build to.
