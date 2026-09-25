# ADR-0002 amendment — motion faster than a frame (vectors to the shutter's ends, nine sub-frame samples)

## Status

**APPROVED — 2026-09-25 by the owner («утверждаю»); merged into ADR-0002 the same day,
`master_contract_version = 4`; implemented — see §Implemented.** It changes D5 row 14 (the time
base of the motion vectors), D7 (the number of sub-frame samples) and how §Validation criteria 2
and 8 sample time (CLAUDE.md §9: changing an approved ADR). The evidence was produced by experiment scripts committed as
`slice/measurements/blur_1209_*.py`; the record is
`slice/measurements/blur_1209_investigation_2026-09-25.json`.

## What was found

On the contractor's SHOT_002 v01 the laugh's fastest nod — frame 1209, a close-up — fails two
gates: **blur fidelity** (the post-composite blur's head error 0.057 at 100 % against 0.02; it beats
no blur 2.8× but a doubled shutter only 1.2×) and the **round-trip against the blurred matte**
(IoU 0.99925 against 0.9995, centroid 0.40 px). The centre-sample round-trip is at the floor on
every frame: the export places the head exactly. The nod is a pulse shorter than a frame — the head
turns 0.35, then 3.95, then 2.43 °/frame over 1207–1210, travels 34 px (median; 74 px max) during
the 180° shutter of 1209 at 4K, and reverses inside the shutter of 1210.

Five hypotheses were tested one variable at a time. Two root causes survived.

**1. The blur's path is built from vectors to the previous and next FRAME.** Cycles' Vector pass
gives the displacement to frame ±1; the blur draws a quadratic through those two positions and the
centre and reads it at ±¼ frame. A pulse faster than a frame puts the shutter's true ends
elsewhere: measured from the exports' sub-frame samples, the quadratic misses them by 6.2 px median
(p95 9.0, max 13.1) on 1209 at 4K. Rendering the same frame with the time stretched ×4 moves every
per-layer Vector pass to ±¼ frame — the shutter's own ends — and leaves the picture unchanged
(p99 difference 0). **With those vectors and nothing else changed, the same blur code passes:**
head error 0.057 → 0.018 at 100 % (0.046 → 0.018 at 25 %), 9× closer to the truth than no blur and
4× closer than a doubled shutter. Hair 0.057 → 0.010, eyes 0.173 → 0.034, silhouette 0.117 →
0.037. The reference itself was not the problem: re-rendered with nine time points instead of
Cycles' default, it moved the old blur's error by 0.0003.

**2. Three sub-frame samples cannot describe such a pulse.** D7 exports the socket, camera, joints
and deformed head at −¼, 0, +¼ frame; the round-trip interpolates between them. Every blurred
reference — two, three or nine time points — sits 0.41–0.64 px from that integration along the
motion, and linear, midpoint and quadratic integrations of the same three samples differ from each
other by up to 0.5 px. **Exported with nine sub-frame samples and integrated over the nine exact
poses** against a reference rendered at the same nine instants, the centroid offset falls to
0.055 px on 1209 (was 0.34–0.47) and 0.106 px on 1210 (was 0.64). The contractor's export is exact
at its samples; the contract samples too sparsely.

Neither is SHOT_002's fault, and the acting must not be damped for it (standing rule). SHOT_001's
laugh passes only because its nod is smaller on screen (1090: 3 px of path error); SHOT_003's fast
turn (≥ 210 °/s) is the hardest case of the slice.

## Proposal

**C1. Vectors to the shutter's ends (D5 row 14).** Every per-layer Vector pass of the master
describes the displacement to the shutter's open and close instants (±½ shutter), not to the
previous and next frame. The renderer produces it from the same render: the plates are rendered
with the time stretched by 2 / shutter (×4 at 180°), which leaves the picture unchanged and moves
the pass's reference instants to the shutter's ends — no extra render. The post-composite blur's
quadratic then runs through open, centre and close. The time base is recorded beside the sign
convention in the package. **The head technology delivers its head layer's vectors in the same
convention**; the export's sub-frame poses (C2) give it the shutter-end positions.

**C2. Nine sub-frame samples (D7).** The export carries the socket, camera, joints and the
deformed default head at nine instants across the shutter (every 1⁄16 frame at 180°) instead of
three. The blurred-matte round-trip integrates the nine exact poses with trapezoid weights against a
blur reference rendered at the same nine instants (Cycles motion steps 4, recorded in the render
manifest); the blur-fidelity reference is the same render. The head technology gets the master's
motion at the same resolution.

## Cost

- C1: none at render time (the same render; the stretch changes only what the Vector pass refers
  to). The per-order blur keeps its sample rule (K follows the path).
- C2: the export grows about ×3 — 26 → 75 MB per shot, almost all of it the QC-only deformed head;
  the blur reference with nine time points renders in 42–44 s per 4K frame against 40–42 s
  (`MASTER_COST` per master version, never per order).
- No contractor work: the export is ours, from his file.

## Alternatives

- **Render the real 3D blur per order** (the head technology renders its head blurred) —
  compositing blurred layers is exactly what drew the seam line the 2026-09-22 amendment removed.
- **More blur samples** — the information missing is where the pixels are at the shutter's ends,
  not how finely the path is cut.
- **Head-only fix** (vectors from the export's geometry for the head layer) — the body and the
  hand plates would keep frame vectors, and they move with the same laugh.
- **Loosen the fidelity gate, or slow the laugh** — the first passes a wrong blur, the second
  breaks the standing rule and damps the acting the product is for.

## Does not solve

- **The mouth opening inside the shutter** — teeth and tongue appear during it, which no warp of a
  sharp frame can make (region error 0.12 on 1209; the head as a whole passes).
- **Hard shadows sliding over the face** during a fast nod (face region 0.025) — the same limit of
  any 2D warp; small here.
- The sub-frame sampling of the head technology's own renderer is its concern at the bake-off.

## Validation after approval

Render with stretched vectors in `render_passes.py`, the time base in the vector convention and
`motion_blur.py`; the export with nine sub-frame samples; the round-trip's trapezoid integration and
its reference at nine instants. Tests: a synthetic pulse faster than a frame is blurred right with
shutter-end vectors and wrong with frame vectors; a round-trip on a sub-frame pulse passes with nine
samples and fails with three. Then `check_asset.sh` at 25 % and 100 % on SHOT_001 and SHOT_002:
blur fidelity and the round-trip pass on every frame of every window.

## Implemented (2026-09-25)

**C1.** `render_passes.py` renders the plates with the time stretched by 720 / shutter angle
(Blender's time remapping, ×4 at 180°) and records `time_stretch`, `vector_reach_frames` (¼ frame)
and `vectors_point_at` in the render manifest; the lighting probe is rendered at the shot's own
frame; a scene that remaps time itself is refused by the export and by the render, because the
stretch is set absolutely. `split_bundles.py` writes the time base beside the sign convention on
every `*MOTION_VECTORS` part and refuses a video render without it. `motion_blur.py` takes the reach
on every call (path parameter u = t / reach); `composite.py` and `check_blur_fidelity.py` read it
from the render manifest and refuse plates without it — plates rendered before this amendment carry
vectors to frame ±1 and are re-rendered, never blurred on a guess. The doubled-shutter control is
now the same path twice as long (every layer's vectors ×2): the vectors reach only the shutter's
ends, and extrapolating the quadratic past them would add a shape error the control is not about.

**C2.** `conventions.json → exports.sub_frame_offsets_frames` holds nine offsets, every 1⁄16 frame
across the 180° shutter (the export, `check_exports.py` and the Alembic comparison were already
generic over the list; SHOT_002's export grows from 27.2 to 78.5 MB). `render_passes.py
--blur-reference` sets every object's Cycles motion steps to 4 — 2³ + 1 = 9 time points, the exports'
own instants — records `motion_steps` and `shutter_time_points`, and lists objects whose own motion
blur is off (none on either shot). `roundtrip.py` integrates the nine exported samples with
trapezoid weights and refuses a reference sampled at other instants. `master_contract_version` 4.

Tests (CI or the slice machine; the full suite, 177, passes): a synthetic pulse shorter than a frame
is blurred right only through shutter-end vectors (0.008 against 0.059 through frame vectors); a
disc head jumping 40 px inside the shutter round-trips with nine samples (centroid 0.012 px) and
fails with three (1.50 px, the gate's centroid); plates without the reach, a reference at other
instants and a scene that remaps time are refused; the render manifest and the package carry the
time base.

**Found while validating — three additions.**

1. *Nothing compared the time-stretched plates' head with the exports* — the round-trip's blurred
   matte comes from the unstretched reference. The centre sample is now also gated against the
   plates' own sharp `HEAD_HOLDOUT` (`plate_centre_sample`); on every frame measured it sits at the
   floor (IoU ≥ 0.99998, centroid ≤ 0.006 px): the stretch leaves the head where it was.
2. *The reference's own resolution.* At 100 % frame 1209 still failed the round-trip — on IoU alone
   (0.99929 against 0.9995), with the centroid at 0.054 px, which is what C2 promised; the
   investigation had measured C2 on the centroid only. The cause is the reference, not the export:
   its alpha is a Monte Carlo estimate quantized to 1/64 (every ramp pixel is exactly k/64, 2 690 of
   them exactly 0.5), and across the nod's blur ramp the 0.5 contour it draws is known only to about
   1/(n·g) px for n samples and a coverage gradient g per px. Ties counted inside, outside or split
   leave the IoU where it is (the excess is symmetric noise, not a bias); a 33-instant integration
   (Cycles' own motion-step model) leaves it too; the same exports, plates and code against a
   256-sample reference pass (0.99970; p95 0.50 → 0.25 px). `matte_metrics.reference_quantization_px`
   estimates that floor from the re-projection itself — the measured IoU boundary error is the
   estimate plus a constant 0.08 px at both sample counts (0.309 = 0.228 + 0.08; 0.133 = 0.057 +
   0.08). `roundtrip.py --plan-reference-samples` computes from the exports how many samples the
   reference needs (to 0.04 px, PROVISIONAL), `check_asset.sh` renders it so, and the round-trip
   records the estimate per frame and names the reference, not the export, when a frame fails
   within it. This keeps every gate as it was; the cost is render time on fast frames, a
   `MASTER_COST` line per master version: 1209 at 4K plans 384 samples, 232–236 s per frame against
   ~40 s.
3. *The blur-fidelity noise floor was optimistic.* A reference rendered with the plates' own sample
   count shares their Monte Carlo pattern: on the static frame 1121 at 25 % it sat 0.003 from the
   plates, while a 256-sample reference sits 0.010 from the plates and from the same-count reference
   alike. The honest floor at the video profile's 64 samples is 0.0075–0.010 of the 0.02 bound, not
   the 0.004 recorded on 2026-09-22; the planned reference measures against it.

**Validated — full `check_asset.sh` on fresh renders of both delivered v01 files, 64-sample plates,
the reference planned; SHOT_002's other state windows at 100 % through the same chain. Every gate
passes on every frame.**

| Shot, scale | Frames | Reference (planned) | Blur fidelity, head: blur / no blur / doubled | Round-trip on the blurred matte: IoU (min 0.9995) / centroid |
|---|---|---|---|---|
| SHOT_002, 25 % | 1121, 1209, 1210 | 256 samples | 1209: **0.0144** / 0.111 / 0.123 (was 0.046) | 1209: 0.99967 / 0.014 px |
| SHOT_002, 100 % | 1121, 1209, 1210 | 384 samples | 1209: **0.0120** / 0.161 / 0.132 (was 0.057) | 1209: **0.99976 / 0.055 px** (was 0.99925 / 0.40) |
| SHOT_002, 100 %, windows | 1144, 1164, 1185, 1228 | 128 samples | 1164: 0.0096 / 0.033 / 0.051 | ≥ 0.99992 / ≤ 0.022 px |
| SHOT_001, 25 % | 1001, 1090, 1094 | 128 samples | 1090: 0.0101 / 0.021 / 0.028 (head path 7.9 px: below 8, not discriminating) | 1090: 0.99968 / 0.015 px |
| SHOT_001, 100 % | 1001, 1090, 1094 | 320 samples | 1090: **0.0069** / 0.027 / 0.031 (was 0.0135 / 0.025 / 0.018) | 1090: 0.99986 / 0.075 px |

On the frames whose head moves less than 8 px during the shutter (not required to discriminate) the blur sits on the noise floor, 0.006–0.011. The p95
boundary distance is on its 0.25 px floor on every frame; the plates' centre sample is on the floor on
every frame; the stills (1050, 1215) and criterion 3 with the seam criterion pass as before. SHOT_001
1090's doubled-shutter margin, 1.33× before the amendment, is 4.5×. `check_asset.sh` at 100 % takes
34–36 min per shot, of which 10–12 min is the planned reference.

Scripts: `slice/measurements/subframe_v4_roundtrip_reference.py`,
`slice/measurements/subframe_v4_fidelity_noise_floor.py`; record
`slice/measurements/sub_frame_motion_2026-09-25.json`.
