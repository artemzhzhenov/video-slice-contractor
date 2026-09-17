# ADR-0002 — Master ↔ Head Interface

## Status

ACCEPTED — 2026-09-07, by owner instruction to proceed. Amended 2026-09-11: slice ledger (§Validation).
Amended 2026-09-14 from the slice proposal review (`../experiments/phase-0-5-slice-proposal.md`
§8–§9): D2 head as shadow-caster only; D3/D5 row 9 semantics; D5 row 13 as a plate pair; D5 row 14
and D7 shutter fields; D6 alpha `NOT_APPLICABLE` for data passes; D1 envelope recorded on the slice;
D7 round-trip implemented against the matte with per-profile intrinsics (amendment 2026-09-15).
Amended 2026-09-15: D5 row 2 holdout is the unoccluded silhouette (slice compositor measurement).
Amended 2026-09-16: D7 round-trip measured on the real head — controls validated, rest-head
re-projection found to fail open-jaw frames (open defect of the test).
Amended 2026-09-17: D7 re-projects the per-sample deformed default head (defect closed); D8
channel combination rules. Contract version `master_contract_version = 1`.
Validated by the Phase 0.5 reference slice (§Validation); any item that fails validation reopens
this ADR before any master production begins. Layer: Core (`../architecture/layering.md`).

## Context

The master is built once and reused for every order by replacing only the hero's head. That
only works if the boundary between what the master delivers and what the head technology
supplies is a *contract* — fixed before the master is modelled, rigged, lit and rendered,
because every one of those steps bakes assumptions in. The foundation review found that this
interface did not exist: `head_socket` appeared once, in a directory listing; no default head;
no pass set anyone had committed to; no colour, frame-rate or alpha convention; hair assigned
to the head while it lives on the body; skin tone unaddressed although the neck and hands are
body.

Decisions already made by the owner that this ADR implements: the master is 3D (§4.4); skin
tone matches the child on a template body (§3, §4.3); glasses only when habitually worn
(§4.9); 4K minimum and a still render profile for the comic; dub-friendly staging (§4.18).

The head technology itself is **not** decided here (Phase 1 bake-off). This ADR defines what
the socket provides so that any head technology that can consume it is admissible, and any
that cannot has excluded itself — invariant 15.

## Decision

### D1. The head socket

- **Cut boundary.** The neck belongs to the body. The socket boundary is a closed curve on the
  default head's neck geometry, below the jaw and above the collar, shipped as `NECK_PROXY`
  (§D5). The personalized head terminates exactly at this curve; the body's neck is rendered
  to it. A diagram of the curve on the default head is part of the master package.
- **Socket transform.** Pivot at the base of the neck on the boundary curve. Right-handed,
  Y-up, Z-forward (character facing +Z in socket space), metres. Rotation exported as a unit
  quaternion **and** as a 4×4 matrix; Euler angles are never the interchange form. Exported
  per frame with sub-frame samples per §D7.
- **Envelope.** The socket fixes the head's bounding envelope (extent, scale, pivot). Identity
  is expressed as feature shape *within* the envelope, never by scaling the head to the child.
  A candidate whose head cannot fit the envelope is rejected at candidate generation, before a
  parent ever sees it. Envelope tolerance is `PROVISIONAL` until the Phase 7 calibration set
  exists. The first envelope value is the default head's bounding box measured on the Phase 0.5
  slice and written into the package as `PROVISIONAL` (amendment 2026-09-14) — without a number,
  Phase 1's `EXCLUDED_BY_SCALE` has nothing to test against.

### D2. The default head

The master ships a **default reference head**: the archetype head the body was animated,
lit and simulated against. It is not a placeholder — it is the seam reference, the acting
ground truth, the QC known-good, the negative-control baseline for every metric in
`../qc/evidence-and-experiments.md`, and the head against which hand-contact shots were keyed.
The master delivers a **default-head beauty render of every shot** in both render profiles.
It costs nothing extra: it falls out of master production.

**The head is a shadow-caster only** (amendment 2026-09-14): the master's lighting disables
indirect light — diffuse and specular bounce — from the hero head and hair onto the body. The
body plate is rendered with the head absent, so any head bounce in the full render is exactly
the light a precomp cannot reproduce; and head bounce carries the head's skin tone, which is
personalized (§D4), onto a plate that is not. The look cost is a slightly flatter neck under
strong key; the gain is that §Validation criterion 3 is achievable on physical grounds, not by
tolerance. ENGINEERING JUDGMENT; owner may reverse it at the cost of that criterion.

### D3. Hair ownership

Hair lives on the body even though it is personalized.

- Body beauty is rendered **with the hero head and hero hair absent**. No hero hair, no hero
  hair shadow, is ever baked into the body plate.
- The head/hair shadow onto the body is delivered as a **separate multiply/occlusion pass**.
  It is the **default head's** shadow (amendment 2026-09-14): its consumers are QC, seam
  calibration and the negative-control baseline. The per-order comp does not use it — the
  personalized head+hair shadow onto the body is a **head-technology deliverable**, produced
  against the collision proxy and the lighting reference, and a candidate that cannot produce
  it has excluded itself (`../experiments/bakeoff-protocol.md` §2). Using the default shadow
  for a child's head would be a fallback under CLAUDE.md §6 and is not registered.
- The master exports an **upper-body collision proxy** (shoulders, chest, back) and per-frame
  spine and shoulder joint transforms, because hair dynamics are driven by body motion, not
  head motion. Hair simulation is per-child work owned by the head technology; the master
  supplies what it needs to simulate against.
- Supported hair classes (length × volume) are a **closed enumeration** declared at candidate
  generation, so the master is pre-validated against each class rather than against unbounded
  hair. The enumeration's values are set in Phase 1; its existence is decided now.

### D4. Skin tone

- Every exposed hero skin region — head, neck, hands, arms, legs — is delivered as an
  **ID / cryptomatte** separable from clothing, props and other characters.
- Beauty passes are delivered **scene-linear with the grade unbaked**; the grade is a separate,
  reproducible CDL/LUT applied after compositing, so re-tinting is possible at all.
- The **supported tone range is a master property**: lighting is designed and test-rendered
  against the full intended range before the master is approved. An avatar whose tone is out
  of range is a qualification reject, never a silent clamp.

### D5. Frozen base pass set

The "no pass without a consumer" rule applies to *incremental* passes. The base set below is
frozen by this ADR because a missing pass in a finished master costs a re-render at best and,
if the scene organisation did not plan for it, is unrecoverable. Each row still carries the
full contract (`../architecture/master-spec.md`), including `read_granularity` and
`bytes_per_frame` measured on the slice.

| # | Pass | Consumer | Bundle |
|---|---|---|---|
| 1 | Body beauty, hero head and hair absent | compositor | COMPOSITE |
| 2 | Hero head+hair holdout matte — the head's **unoccluded** silhouette (occluders are shadow-only in the head layer); occlusion ordering comes from the foreground plate (row 4) and depth (row 5), never from this matte (amendment 2026-09-15, from the precomp-reproduction measurement) | head technology, compositor | HEAD_RENDER, COMPOSITE |
| 3 | Default-head beauty (§D2) | QC, seam calibration, negative controls | COMPOSITE |
| 4 | Foreground / occluder plate with its own alpha — hands, props, anything crossing the face | compositor | COMPOSITE |
| 5 | Per-frame depth (occlusion ordering for the head region) | compositor, head technology | COMPOSITE |
| 6 | Per-frame camera intrinsics + extrinsics (§D7) | head technology | HEAD_RENDER |
| 7 | Head and neck socket transform, scale, pivot, sub-frame samples (§D1, §D7) | head technology | HEAD_RENDER |
| 8 | Lighting reference per shot: key/fill direction, colour, intensity, plus the light rig or HDRI | head technology | HEAD_RENDER |
| 9 | Default head/hair shadow onto body (§D3) | QC, seam calibration, negative controls | COMPOSITE |
| 10 | Hero skin ID / cryptomatte, all exposed skin (§D4) | compositor (re-tint), QC | COMPOSITE |
| 11 | `NECK_PROXY` and upper-body collision proxy (§D1, §D3) | head technology | HEAD_RENDER |
| 12 | Performance track (§D8) | head technology | HEAD_RENDER |
| 13 | `STATIC_PRECOMP` — everything composited except the head layer, once per master version, delivered as the ordered pair `PRECOMP_BACK` (behind the head) + `PRECOMP_FRONT` (occluders in front of the head, alpha-zero where none) so the per-order comp is two overs in every shot (amendment 2026-09-14) | per-order compositor | COMPOSITE |
| 14 | Motion vectors — forward and backward screen displacement from a blur-off data layer, so they describe motion, not the rendered blur; consumed together with `shutter_angle_deg` and `shutter_position` (§D7). In the still profile they are delivered (§D9) with `consumer: NONE` recorded (amendment 2026-09-14) | head technology (motion-blur matching), compositor | COMPOSITE |

Normals are **not** in the base set: no consumer is known before the head technology exists.
They may be added as an incremental pass with a consumer.

### D6. Conventions

Fixed here because they are catastrophic to change after a master exists and cost one page
now. Everything not listed is set by the render pipeline TD on the Phase 0.5 slice and
recorded in the master package, never left implicit.

| Convention | Value | Basis |
|---|---|---|
| Frame rate | 24 fps | ENGINEERING JUDGMENT — animation standard; all frame counts in the docs assume it |
| Resolution, video profile | 3840 × 2160 minimum | owner, via the comic requirement |
| Resolution, still profile | print resolution per `COMIC_LAYOUT` pixel budget | comic spec §3.1 |
| Working colour space | scene-linear; OCIO config and version pinned in the master package | ENGINEERING JUDGMENT — ACEScg recommended, TD confirms on the slice |
| Display transforms | Rec.709 for video delivery; sRGB, profile embedded, for print | comic spec §3.5 |
| Grade | never baked; separate CDL/LUT after compositing | §D4 |
| Alpha | premultiplied (associated), the OpenEXR convention; **every pass declares** `PREMULTIPLIED`, or `NOT_APPLICABLE` for data passes with no colour–alpha association (depth, motion vectors, cryptomatte, non-image exports — amendment 2026-09-14); a straight-alpha pass is a contract violation | ENGINEERING JUDGMENT — inconsistency, not the choice, is the defect |
| Intermediate format | OpenEXR, multi-part, one file per shot per bundle; half-float beauty, full-float depth/MV/position | ENGINEERING JUDGMENT |
| Compression, overscan, handle frames, sample counts | set by TD on the slice, recorded in the package | measured, not guessed |
| Frame numbering | 1001-based; shot manifest carries `frame_range` | ENGINEERING JUDGMENT |
| Units | metres, seconds, frames | §D1 |

### D7. Transform and camera contract

Per frame, with sub-frame samples at the shutter's open/close (count recorded in the package):

    camera: focal_length_mm, filmback_mm (w, h), principal_point, near, far,
            focus_distance_m, f_stop, shutter_angle_deg, shutter_position, extrinsic_matrix_4x4
            (shutter_position: where the shutter interval sits relative to the frame —
             CENTRED | START | END — with the sub-frame sample count; amendment 2026-09-14)
    socket: matrix_4x4, quaternion, position_m, scale, pivot_m
    joints: spine[], shoulder_l, shoulder_r (matrix_4x4 each)

**Round-trip test**, run on the slice and on every master version: re-project the default head
using only the exported camera and socket data and confirm it lands on the default-head beauty
render within a stated pixel tolerance (`PROVISIONAL`). A master whose export does not
round-trip is not delivered.
Amendment 2026-09-15 (implemented, `slice/roundtrip.py`): the comparison is between mattes —
the re-projected default head (`default_head_rest.obj`, exported in the socket's local frame)
against `HEAD_HOLDOUT` — so the test measures the transform contract and not shading; pixel
intrinsics are exported per render profile (`camera.json → px_by_profile`), because the still
profile's frame is not the video's; the tolerance table and the negative controls are
`slice/conventions.json → roundtrip` (1 px p95 boundary between sub-pixel iso-contours /
0.5 px centroid / IoU 0.995 / band coverage difference 0.05, looser in the STRESS fast-turn
window; a 5-px socket displacement and a 5-px focal growth must each fail the gate on every
frame). Two bounds are stated with it: `HEAD_HOLDOUT` is cut where `C_BODY` or `C_ENV` is in
front of the head (they hold out in `L_HEAD`; only `C_HAND_FG` is shadow-only) — those pixels
are excluded from the comparison and their fraction reported per frame, and a frame whose
excluded fraction exceeds half the re-projected head fails before any metric (a head placed on
the wall would otherwise be excluded instead of failed); and the re-projected
head is the REST head, so frames with facial deformation beyond |0.2| on any channel are
flagged in the report (reported only — no separate thresholds exist yet; they are calibrated
on the real asset, and until then such frames are gated like every other).
Amendment 2026-09-16 (measured on the contractor's v01 head, SHOT_001, seven video frames and
the still at 100 %; `slice/measurements/roundtrip_v01_SHOT_001_review.json`): the controls are
validated on a real silhouette — the 3° rotation fails every metric (p95 3.3–3.5 px; the
placeholder sphere could not validate it), and the shutter-integration control discriminates
wherever the head moves (centre-only differs by 0.014–0.040 and fails the gate on two of five
moving frames); a frame that does not move across the shutter cannot test the sub-frame data and
reads NOT_DISCRIMINATING (threshold raised to 0.005 above the measured static floor). The gate
catches a 0.5-px translation or size error and a 0.5–0.75° rotation. The PROVISIONAL thresholds
are kept. **Open defect of this test:** re-projecting the rest head fails a correct export on
an open jaw (jaw_open 0.87: p95 2.57 px, the extra pixels at the chin), so the test as written
cannot accept a master whose hero laughs. Loosening the thresholds on deformed frames is rejected
because it would hide transform errors of the same size; the re-projected head must carry the
frame's facial deformation (the per-frame deformed default head in the socket's local frame)
before any master with open-mouth frames is accepted — Phase 0.5 burst 2 included.
`iou_min` depends on the silhouette's size (≈ 0.67 px of boundary error at r ≈ 270 px, 2 px in a
close-up); a size-aware form is to be decided on burst 2's framings.
Amendment 2026-09-17 (implemented; the open defect above is closed): the re-projected head is the
**default head as rendered** — the export writes every C_HEAD mesh evaluated at every frame and
sub-frame sample in the socket's local frame (`default_head_deformed.npy`, vertex order of
`default_head_rest.obj`), the round-trip interpolates it across the shutter like the socket, and
C_HAIR must stay rigid on the socket (the export stops otherwise). This file is **QC only** and not
a HEAD_RENDER deliverable: a head technology receives the performance track, never the default
head's deformation (identity and performance stay separate, §D8). The rest head is still
re-projected on every frame and reported, never gated. Measured on v01 at 100 %: frame 1100
(jaw_open 0.87) now passes at the floor (p95 0.25 px, centroid 0.004 px, band 0.016) while the
rest head on the same render reproduces the old failure (2.57 px / 0.57 px); a placeholder head
with a 2-cm jaw passes deformed and fails at rest (slice test). The positive control is reported
per frame, and the acceptance self-check renders the fastest-turning and the widest-jaw frame
besides the first.

### D8. Performance track

`emotion` + `emotion_intensity` is a label track, not a performance. The performance track is a
per-frame **project-owned continuous control-channel vector**:

- named channels with documented ranges and a written semantic definition each (brow
  inner/outer, lid aperture, squint, cheek raise, nose, mouth corners, jaw, lip funnel/purse,
  gaze yaw/pitch, blink, asymmetry per side), plus head pose from §D7; where two channels act
  on the same feature, the vocabulary states how they combine, and every consumer applies that
  rule to the raw values (amendment 2026-09-17: lid closure = max(lid pose closure, blink), a
  blink cancels lid widening — `slice/channel_map.json → combination_rules`);
- a **reference render of every channel at its extremes on the default head**, shipped with the
  master, so "what does 0.7 on this channel look like" has one answer;
- the channel vocabulary is versioned in single-source-of-truth config; `mouth_state` never
  carries a vendor's blendshape or viseme names — that would couple the master to one vendor
  inside the master;
- `emotion`, `emotion_intensity`, `emotion_*` become editorial metadata used for routing and QC
  bucketing, not for driving.

This is what makes invariant 6 true in practice: the master owns the acting, and two children
land the director's beat on the same frame.

### D9. Still render profile

Same scenes, same rig, same default head; shutter angle 0, sample count per TD, depth of field
for the page, print resolution. **Identical pass set to the video profile** — a still profile
that omits a pass is a defect. One still per shot is rendered on the slice.

### D10. Dub-friendly staging

Every shot with `secondary_speech_on_camera: true` carries `dub_staging` ≠ `NONE` (`../../CLAUDE.md`
§4.18, shot manifest). Caught at storyboard review.

### D11. Master package versioning and rebuildability

- The package is immutable and content-addressed; per-shot content hashes; any change bumps
  `master_version` (`../architecture/entities.md`).
- The package carries `master_contract_version` (this ADR), the DCC and plugin versions
  pinned, the OCIO config, the channel vocabulary version, and a **rebuild recipe**.
- Source scenes are archived with the package. A test-rebuild of one shot per master version is
  a delivery criterion — so a pass discovered missing later costs a re-render, not a rebuild.
- The package is the Story Template layer; it contains no personal data and replicates freely.

## Alternatives

- **Face swap on the finished render.** No passes, no seam control, no lighting match, hair
  impossible. Rejected — it is the "beautiful portrait, unproducible" failure at architecture
  level.
- **2D rig / hybrid master.** Rejected by owner (§4.4); the transform and pass contract above
  cannot be produced by a 2D rig.
- **Head-technology-specific passes chosen after the bake-off.** Rejected — it couples the master
  to the Phase 1 winner and silently kills invariant 15. The base set is technology-neutral.
- **No default head; the master is "headless".** Rejected — there is then no seam reference, no
  QC baseline, no negative-control baseline, and hand-contact shots have nothing to be keyed to.
- **Scaling the head to the child.** Rejected — breaks the neck/collar seam and the silhouette
  in every shot; identity lives within the envelope (§D1).

## Evidence

ENGINEERING JUDGMENT throughout, from the animation-pipeline review of 2026-09-07 and standard
VFX practice; no vendor claims. The only measured inputs will come from the slice (§Validation).
Every numeric tolerance in this ADR is `PROVISIONAL` until calibrated.

## Consequences

- Master production cannot start until the slice validates this contract. That is the point.
- `MASTER_COST` gains: default-head renders, `STATIC_PRECOMP`, the still profile, the
  collision proxy and joint export, the channel reference renders, the rebuild archive.
- The Phase 1 bake-off has a real input: any candidate head technology is evaluated on the
  slice's socket, passes and performance track, not on a portrait.
- Hair simulation and hair shadow are explicitly per-child costs owned by the head technology;
  the master's obligation ends at the collision proxy and the separate shadow pass.

## Does not solve

- Hair simulation quality per child, and hair crossing the face — the most likely per-child
  manual work in the pipeline.
- Likeness in profile: carried by the nose/chin/forehead outline that the envelope constrains.
- Hands touching the face: keyed to the default head; a different head shape leaves the hand
  floating or intersecting. Mitigation is shot design (RED/BLACK at storyboard), not this ADR.
- Style match between the head technology's shading and the master's — a bake-off criterion.
- The head technology itself, and the hair-class enumeration values (Phase 1).

## Validation / experiment — the Phase 0.5 reference slice

Three shots (EASY / DIFFICULT / STRESS), ~5 s each, built in the intended 3D toolchain with the
full §D5 pass set, both profiles, default head. Exit criteria, all recorded:

1. every pass in §D5 present in both profiles, with `read_granularity` and measured
   `bytes_per_frame` per bundle;
2. the §D7 round-trip test passes on all three shots;
3. `STATIC_PRECOMP` + default head layer reproduces the full default-head render within the
   stated tolerance;
4. a placeholder head (any technology, even the default head re-imported) composites
   end-to-end through the socket, holdout, shadow and skin-ID passes;
5. one still per shot rendered and assembled into a test page at print resolution;
6. `t_comp`, `S_frame` per bundle and `worker_warmup_minutes` measured and written to the
   bake-off record;
7. a test-rebuild of one shot from archived source succeeds.

Cost: a `PLATFORM_COST` line under the bake-off `experiment_id`, `amortization_basis:
PER_MASTER` (owner decision 2026-09-11 — the slice is the bake-off's input, not part of a
sellable master; amends the earlier `MASTER_COST` wording). Capped by the owner before the slice
starts, from the TD's written estimate. Stop criterion: no
external paid call and no real subject anywhere in the slice.

## Rollback / replacement strategy

The contract is versioned. A change bumps `master_contract_version` and, for any existing
master, `master_version`; because source is archived with a rebuild recipe (§D11), re-export
under a new contract is a re-render, not a rebuild. Head technologies are replaced without
touching this contract — that is the acceptance criterion the contract exists for.
