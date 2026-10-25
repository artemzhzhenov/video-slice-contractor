# ADR-0002 amendment — the round-trip integrates the shutter densely enough for thin, fast hair

## Status

**APPROVED — 2026-10-24, on the owner's go to settle the thin-hair rule («займись правилом обратной проекции для тонких
волос»), with the option the TD recommended; implemented — see §Implemented.** It changes how §Validation criterion 2 (the
D7 round-trip) samples time; it adds no threshold and loosens none (CLAUDE.md §9: a quality gate is not removed or
weakened). The finding: `slice/measurements/roundtrip_hair_probe.py` and `slice/measurements/subject_01_acceptance_2026-10-18.json`;
the validation record: `slice/measurements/roundtrip_thin_hair_2026-10-24/`.

## What was found

On the burst-3 pilot child `subject_01` (curly high-volume hair, 1 059 curls) SHOT_001 frame 1101 — the fastest frame of
the slice, a head path of 108 px across the shutter at 4K — failed the round-trip at **p95 1.35 px** (gate 0.5) with the
export correct. The probe split the contour error: the hair's own silhouette p95 2.2 px, the face 1.0; and the same export
integrated at 33 instants instead of 9 passed at **0.25 px**. The default head on the same frame passes at 9.

Why: the blur reference (Cycles, motion steps at the export's nine instants) integrates the shutter *continuously*, the
vertices moving linearly between its time points. The round-trip summed the head's coverage at the nine instants
themselves. A solid edge comes out right either way (the 0.5 level of a nine-step staircase sits where the continuous ramp
crosses it), but a curl a few pixels wide moving 13.5 px between two instants is stamped as dots where the renderer draws a
band — the comparison measures the integration, not the export.

## Decision

The round-trip integrates **the same path** — piecewise linear between the exported samples, the socket and camera
slerped, the vertices linear (`head_at`, `sample_at`, unchanged) — at **denser instants**: between consecutive exported
samples the interval is cut into the fewest equal steps in which no head or hair vertex moves more than
`conventions.json → roundtrip.time_integration.max_step_px` (**2.0 px, PROVISIONAL**) on screen; the weights are the
trapezoid rule on that grid (`slice/roundtrip.py integration_instants`). Wherever no interval needs cutting the instants
and weights are exactly the nine-sample trapezoid of the 2026-09-25 amendment, and the result is bitwise unchanged. The
negative controls (translation, scale, rotation), the rest-head comparison and the planning of the reference's samples
use the same instants. Each frame's report records its instant count and, per interval, the screen motion and the cut.

The export does not change (nine samples, contract version unchanged); the reference render does not change; the
thresholds do not change.

## Alternatives

- **Loosen the round-trip on hair** (a separate threshold for the hair contour) — would hide a hair placement error of the
  same size; the test would stop testing the hair it exists to place.
- **Leave hair out of the round-trip** — the hair is part of the head layer the head technology delivers (D3); its
  placement is exactly what the test must catch.
- **Export more sub-frame samples** (17 or 33) — the export grows ×2–4 for every shot and every head, while the motion
  between the nine is already piecewise linear in the reference itself; denser integration of the same samples is
  equivalent and costs only QC time, only on fast frames.

## Cost

QC compute only, never per order: a frame is cut only where its motion asks for it. Measured on the pilot run (three
frames): 1001 — 9 instants, 1094 — 11, 1101 — 46; the round-trip took 32.6 min against ~14 before. Per-frame instant
counts are in each report.

## Validation

- `tests/test_slice_roundtrip.py::test_thin_fast_strands_are_swept_by_the_dense_instants_and_slow_motion_is_integrated_as_before`:
  a comb of irregular thin strands travelling 80 px across the shutter — the coverage error against 257 exact instants
  falls 3.8× (0.034 → 0.009) and the contour 3× (p95 6.25 → 2.0 px); moving 4 px, the instants, weights and coverage are
  the nine-sample ones exactly.
- The pilot `subject_01` SHOT_001 run re-measured (shadow copy of the archived run): 1101 **PASS** — p95 0.25 px, centroid
  0.047 px, IoU 0.9998 (was 1.35 / 0.063 / 0.9994); the translation, scale and rotation controls still fail on every frame;
  1001 bitwise identical to its accepted record.
- The accepted runs re-measured: see §Implemented.

## Implemented (2026-10-24)

`slice/roundtrip.py` (`screen_uv`, `integration_instants`; the per-frame loop, the controls, the rest head and
`plan_reference_samples` take its instants), `slice/conventions.json → roundtrip.time_integration.max_step_px` and its
rule; the test above. **Regression on the archived accepted runs** (2026-10-24,
`slice/measurements/roundtrip_thin_hair_2026-10-24/comparison.json` and the six new reports beside it; each run's shadow
copy links the archived exports, plates and blur reference unchanged): SHOT_001 v02, SHOT_002 v03, SHOT_003 v06 (contract
v5), the Stage 0 FaceBuilder head, and the pilots subject_01 and subject_02 on SHOT_001 — 18 frames.

- Every run's verdict holds; subject_01 turns FAIL → PASS (1101: p95 1.35 → 0.25 px, IoU 0.99943 → 0.99983).
- The 10 frames whose intervals need no cut (9 instants) are **bitwise** the archived results.
- The 8 fast frames (11–46 instants; up to 11.7 px of screen motion between two exported samples on SHOT_002 1217) all
  pass at p95 0.25 px; the centroid closer on seven (SHOT_002 1217 0.143 → 0.119 px, SHOT_001 1101 0.090 → 0.071) and
  0.001 px further on one (SHOT_003 1338, 0.028 → 0.029); the IoU within 0.00001 of before or higher.
- The translation, scale and rotation controls fail on every frame of every run (VALIDATED); the positive control
  DISCRIMINATING on every run.
- Time per run 6–20 min (SHOT_003 6, SHOT_002 20; the pilot subject_01 33).
