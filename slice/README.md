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
| `export_shot.py` | Exports one shot's `HEAD_RENDER_BUNDLE` data (ADR-0002 D5 rows 6, 7, 8, 11, 12): `camera.json` (per-frame intrinsics with fx/fy and a sign-verified principal point, extrinsics with sub-frame samples), `socket.json` and `joints.json` (sub-frame samples — nine across the shutter since the ADR-0002 amendment of 2026-09-25, `conventions.json → exports.sub_frame_offsets_frames`), `socket_boundary.json` (ordered rings on head and body, rest gap, the first PROVISIONAL envelope), `lighting_ref.json`, `performance_track.json` (validates against `schemas/performance_track.json`), `proxies.abc` + meta with the `abc_to_socket` matrix, `proxies_rest.obj`, `default_head_rest.obj` (every renderable mesh of `C_HEAD` ∪ `C_HAIR` in the socket's local frame — the head technology's envelope reference and the round-trip's faces), `default_head_deformed.npy` (QC only: the C_HEAD meshes evaluated at every frame and sub-frame sample in the OBJ's vertex order — what the round-trip re-projects; the export stops if C_HAIR moves on the socket), `export_manifest.json` with sha256 per file and the root matrix everything is relative to. `camera.json` carries pixel intrinsics per render profile (`px_by_profile`): the still's principal point is not the video's. Asserts the scene's units, fps, shutter and pixel aspect against `conventions.json`, and that the scene does not remap time (render_passes.py stretches it itself since 2026-09-25 and refuses a scene's own remap too), before exporting; cleans the output directory first. |
| `check_exports.py` | Validates an export directory outside Blender with load-bearing checks: file set and manifest hashes, no NaN token, schema, frame coverage, sub-frame offsets and that the samples are actually distinct, measured scale, proper rotations, frame-to-frame continuity (jumps and hemisphere flips fail), intrinsics-constant flag vs data, joints complete and proper, boundary rings equal and coincident at rest, lighting present, Alembic and OBJ non-empty, track socket rows equal to the socket file's centre samples, the deformed head's dtype, shape, object prefix and its rest sample equal to the OBJ. |
| `check_alembic.py` | Re-imports `proxies.abc` into an empty Blender and proves it carries per-frame geometry. |
| `render_passes.py` | Renders one shot for one profile in two groups — beauty layers with the profile's shutter, `L_DATA` with blur off — as raw multilayer EXRs per frame, plus the lighting probe (chrome and grey balls at the socket, hero excluded) on request; writes `render_manifest.<profile>.json` with settings, device, per-frame seconds and bytes, hashes. Never saves the scene. **Since the ADR-0002 amendment of 2026-09-25 the plates are rendered with the time stretched by 720 / shutter angle** (×4 at 180°, Blender's time remapping, recorded as `settings.time_stretch`): the picture is the frame's own and every Vector pass points at the shutter's open and close instants (`settings.vector_reach_frames`, ¼ frame) instead of frame ±1; `--blur-reference` sets every object's Cycles motion steps so the shutter is sampled at the exports' nine instants (`settings.motion_steps`, `shutter_time_points`) and lists objects whose own motion blur is off. `--samples/--scale` overrides mark the output `smoke_test_only`; a `--scale` that does not give whole pixels on both axes is refused with the list of scales that do (16 % on 3840×2160 renders 614×345 while every consumer re-deriving the size rounds to 614×346, and the round-trip then stopped on a size mismatch that said nothing about its cause — contractor, 2026-09-17). |
| `split_bundles.py` | Splits the raw EXRs into `HEAD_RENDER_BUNDLE/holdout.####.exr` and `COMPOSITE_BUNDLE/composite.####.exr` through the OpenImageIO API under Blender's Python, parts named and typed per `conventions.json → bundles` (half for beauty, float for cryptomatte, depth, vectors), `cryptomatte/*` manifests carried onto every `CRYPTO_*` part and re-parsed as JSON, `slice:alpha` / `slice:pass` on every part; re-reads every written part and requires exact equality with the source after the declared quantization; records `bytes_per_frame` and a pixel SHA-1 per part in `bundle_manifest.<profile>.json`; copies the HEAD_RENDER plus files (exports, probe). Every `*MOTION_VECTORS` part records the vectors' time base (`vector_reach_frames`) beside the shutter; a video render without it (vectors to frame ±1, rendered before 2026-09-25) is refused. |
| `composite.py` | **Criterion 3 composites `FRONT over (HEAD over SEAM_EXTEND(BACK))` and gates the seam's signed error (A2) beside the band fraction** (since 2026-09-25, `seam_extend.py`; the rings come from HEAD_RENDER_BUNDLE's plus files, so the split must carry the exports; PRECOMP_BACK is written as rendered). Derives `HEAD_SHADOW_MULTIPLY` (shadowed ÷ body with a declared epsilon, clipped fraction reported), `SKIN_ID` / `SKIN_ID_HEAD` / `SKIN_ID_BODY` from the material cryptomatte, `PRECOMP_BACK` / `PRECOMP_FRONT`, and runs the precomp-reproduction test (ADR-0002 §Validation 3) — `FRONT over (HEAD over BACK)` against the full render, error fractions inside and outside a 2-px boundary band, PROVISIONAL tolerances — writing `derived.####.exr` and `precomp_report.####.json`. |
| `motion_blur.py` | **The post-composite blur** (ADR-0002 D5, amendments 2026-09-22 and 2026-09-25), numpy only, tested in CI (`tests/test_motion_blur.py`): at K instants of the shutter every layer is forward-warped along its own vectors on a quadratic path through the shutter-open, current and shutter-close positions, composited, and the K composites averaged; K follows the longest path. Every call states how far the vectors reach (`reach_frames`, from the render manifest); a synthetic pulse shorter than a frame is blurred right only through shutter-end vectors (0.008 against 0.059 through frame vectors). |
| `camera_model.py` | Pinhole intrinsics from Blender camera data (fit rules, shift signs, per-profile pixel values) and the projection, pure Python, unit-tested in CI. Used by the exporter and the round-trip. |
| `matte_metrics.py` | The round-trip's rasteriser (4×4 supersampled box coverage), the edge band shared with `composite.py`, and the silhouette metrics (p95 symmetric boundary distance, centroid, IoU, band coverage difference), and `reference_quantization_px` — what a Monte Carlo reference's 1/samples quantization costs the ≥0.5 masks across a blur ramp (since 2026-09-25) — numpy only, unit-tested on synthetic mattes in CI. |
| `roundtrip.py` | **D7 round-trip test.** Loads no scene: places the default head as rendered (`default_head_deformed.npy` for C_HEAD, `default_head_rest.obj` for faces and rigid hair; the rest head is re-projected too and reported as `rest_head_comparison`) by `socket.json`, sees it through `camera.json`, integrates the nine exported sub-frame samples with trapezoid weights (since 2026-09-25; before, nine instants interpolated between three samples) against a blur reference that samples the same nine instants (refused otherwise), rasterises, and compares with the blurred matte; the centre sample is also gated against the plates' own sharp `HEAD_HOLDOUT` (`plate_centre_sample` — the only check of the time-stretched render's head against the exports). The blurred reference's alpha is quantized to 1/samples, so across a fast head's blur ramp its 0.5 contour is only known to ~1/(n·g) px: every frame records `reference_quantization_px` (`matte_metrics.reference_quantization_px`), a failure within it says so instead of blaming the export, and `--plan-reference-samples` computes from the exports alone how many samples the reference needs (`conventions.json → roundtrip.reference_quantization`; SHOT_002 1209 at 4K failed the IoU against 64 samples and passed against 256 with nothing else changed). PROVISIONAL gate from `conventions.json → roundtrip` (1 px p95 / 0.5 px centroid / IoU 0.995 at profile resolution; STRESS window looser), exit 2 on FAIL. Runs the negative controls on every frame: a 5-px screen shift of the socket MUST fail the gate (else the metric is NOT VALIDATED and the script exits 2); a 3° yaw is reported VALIDATED / NOT_VALIDATED (the placeholder cannot validate it, the real head does). The positive control compares every video frame with its centre sample (DISCRIMINATING above `min_difference` 0.005 — a frame that does not move across the shutter reads NOT_DISCRIMINATING; the report lists both kinds of frame); `--ignore-subframes` writes a whole centre-only report. Writes `roundtrip_report.<profile>.json` and the status into the bundle manifest. | **Gate reviewed 2026-09-19 against v01–v03 at 25 % and 100 %:** the boundary threshold is 0.5 px at full scale, not 1.0 — every correct frame measured sits on the 0.25 px quantisation floor, and the smallest real defect seen (the rest head on an open jaw) is 0.354 px. The flat `iou_min` is gone: IoU is stated as the boundary error it implies and resolved per frame from that frame's own boundary and area (`iou_boundary_error_px_max` 0.15 px, 0.3 in the stress window), because the same error costs 1 − IoU in proportion to boundary/area — a flat 0.995 was nearly free on a 274k px head (a 0.5 px translation passed it) and harsh on a small one. Measured implied error: 0.022–0.054 px for a correct export at either scale, 0.24–0.33 px for the 3° yaw control (IoU now catches it on its own), 3.6–4.7 px for the 5 px translation and growth.
| `composite_order.py` | **Per-order composite entry point.** `FINAL = PRECOMP_FRONT over (HEAD_LAYER over SEAM_EXTEND(BODY_BEAUTY × SHADOW_MULTIPLY_ORDER))` (the seam extension since 2026-09-25, `seam_extend.py`; its parameters are part of the idempotency key) from a head technology's `head.####.exr` (premultiplied, colour declared) and `shadow.####.exr`; refuses to run on a bundle whose precomp reproduction or round-trip has not PASSed; gates on the layer filling `HEAD_HOLDOUT`; never substitutes the default head's multiply. `default-head-inputs` writes the master's own head layer and multiply in the same layout, so the entry point is checked against `DEFAULT_HEAD_BEAUTY`. `order_composite_manifest.json` carries input hashes and `fallbacks: []`. |
| `check_blur_fidelity.py` | **Blur fidelity** (ADR-0002 §Validation criterion 8, amendment 2026-09-22): the post-composite blur of the default head against a render WITH the shutter open (`render_passes.py --blur-reference`), mean max-channel error over the head region on a 4×4 low-pass, beside two negative controls (no blur, a doubled shutter) that a discriminating frame's blur must beat by `discrimination_min_ratio`. Since 2026-09-25 a frame discriminates by its HEAD's own motion (p90 of the head layer's shutter path), not the frame's longest path — SHOT_002 1185 counted a blinking eyelid and failed on noise — and the controls are built from the same seam-extended back as the blur. SHOT_002 1209/1210 failed because the blur's path ran through vectors to the previous/next FRAME, which a laugh pulse faster than a frame outruns (`slice/measurements/blur_1209_investigation_2026-09-25.json`); since the ADR-0002 amendment of 2026-09-25 the vectors reach the shutter's ends, the reach is read from the render manifest, and the doubled-shutter control is the same path twice as long (vectors ×2), not an extrapolation of the quadratic. |
| `seam_extend.py` | **The back under the head's lower edge** (ADR-0002 amendment 2026-09-24, approved 2026-09-25), numpy only, tested in CI on synthetic plates (`tests/test_seam_extend.py`). The head and the body meet vertex to vertex at the socket ring, so the body plate under the head shows the open neck and the head's partial edge pixels drew a dark line along the neck in every layered composite — measured on every frame of the contractor's SHOT_001 v01 and SHOT_002 v01, and passed by criterion 3 on SHOT_001 because the seam is ~5 % of the band. `SEAM_EXTEND` replaces the back only inside the head holdout and within `zone_px` of the projected rings (the head ring carried by the socket, the body ring per frame; a ring that dips is followed), growing the body from the pixels outside the head for `extend_px` rings (render pixels, `conventions.json → compositor.seam_extend`, PROVISIONAL); `seam_criterion` is criterion 3's A2 — the signed mean error over the seam's MIXED pixels (band ∩ zone ∩ fractional head coverage — where the line lives; the whole band dilutes it about threefold) within ±0.04. The zone uses only ring segments facing the camera (outward radial normal towards it, grazing tolerance), so the hidden back arc adds nothing, and only where the seam is welded (head-ring and body-ring points within `ring_weld_mm`): an open seam is the master's and is reported per frame (`OPEN_SEAM`), never painted over — the placeholder's rigid body opens as its head turns, the contractor's asset never does (0.000 mm on 240 frames). `composite.py` reports the same composite WITHOUT the extension beside it on every frame, never gated. |
| `package.py` | Content-addressed package (D11): `hash` writes `package_manifest.json` with sha256 + bytes of every file, per-shot entries derived from the export and bundle manifests (their hashes re-checked against disk — stale files refuse to package), toolchain and OCIO from the lock (hash verified), `package_hash`; `verify` recomputes and fails on any missing / added / changed file. CI verifies the committed package. |
| `rebuild_shot.py` | Test-rebuild of one shot from the archived source (REBUILD.md step 8): runs every step into a fresh directory, records each step's exit code and wall-clock, then compares the fresh exports with the archive's by hash (must be identical) and the render bundle parts by pixel SHA-1 (identical / differing counted and listed). |
| `check_silhouette.py` | See-through holes in the silhouette, the measured form of contractor ACCEPTANCE item 2в. Links `C_HEAD`, `C_BODY` and `C_HAND_FG` into a fresh scene — **without `C_ENV`** (a wall behind the character fills every opening) and **without `C_HAIR`** (hair has free edges: it invents gaps between strands and hides real openings behind them) — gives each render-visible object an opaque emission colour, poses the rig at rest and at the slice's maximum head turn, and renders the declared views (4 framing the figure, 36 sweeping the seam at 12 yaws × 3 pitches) with a transparent film at 1 spp and a 0.01 px box filter. Background regions that never reach the image border are labelled: each is a line of sight that enters the silhouette and leaves it. A region fails only when its line of sight passes within `region_of_interest.radius_m` (0.12 m) of `SOCKET_HEAD`, which gates the head↔body seam and leaves the gap between a hanging arm and the torso a report. **The pose is verified, not trusted:** bone rotations are local and +Y runs along the bone, so a turn is about Y — the first version of this gate said Z, which is a 60° roll with 7° of yaw, and the tool now measures SOCKET_HEAD's world rotation after posing and stops unless it matches `pose.achieved`. The verdict names the objects bordering the hole; every view is written out as a PNG next to `silhouette_report.json`. 80 renders, ~20 s. Measured: the contractor's v02 leaves exactly one region at the seam — the 237 px collar opening, visible from a single 30° sector — and v03 none. Tested: the placeholder passes, a placeholder with faces deleted beside the socket fails. |
| `measure_hand_over_head.py` | **How much of the head the hand and the forearm cover** — ACCEPTANCE item 4 of burst 2 (a fifth to a half, `state_requirements.json → hand_over_head`), measured on a split render: the head re-projected from the exports (HEAD_HOLDOUT is cut by the forearm) against the forearm (object cryptomatte) and the hand (FOREGROUND_PLATE). In range only when every measured frame is (the hold, Q40 — not the peak); names the frames outside it and the lowest. Informs the owner, who judges the gesture; exit 0 either way. Bounding boxes said 28 % on the SHOT_003 early checkpoint where the render shows 16 % (2026-09-25). |
| `check_asset.sh` | One command for a delivered scene (the blur reference's samples are planned from the exports since 2026-09-25 — step 8 prints them): check_scene → check_silhouette → export → check_exports → check_alembic → smoke render of the video frames `pick_frames.py` chooses and the still (64 spp / 25 %, the criterion-3 gate needs ≥ 64 spp) → split → composite → round-trip; stops at the first failing gate. The contractor's self-check and our acceptance (`contractor/burst-1/ACCEPTANCE.md`). `CHECK_ASSET_QUICK=1` runs the first video frame only, no still, and ends with `ASSET_CHECK_QUICK_OK`, never `ASSET_CHECK_OK` — for the animator's intermediate runs on a CPU (contractor Q22); `accept_delivery.py` removes the variable and always runs the full check (tested). |
| `pick_frames.py` | The video frames `check_asset.sh` renders, from the exports: the shot's first frame, the fastest head turn (where the sub-frame positive control can discriminate) and the widest open jaw (where the deformed-head re-projection matters). Fewer when the head never turns or the jaw never opens; never an invented frame. Tested in CI. |
| `accept_delivery.py` | ACCEPTANCE item 5 as one command: MPFB2 from the declared git ref (or zip), built and installed into an isolated Blender profile under the run directory (extensions, config, scripts, datafiles; version and commit verified against LICENSES.md); the judging tools (slice/, schemas/, scripts/, the OCIO config) fingerprinted before the build and re-checked after it, byte-code caches under those trees deleted before the fingerprint and required absent after the build (Blender's embedded Python ignores `PYTHONDONTWRITEBYTECODE`, so a planted `.pyc` is caught by presence); the template from `scene_template.py` at the commit named in REPORT.md; the contractor's `build_character.py` copied into the run directory with every sibling file (all recorded by sha256), scanned by logical line of code tokens, comments and docstrings removed, for the module and operator forms of what a rebuild never needs (opening or appending another `.blend`, processes, network, file-copy modules, dynamic imports, `exec`/`eval`, `wm` operators resolved at run time; bare words like a `socket` variable are not hits — measured on `scene_template.py`, whose only hit is its legitimate `read_factory_settings`; a hit blocks unless `--allow-scan-hits`, which caps the verdict at PARTIAL) and run there (must print `BUILD_OK`; the delivered file must be unchanged afterwards; the rebuilt bytes must differ from the delivered ones); the template script's content must exist in this repository's history; `check_scene` on both files; `check_asset.sh` on both; the shot's exports of both compared by `rebuild_shot.compare_exports` with the cross-platform tolerance (non-identical JSON/OBJ files numerically, `proxies.abc` by `compare_alembic.py`); `blend_content_hash.py` on both, and when the hashes differ the original-order dumps compared within the same tolerance, differing objects and fields named. Measured on the contractor's v01 (Linux CPU build vs macOS Metal rebuild): every number within 3.6e-7, verdict OK. Verdict `ACCEPTANCE_REBUILD_OK` (exit 0; needs a git MPFB2 source at the declared commit and the asset check) / `_PARTIAL` (exit 3: asset check skipped, or MPFB2 not installed / commit unverifiable) / `_FAIL` (exit 2) / 64 usage error; `acceptance_report.json` with every step's exit code and log. Not a sandbox: a script that assembles an operator name at run time, opens the delivery and saves it as the rebuilt file passes every automated check (bytes differ, content equal by construction); the copied scripts' sha256 are recorded and a human reads them. Tested on the placeholder: identity build with a test-double MPFB2 from a local git repo and the asset check → OK without touching the user's Blender profile; no asset check or zip source → PARTIAL; tampered delivery → FAIL naming the object; a script opening another `.blend` → FAIL before running; an obfuscated byte copy → FAIL; a script overwriting the delivery → FAIL; a script planting a file under `schemas/` → FAIL by the fingerprint, a planted `.pyc` under `scripts/` → FAIL by presence (both Blender-gated, local evidence); no `BUILD_OK` → FAIL; MPFB2 version or commit mismatch → FAIL; another shot's scene → FAIL at export; usage errors → 64. |
| `blend_content_hash.py` | Content hash of a `.blend` scene (what it means, not its bytes): canonicalised mesh geometry (ties between coincident vertices broken by their neighbours), vertex groups, shape keys, armature bones with full orientation, pose-bone constraints and IK, object constraints and modifiers with their RNA parameters, custom properties with their limits, materials' nodes and packed textures by sha256, animation curves and **drivers**; per-object hashes in a JSON so a difference is located. Tested: two template builds hash equal; a moved vertex, a renamed bone, a driver, a constraint, a bone roll, a hard limit or a swapped texture each change it and are located. Gaps found by the contractor's review (Q12) closed 2026-09-16. `mesh_data` (2026-09-16, hash rule version): per-mesh {hash, collections, objects, materials}, the hash over geometry, shape keys and every user's vertex groups but not transform, parent or pose — measured: a neck pose key moves the socket children's object hashes and leaves `mesh_data` intact, a vertex-group change moves the mesh entry; this is the burst-2 "character unchanged" rule. `--dump` writes the content in Blender's own vertex order (order-sensitive, not what is hashed) for the cross-machine numeric comparison — the canonical order flips under float noise for near-tied vertices; machine-derived scene props `render_device` and `ocio_config_env` are excluded from the hash (2026-09-16). |
| `check_states.py` + `state_requirements.json` | Burst-2 gate "states reached" (contractor/burst-2/ACCEPTANCE.md item 3), from the exports only: per state window of `state_map.json`, channel peaks, head angle to the camera (socket +Z vs the direction to the camera, socket space), angular velocity against the animator-declared T (`head_angular_velocity_threshold_deg_s` in state_map.json — NOT_EVALUATED until declared, verdict at most PARTIAL; the maxima are printed meanwhile) with a separation margin (`velocity_separation`, PROVISIONAL: MEDIUM windows ≤ 0.8·T, fast_movement ≥ 1.5·T, so T cannot sit flush against either), a hold / endpoints / range rule per state, the strong-light colour ratio from `lighting_ref.json`, a freeze rule over the whole shot (> 12 frames with no channel, socket position or rotation change), and — since 2026-09-24 — a **jump rule** over the whole shot: the head's screen step between consecutive frames (the rest head of `default_head_rest.obj` placed by each frame's socket, both seen through the later frame's camera at the video profile, median over vertices) may not exceed 3× BOTH neighbouring steps above a 3 px noise floor (`state_requirements.json → jump_rule`, PROVISIONAL). Found by the SHOT_002 v01 acceptance: per-window pose formulas that do not meet at a window boundary throw the head by a whole step in one frame (SHOT_002 1153, 1177, 1195 at 4.1–5.5×; SHOT_001 1019 at 4.5×), while every other step of both shots — both laughs and a 4-frame glance-follow — stays at or below 2.08×; no velocity or freeze rule sees it. NOT_EVALUATED (verdict at most PARTIAL) when the exports carry no rest head or no video intrinsics. Since 2026-09-25 SHOT_003's sadness, fear and hand_over_face keep the head at 35–55° to the camera on every frame (`three_quarter_neutral_rule`, version 2): the shot is the bake-off's only ¾ under neutral light, and the early checkpoint stood frontal at 4–15° and passed while the rule lived only in the task text. Human items (hand fraction — measured by `measure_hand_over_head.py`, shadow picture, liveliness) are listed, never evaluated. Verdict STATES_OK / PARTIAL / FAIL with the window, rule and measured value. Tested on synthetic exports (meeting every minimum → OK with T, PARTIAL without; flat → FAIL by freeze and every peak; no turn → SHOT_002 profile/turn/hold FAIL; a T between the tiers but inside the margin → FAIL, outside it → PASS; T ≤ 0 → error) and on the placeholder: SHOT_002 and SHOT_003 FAIL, SHOT_001 passes — the SHOT_001 minimums were written from the template's own test ramps, so SHOT_001 is the weakest window of this gate and the acting judgement there is the owner's. |
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
- **D7 round-trip on the real head (contractor v01, 2026-09-16)**, SHOT_001 at 100 % / 64 spp on
  the delivered file (`measurements/roundtrip_v01_SHOT_001{.video,.still,_motion.video}.json`;
  review and decisions in `measurements/roundtrip_v01_SHOT_001_review.json`). The acceptance run
  (frame 1001 and the still) and six more video frames rendered for motion (1030, 1060, 1080,
  1085, 1090, 1100 — up to 0.41° of head rotation per shutter):
  - **Undeformed floor** (1001, 1030, 1060, 1085, still): p95 0.25 px (the iso-contour quantum),
    centroid 0.0006–0.006 px, IoU 0.9997–0.9999, band 0.016–0.020 — the band floor is the
    placeholder's, i.e. the reconstruction filter, not the geometry. Body over head ≤ 1e-4.
  - **Rotation control VALIDATED** on both profiles and on every metric: the 3° yaw gives p95
    3.3–3.5 px, centroid 0.77–0.81 px, IoU 0.992, band 0.17 (the sphere sat on the band threshold
    at 0.050–0.053). At 25 % the margin is thin: band 0.052–0.056, p95 0.79–0.90 against 0.5.
  - **Sensitivity** (`measurements/roundtrip_v01_sensitivity.py`, frames 1001 / 1050, no render):
    the gate catches a 0.5-px translation or size growth and a 0.75° yaw (0.5° pitch on the
    still), almost always first through the band metric; it misses 0.25 px and 0.25–0.5°. IoU is
    the least sensitive metric and fails only from 0.75–1 px or 1.5–3°.
  - **Positive control DISCRIMINATING where the head moves**: centre-only differs from the
    shutter-integrated result by 0.014–0.040 on the moving frames, and on 1030 and 1090 the
    centre-only result FAILS the band gate (0.057, 0.054) while the integrated one passes — the
    gate itself catches a missing shutter integration at 0.26–0.4° per shutter. Frame 1001, the
    only video frame `check_asset.sh` renders, does not move (0.001° per shutter); its
    "DISCRIMINATING" (0.0020 against the old 0.001) was the metric's floor, so `min_difference`
    is now 0.005 and that frame reads NOT_DISCRIMINATING, as it should.
  - **Found: an open jaw fails a correct export.** Frame 1100 (jaw_open 0.87, mouth corners 0.96)
    FAILS: p95 2.57 px, centroid 0.57 px, band 0.069. The render's silhouette has 649 more
    pixels than the rest head, 605 of them in the 70–90 % height band (chin), the rest of the
    contour at the floor (`measurements/roundtrip_v01_where.py`) — the transform is right, the
    rest head cannot open its mouth. Jaw 0.18–0.19 (1080, 1090) passes at p95 0.35 px. Loosening
    the thresholds on deformed frames would hide a transform error of the same size, so the
    recommended fix is to re-project the per-frame deformed default head — **done 2026-09-17**,
    next item. The old `deformed_beyond_gate_calibration` proxy (max |channel| > 0.2) was weak on
    the real head: it flagged a blink (1.0, frame 1080) and mouth corners (0.74, the still) that
    leave the silhouette unchanged; it is gone with the fix.
  - **Thresholds reviewed, kept** (PROVISIONAL, one asset, one shot, static camera): p95 1.0 px
    (0.5 px would be possible once deformation is re-projected), centroid 0.5 px, band 0.05
    (2.5× its floor, the most sensitive metric; it does not scale, so a 25 % run is weaker).
    `iou_min` 0.995 is size-dependent: for a uniform boundary error δ, 1 − IoU ≈ 2δ/r, so it means
    ≈ 0.67 px at this framing (r ≈ 270 px) but 2 px in a close-up. A size-aware
    `1 − 2·p95_max / r_eff` is proposed for burst 2, whose three shots have different framings.
    The STRESS window has no real-head data yet.
- **D7 with the deformed head (2026-09-17).** `export_shot.py` writes `default_head_deformed.npy`
  — every render-visible C_HEAD mesh evaluated at every frame and sub-frame sample, socket-local,
  float32 `[frames, 3, vertices, 3]`, in the vertex order of `default_head_rest.obj` — and stops
  when a C_HAIR mesh moves on the socket by more than 1e-5 m (the contract hangs hair rigidly).
  QC only, not a HEAD_RENDER plus file. `roundtrip.py` re-projects it (interpolated across the
  shutter like the socket), still re-projects the rest head and reports it as
  `rest_head_comparison`, never gated, and refuses exports without the file or with an array
  that does not match the OBJ at the rest sample. v01 re-rendered at 100 % / 64 spp (frames 1001,
  1030, 1060, 1080, 1085, 1090, 1100 and the still; the renders of 2026-09-16 had been cleaned
  from the scratch space; `measurements/roundtrip_v01_SHOT_001_deformed.{video,still}.json`):
  **every frame at the floor** — p95 0.25 px, centroid 0.0006–0.007 px, IoU ≥ 0.9997, band
  0.016–0.020; frame 1100 passes (band 0.016) where the rest head on the same render reproduces
  the old failure exactly (p95 2.57 px, centroid 0.570 px, band 0.069), and 1080 / 1090 drop from
  p95 0.35 to 0.25 px. Rotation control VALIDATED on every frame; positive control DISCRIMINATING
  on the six moving frames, not on 1001. Slice test: a placeholder head given a 2-cm jaw shape
  key driven by `jaw_open` passes deformed and fails at rest (p95 > 2 px at 50 %); a deformed
  array with reversed vertex order fails `check_exports` and the round-trip; a C_HAIR mesh with
  a shape key stops the export. `check_asset.sh` renders the frames `pick_frames.py` chooses —
  the first, the frame whose head turns most within its own shutter, the widest jaw (v01: 1001,
  1090, 1102).
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
  finding, recorded per frame. Facial deformation is re-projected since 2026-09-17 (the deformed
  default head); the rest head is reported beside it.
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
