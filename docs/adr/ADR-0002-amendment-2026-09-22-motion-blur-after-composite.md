# ADR-0002 amendment — motion blur after compositing; seam overlap margin

## Status

**APPROVED by the owner — 2026-09-22, and merged into ADR-0002 the same day** (Status line, §D1,
§D5 row 14 and the new paragraph, §D7, §D9, §Validation criteria 3 and 8, §Consequences);
`master_contract_version` = 2. The owner chose the direction ("path A": blur after compositing,
over leaving the defect or a hybrid that renders every order's head twice) and approved this text.
This document stays as the record of the evidence, the numbers and the alternatives; ADR-0002 is
the contract. Implementation is tracked in PROJECT_STATE.md and is not finished — the ADR text is
what a master must satisfy, and no master production has begun.

Layer: Core. Escalation (CLAUDE.md §9): it changes an approved ADR, and item 2 moves a stage into
the per-order path whose cost is not yet measured.

## Context — what was measured

Evidence: `slice/measurements/composite_seam_motion_blur_SHOT_001_v01.json` and
`slice/measurements/seam_research_2026-09-22/`. SHOT_001 v01 (burst 2), the "ha" peak of the laugh.

1. **§D5 composite fails under relative motion.** FRONT over (HEAD over BACK) with layers rendered
   *with* 3D motion blur does not reproduce the full render where the body moves fast under a nearly
   still head. The precomp gate fails on 5 of the 13 laugh-peak frames (1088, 1090, 1093, 1095, 1096 at
   25 %; 1090 at 100 %: 0.864 against 0.90), and at 100 % the seam ring shows as a **visible contour
   across the neck** that the full render does not have. Without motion blur the same frames pass
   (0.973–0.994). Cause: "over" of two time-averaged layers is not the time average of the composite
   when coverage and the plate behind it move differently during the shutter. No seam geometry and no
   shadow-pass change can fix it. Composite-side variants were measured and did nothing
   (0.867 → 0.865–0.869).
2. **A second, independent seam defect: coincident geometry.** The default head's overlap band below
   the socket boundary lies **on** the body neck. As delivered, band-to-skin distance over all
   120 frames runs from exactly 0 to 6.7 mm outside. The head is rigid on the socket while the neck is
   skinned to head/neck/spine/shoulders, so the two fight for depth. Tucking the band ≥ 2 mm inside on
   every frame lowers the seam error on calm frames by a third to a half (1001: 0.954 → 0.971,
   1094: 0.948 → 0.970), and the silhouette gate still passes. It does not touch the motion-blur
   defect (1090: 0.867 → 0.888).
3. **Blur after compositing, done by layers, fixes the seam and stays close to the true blur.** Each
   sharp layer is warped along its **own** motion vectors to K instants of the shutter. The layers are
   composited at every instant, then averaged. Measured against a true 3D-blurred render (1024 spp) on
   1084–1096 (4×4 low-pass, noise floor ≈ 0.004):

   | mean error vs true blur | layered blur (this amendment) | Blender VecBlur | no blur |
   |---|---|---|---|
   | head | **0.0076** (best on 13/13 frames) | 0.0175 | 0.0127 |
   | seam zone | **0.0156** | 0.0271 | 0.0258 |

   The sharp-domain seam gate passes on every frame (≥ 0.973 inside the band). At 100 %, frame 1090
   shows no seam contour. Two details were measured, not assumed: Cycles stores the backward and
   forward vector pairs with **opposite sign conventions**, and the motion path must be **quadratic**
   through the previous/current/next positions. A straight line over-blurs at the turning points of
   a laugh bounce.

## Decision (proposed)

### A1. §D1 — seam overlap margin (new bullet)

- **Overlap margin.** Head geometry that continues below the socket boundary curve (the band that
  closes cracks from inside) lies **inside** the body neck on every frame of every shot. Its signed
  distance to the evaluated body surface is ≤ −M. The margin is ramped from 0 at the boundary curve
  to M at depth R below it. Surfaces that coincide with the body skin (distance 0) violate the
  contract. First values `PROVISIONAL`: **M = 2 mm, R = 2 mm**, the ones measured on the slice. The
  check runs on all frames, not on the rest pose: the head is rigid, the neck is skinned. It applies
  to the default head and to every head technology that delivers geometry. For a technology that
  delivers only images the rule is vacuous; its seam is judged by the composite gates.

### A2. §D5 / §D7 — motion blur is applied after compositing, not rendered

- **Render.** In the video profile every beauty-type layer (rows 1, 3, 4, 9 and the row-13 pair) is
  rendered with **shutter 0**. Each layer carries its **own** forward and backward motion vectors
  and depth. Per layer matters because a layer's hidden surface — the neck under the head — moves
  differently from the front-most surface that a single data layer describes.
  `shutter_angle_deg` and `shutter_position` (§D7) stay in the package. They now define the blur
  applied in compositing, not a render setting.
- **Row 14 amended:** motion vectors per layer, from the same shutter-0 render, full float, sign
  convention recorded in the package (measured: backward pair `(+x, −y)`, forward pair `(−x, +y)` into
  array coordinates on Blender 5.2.1). Consumer: the post-composite blur. The head technology no
  longer matches motion blur.
- **Head technology deliverable:** the head layer **sharp**, with its own vectors and depth in the
  same convention. This replaces "motion-blur matching". Every candidate finds it simpler; one that
  cannot deliver vectors has excluded itself (bake-off exclusion list).
- **Per-order composite:** at each of K instants of the recorded shutter, warp FRONT, HEAD and BACK
  along their vectors on the quadratic path, composite FRONT over (HEAD over BACK), then average the
  K composites. K follows the largest displacement in the frame: at least one instant per ~1.5 px of
  path, measured at 1090 at 100 % as 57 px of path → K = 48. The contract fixes the inputs, the
  convention and the fidelity check below. The implementation is replaceable.
- **Still profile (§D9) unchanged:** it was already shutter 0. Video and still now render the same
  way.

### A3. §Validation — gates

- **Criterion 3 (precomp reproduction)** is evaluated on the **sharp** layers, same thresholds
  (`PROVISIONAL`).
- **New criterion — blur fidelity.** Per shot, on the frames with the fastest head and relative
  motion (chosen by `pick_frames`), the master renders a **true 3D-blurred** default-head reference
  at high samples. The post-composite blur of the default head must match it within a `PROVISIONAL`
  threshold on a low-pass metric. Negative controls must fail: no blur, and a doubled shutter
  (invariant 12). The reference renders are a `MASTER_COST` line, per master version, never per
  order.
- **Noise.** Sharp layers must be clean enough that the blur does not streak render noise along
  the motion, which is visible at 100 % on 64-spp inputs. Samples or denoising are a TD setting,
  recorded in the package and caught by the fidelity criterion.

## Consequences

- **Per-order cost — to be measured before master production.** The head renders without 3D
  motion blur, which is cheaper. The blur becomes a per-order compute stage. The measured
  prototype is single-threaded numpy at **3.7 min per 4K frame**, which is **not** a production
  number: a GPU implementation is a different order of magnitude. Production implementation and
  its per-frame cost are a prerequisite, recorded in `docs/costs/cost-model.md` terms. Until
  measured, `per_order_blur_cost = UNKNOWN`.
- **Look.** A 2D blur is not a 3D blur. It approximates rotation about the view axis, fast
  deformation, semi-transparent hair edges and occlusion edges. The fidelity criterion measures it
  per shot. On the slice it was closer to the true blur than any alternative, not identical to it.
- **Seam:** consistent by construction for every head technology — the property the interface
  exists for (invariant 15).
- **Contractor / animation:** unchanged. The change is in our render profile, compositor and
  gates. The default head needs the A1 margin: burst 1 v04, head shell only, no re-animation.
- `master_contract_version` 1 → 2.

## Not yet proven

SHOT_002 (turn to profile, strong coloured light) and SHOT_003 (hand over the face — FRONT
occluding the head — and a fast look-away ≥ 210 °/s); hair edges in motion; a head other than
the default; production speed; the scaling of K and of the noise requirement across shots. Each
is a gate run on the slice before master production, not a reason to reopen the direction.

## Alternatives considered

- **Keep 3D blur, accept the seam contour** — a visible seam on the child's head on every fast move.
  Rejected by the owner.
- **Relative-motion tolerance in the gate** — weakens a quality gate to pass a visible defect.
  Rejected.
- **Hybrid: 3D blur everywhere, layered blur only near the seam** — renders every order's head
  twice. A per-order cost for a patch; kept as the fallback if the fidelity criterion fails in a
  class of shots.
- **Composite-side fix of the head-shadow multiply** — measured, no effect.
- **Blender's VecBlur on the composited frame** — measured: further from the true blur than no blur
  on the head (0.0175 vs 0.0127). A single-image blur has no layer information.
- **Deep compositing** — no deep output from Cycles in the pinned toolchain.

## Rollback

The render still supports 3D motion blur, and the contract version tells a package which mode it
was built in. A master built under version 2 re-renders under version 1 with the shutter turned
back on (§D11 rebuild recipe).

## Also raised, not decided here

`gaze` in §D8 is one yaw/pitch pair for both eyes. It cannot converge on a near target (measured at
~30 cm: 0.2° and 9.9° off), and a head with a different eye spacing would miss differently for the
same numbers. A gaze target point in socket space would let every head compute its own vergence.
This is a separate amendment for the owner. The slice aims between the eyes meanwhile.

## Updated on approval (2026-09-22)

Done in the approval commit: ADR-0002 (Status, §D1, §D5, §D7, §D9, §Validation, §Consequences);
`docs/experiments/phase-0-5-slice-brief.md` (row 14, shutter row); `docs/architecture/master-spec.md`
(seam section); `docs/experiments/bakeoff-protocol.md` (`EXCLUDED_BY_CONTRACT`).

Implementation, tracked in PROJECT_STATE.md: `slice/conventions.json` (video profile, vector
convention, seam margin); `slice/render_passes.py` (sharp layers, per-layer vectors);
`slice/composite.py` (the blur stage); a seam-margin check and the blur-fidelity gate — each with
its negative control; burst-1 v04 of the head shell for the §D1 margin.
