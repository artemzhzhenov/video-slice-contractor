# bakeoff/metrics — Stage 5: the automated metrics and their negative controls

Protocol §5 Stage 5 and §6 (`docs/experiments/bakeoff-protocol.md`); the separation criterion, the `N_rep` rule and the
per-metric rows of the pre-registration (`benchmarks/bakeoff/01J7B000000000000000BAKEXP/preregistration.md` §5, §6).
Built 2026-10-30 (owner: «доделай метрику 5 сначала … поехали»), before Stage 3: the pilot's `N_rep` is read from these
metrics' variance, so without them the pilot would be paid for nothing.

| Module | What | Runs under |
|---|---|---|
| `separation.py` | the separation verdict (`VALIDATED` / `NOT_VALIDATED`) and the `N_rep` rule, χ² quantile included | Python |
| `frames.py` | M3, M4, M6, M7, M8, M10 on arrays | Python (numpy) |
| `controls.py` | the composite-domain negative controls: flicker, shift, scale, head over the hand, a tone step | Python (numpy) |
| `identity.py` | M1, M2, M5 on geometry; the depth-buffered rasteriser the hair's visibility needs | Python (numpy) |
| `rows.py` | a result row's frames: the tier's state windows of `slice/state_map.json` | Python |
| `record.py` | result rows that validate against `schemas/bakeoff_result.json`; the verdict read from rows; `n_rep.json` from the pilot's rows | Python |
| `extract_geometry.py` | HERO_HEAD in the socket frame per frame, the FACE_CTRL channels, the hair's visible coverage in the shot camera | Blender |
| `frame_run.py` | the per-frame metrics on a run's EXRs; the controls' layers and composites; M3 over a sequence; M8 on head layers; M10 over two repeats | Blender (OIIO) |
| `control_render.py` | the PAID control renders: candidate 0's head layer with the key light rotated (M8), or unrotated (its known-good, M3's consecutive frames) — the order render's own head call on the master's own file; booked through `bakeoff/ledger.py` | Blender |
| `face_v04_1.json` | M1's FACE: 1595 of the default head's 4200 vertices (`slice/measurements/face_shape_distance.py`'s rule) | — |

Tests: `tests/test_bakeoff_separation.py`, `test_bakeoff_frame_metrics.py`, `test_bakeoff_controls.py`,
`test_bakeoff_identity_metrics.py`, `test_bakeoff_rows.py`, `test_bakeoff_metric_record.py` (CI, no Blender).

## The metrics as defined here

A **row** is one run × one tier (protocol §10); every per-frame value is aggregated over the tier's frames
(`rows.tier_frames`) — the mean, except M6 (the worst frame: a shot fails on its first failing frame) and M10 (the largest
difference). A frame with nothing to measure gives no value (never a 0); a row with no value on any frame is the sentinel
`UNKNOWN` with its reason (`record.result_row`). M9 is human review only (§8): `NOT_VERIFIED` on every automated row.

| ID | Value (better) | Read on | Known-good | Known-bad (gross; near-boundary recorded) | Margin `m` (drafted) |
|---|---|---|---|---|---|
| M1 | mm (lower) — the RMS of the mean-removed per-vertex displacement over the FACE, the candidate's HERO_HEAD against the child's own truth **in the same frame of the same shot** (same performance on both; the socket frame) | geometry | the child's truth against itself: 0 mm exactly (the estimator reads vertices, not pixels) | identity swap: every unordered pair of children's truths, frame-matched | 1.0 mm |
| M2 | mm (lower) — M1 over a state's frames less M1 over front_neutral's | geometry | as M1: 0 | the swap inside the state while front neutral stays the child's own | 1.0 mm |
| M3 | ratio (lower) — the head's mean luma over consecutive frames: mean of \|m(t−1) − 2m(t) + m(t+1)\| / m(t) | FINAL + the head's alpha | candidate 0 over the repeats | ±3 % luma on alternate frames inside HEAD_HOLDOUT (±1 % and the 1-px edge jitter recorded) | 0.04 |
| M4 | px (lower) — the head edge's mean displacement along the seam against the default head's: Σ\|Δα\| of the two head layers over the seam zone (slice/seam_extend: the welded, camera-facing ring ± 6 px) / the counted ring's length; the luma and chroma differences in the zone recorded beside it | head alphas + FINAL vs the default head's composite | candidate 0 | SEAM_SHIFTED 5 px; HEAD_SCALED +5 px (1 px of each recorded) | 1.0 px |
| M5 | IoU (higher) — the hair as the camera sees it (nearer than the head, body and hand), candidate vs the child's truth, frame-matched, 25 % resolution, every 4th frame | geometry | the truth against itself: 1 | hairstyle swap: every pair of children of different hair classes | 0.10 |
| M6 | fraction (lower) — where the front plate is opaque over the candidate's head (eroded 3 px at 4K), the pixels differing from the default head's composite of the same frame by > 5 % | FINAL vs the reference | candidate 0 | the head layer over FINAL (the head over the hand) | 0.5 |
| M7 | ΔE00 (lower) — the median over pairs across the seam (every 8 px along the counted body ring, each side's skin 6 px from it in a 7-px square) of CIEDE2000, through the pinned OCIO to `sRGB - Display` / `ACES 2.0 - SDR 100 nits (Rec.709)` | FINAL | candidate 0 at the master's tone | the body one ladder step darker (middle − lightest) through the production re-tint; a quarter step recorded | 2.0 |
| M8 | radius units (lower) — the head's skin: the luma-weighted centroid's offset from the area centroid, candidate vs the default head's layer of the same frame | head layers | candidate 0 | key light rotated 30° on the head layer only (10° recorded) — a **PAID re-render** | 0.05 (read with its control 2026-10-30: kept, recorded per shot) |
| M10 | the largest difference between two repeats of the same inputs (0 when bit-identical); pixels over 2e-3 recorded | any layer | its own control | — | reported, not ranked |

**Margins** are drafted by the agent in the TD role, before any candidate output, and pending the TD's affirmation
(preregistration §6): M4 — an edge displaced by a pixel on average, the near-boundary controls' own size; M1, M2 — half the set's minimum difference between two children (2.0 mm, owner 2026-10-24); M3 —
what the near-boundary ±1 % flicker reads (4 · 0.01 / (1 ± 0.01) ≈ 0.04); M5 — ENGINEERING JUDGMENT; M6 — half the
overlap; M7 — twice a just-noticeable CIEDE2000 difference; M8 — ENGINEERING JUDGMENT, kept after its control was read (weak under a soft key; per shot).

### The dry reading before Stage 3 (2026-10-30)

`measurements/stage5_dry_2026-10-30/summary.json` (archive: `archive/runs/stage5_ground_truth_2026-10-30` and, for M3 and M8,
`archive/runs/stage5_control_render_2026-10-30` — the two small renders the owner approved, 0.2 Mac hours on the ledger). No candidate
output exists or was read. One repeat of candidate 0, so the per-frame verdicts are UNVERIFIED — Stage 5 decides on
Stage 4's R repeats.

| ID | Known-good | Known-bad (gross) | Near-boundary | Dry verdict |
|---|---|---|---|---|
| M1 | 0 mm (8 children × 6 rows) | 2.43–4.91 mm, mean 3.46 (28 pairs × 6 rows) | — | VALIDATED (3 SE 0.34 mm) |
| M2 | 0 mm | 3.46 mm mean, the swap inside each of 15 states | — | VALIDATED |
| M3 | 0.015 (0.0007–0.048; 22 triples of two 13-frame windows) | 0.120 (±3 %) | 0.040 (±1 %); the 1-px jitter reads exactly the known-good | VALIDATED |
| M4 | 0.000 px (9 frames) | 1.92 px (shift 5), 4.90 px (scale +5) | 0.39 px (shift 1), 0.97 px (scale +1) | VALIDATED |
| M5 | IoU 1 | IoU 0.43–0.78, mean 0.58 (hair-class pairs) | — | VALIDATED |
| M6 | 0 (one frame) | 0.977 (one frame) | — | NOT_VALIDATED: only SHOT_003 1338 has the hand over the head |
| M7 | 0.92 ΔE00 (0.36–1.57) | 14.2 (one step darker) | 2.08 (a quarter step) | VALIDATED |
| M8 | ≤ 5e-7 (the unrotated render, 12 frames) | 0.095 (key 30°): SHOT_002 0.20, SHOT_001 0.047, SHOT_003 0.037 | 0.030 (key 10°) | VALIDATED pooled, weak where the key is soft |
| M10 | — | idle: the head layer bit-identical in 18 of 19 pairs, the shadow multiply ≤ 0.00098; loaded: ≤ 0.00098 and the one-pixel spike 0.0347 | — | recorded |

The default head scored against each child — a candidate with no likeness at all — reads M1 2.01–3.22 mm and M5 IoU
0.47–0.89, per child (`ground_truth.json` → rows → `no_likeness`): a candidate's M1 for a child is read against that
child's own value — at or above it, the candidate carries no more of the child's face than the master's own head does.

### What the measurements changed (2026-10-30)

- **M1 is frame-matched over the whole FACE, not a "stable region" against front neutral.** The pre-registration's known-good
  for M1 ("the sheet in the state against the sheet in front neutral") is an image estimator's; on geometry it would read
  the expression, not the identity. The expression-stable part of the default head (vertices the 26 channels move ≤ 0.25 mm
  summed at their extremes: 371 of 1595, the forehead and the upper nose) keeps too little identity: two of the children
  differ there by 0.69 mm against 2.43 mm over the whole FACE. Frame-matched, the expression is the same on both sides and
  the whole face counts; the files are refused if their FACE_CTRL channels differ (the same performance).
- **M4's value is where the head's edge lies, not the luma in the seam zone.** The luma moves with the body's tone: the
  tone control read 0.19–0.21 there on SHOT_001, more than the 5-px shift (0.02–0.045); the edge displacement read 0.00 on
  the default head and under the tone control, 0.45 / 1.1 px for the 1-px shift / growth and 2.2 / 5.4 px for the 5-px ones.
- **M6 compares with the default head's composite, not with the sharp front plate.** The post-composite motion blur moves
  a moving hand off its sharp plate: on SHOT_003 1338, 30 % of the overlap was > 5 % off the plate on the correct
  composite, 0 % off the reference; the head over the hand reads 97.7 %.
- **M7 pairs across the seam, not two bands' medians.** The bands read the light across the neck (2.5–7.7 ΔE00 on the
  default head's own frames at the master's tone); pairs at the same place along the ring read 0.7–1.6.
- **The hair's coverage is depth-tested.** Without it the back of the hair projects over the whole face and the bangs over
  the forehead are invisible (protocol: "hair-crossing-forehead handled").
- **The controls go through the production per-frame composite** (`slice/composite_order.compose_frame`, bit-identical to
  the order path on an unchanged head), written even where the per-order gate fails — a shifted head leaves its holdout
  unfilled, which the order path rightly refuses.

**M3 and M8, what the reading says about them.** M3 reads the head's mean luma, so it cannot see a rigid jitter (the
head and its alpha move together and the mean stays) — a head sliding against the body is M4's, per frame; and fast motion
alone reads up to 0.048, so a ±1 % flicker is not told from motion, a ±3 % one is. M8 depends on the light: a 30° turn of
the key moves the skin's shading centroid 0.16–0.24 radius under SHOT_002's strong light and 0.02–0.08 under SHOT_001's
and SHOT_003's soft key, where the gross control reads at or under the margin — the pooled verdict is carried by SHOT_002;
Stage 5 records M8 per shot beside the pooled verdict. **The control tool reproduces the order render**: unrotated, the
first call of a session equals the order render's own first call within the GPU's repeatability (2 of 8.3 M pixels over
2e-3, at most 0.0039); a later call differs more (SHOT_003 1286: 341 pixels, up to 0.08) after the order render's shadow
call at half resolution in between — likely the session's history, not isolated; "the same inputs" for M10 includes the
sequence of calls in a session.

## Not done here

- **A candidate's own skin and hair mattes** (M7, M8 for any head but the default one): the order render does not write
  them; the stage scripts add them for the bake-off's runs.
- **The embedding estimator of M1** (owner 2026-10-30: later, with a named local model and its licence).
- **M6's verdict** needs the `hand_over_face` window's frames over R repeats (Stage 4): one package frame has the hand
  over the head.
- **subject_09** waits for its v02.
