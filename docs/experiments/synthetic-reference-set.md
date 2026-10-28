# Synthetic reference set — the bake-off's children (protocol §3, precondition P2)

Status: **APPROVED 2026-10-02 by the owner — the route: 3D («Путь 3D»); the tones: the three below, kept as the intended range
for now («пока такие тона и оставим»).** The contractor's task is derived from this document on the owner's go; the cap
follows his estimate of the pilot child. Authority: `bakeoff-protocol.md` §3 (where they differ, the protocol wins and
this document is the defect). Composition: the pre-registration's draft (§3, N_ref = 9).

## What it is for

The bake-off has no real children (CLAUDE.md §5, protocol §3). Every candidate head technology receives a synthetic
child's **upload packet** — the photographs a parent would send — and is judged against that child's **ground truth**,
which no candidate ever sees. The set is a durable project asset: held identical across candidates, used for negative
controls and later for staging runs and visual regression.

## The route: 3D synthetic children (the owner's decision, 2026-10-02)

Each child is a 3D head built by script in Blender, so its ground truth exists in any pose, expression and light — the
identity metric (M1) can be measured against the same child in the same frame of the same shot. The upload packet is a
photoreal render of the same head.

- **For:** honest ground truth in every state the benchmark measures; deterministic and rebuildable; provenance trivially
  stated (no photograph of anyone is an input); negative controls (hair swapped, glasses removed) are one parameter.
- **Against — the risk stated in every result:** the packet is a render, not a phone photo. A candidate trained on real
  photographs may behave differently on it. Mitigation: a photoreal packet look (below), and the risk carried into
  ADR-0003's limits.
- **Home advantage:** the children are built in the same parametric family (MPFB2 / MakeHuman) as the default head, and
  possibly as a 3D-head candidate. Each child's identity therefore carries a sculpted deviation outside that family's
  targets, and we report, per child, the residual of the best MPFB fit — a candidate that only reproduces MPFB faces
  shows it.
- **The alternative:** an image generator — more photographic packets, but no ground truth of the same face from every
  side and in every expression. Not proposed.

## Composition — 9 children (pre-registration §3)

- **Skin tone:** three values crossed with hair — the master's supported range at both ends and the middle (ADR-0002 D4,
  the C4 gate): lightest (0.90, 0.72, 0.62), middle (0.55, 0.38, 0.28), darkest (0.20, 0.11, 0.07) scene-linear albedo —
  the gate's tones, kept by the owner as the intended range for now (2026-10-02; PROVISIONAL until the product range is set).
- **Hair:** short straight, long straight, curly high-volume, crossed with the tones. Hair crossing the forehead in the
  neutral pose: 3 of the 9 (one per tone, different classes).
- **Glasses:** prescription glasses on 2 of the 9 (one at a tone boundary, one in the middle, different classes).
- **Facial features:** face shape, eye spacing and nose form varied by a parameter table, no two children sharing a
  row; every value measured on the delivered mesh, not only declared.
- **Age and presentation:** within the slice master — girls, 7–9.

## Per child, built by the contractor (scripts and files)

1. **The head on the slice's socket.** The child's head shell ends at the default head's `SOCKET_BOUNDARY` ring, vertex
   for vertex (the identity deformation fades to zero toward the ring), so it composites through our pipeline exactly as
   a head technology's output would — with the default head's skin, eyes, teeth, tongue and brows replaced by the child's.
   Inside the envelope of ADR-0002 D1 (or reported where not).
2. **The face rig on our vocabulary.** The 26 channels of `slice/channel_map.json` (v2) drive the child's face as they
   drive the default head (the same expression units, rebuilt on the child's identity), the gaze by the vocabulary's
   degrees, the lid / blink rule. Our channel reference renders of each child show the channels move.
3. **Skin, hair, glasses.** Skin albedo exactly the assigned tone (head and body, Principled; any texture multiplies to a
   mean equal to the tone). Hair as a mesh hanging rigidly on the socket (the slice's contract), built by a function of
   its own (`hair_on_head.py`: a head, the socket and the class parameters → the hair), so a class's hair can be put on
   another head — a candidate head has no hair of its own (owner, 2026-10-24). Glasses as geometry, **seated**: the
   bridge on the nose (gap 0–2 mm), the lenses about 10–14 mm in front of the eyes, the temples outside the head
   (skin + ~2 mm) to the top of the ear (2026-10-24, after the checkpoint's glasses floated 30 mm ahead of the eyes).
4. **The upload packet scenes:** 3–5 per child, phone-like — wide lens (24–28 mm equivalent), 0.4–1.2 m, varied height
   and tilt; daylight from a window, warm indoor light, overhead light, open shade; neutral and smiling; the child in
   their own clothes (not the master's costume), simple home backgrounds; the photoreal look: subsurface skin, fine
   procedural skin detail, the hair's own render. Imperfections are ours to add at render time (noise, slight blur,
   compression), recorded.
5. **The ground-truth scenes:** a turntable (yaw 0, ±30, ±60, ±90°; pitch ±20°) and an expression sheet (the benchmark's
   states: smile, laughter, sadness, fear, open mouth, blink, gaze shift) in each shot's lighting reference, in the
   master's look (the slice's materials). In the shots themselves, the child's head in the socket driven by the shot's
   performance track — the per-frame truth.
6. **Negative-control variants:** hair swapped between two children; glasses removed from a glasses child.
7. **Report and licences:** the parameter table, the sculpted deviation per child, every third-party asset with its
   licence (MPFB2 assets are CC0), a statement that no photograph of a real person was an input, a seed or a reference.

Rendering is ours (the contractor works on one CPU core; we have the GPU): his scripts set the scenes, we render.

## Our acceptance (gates, per child)

| Gate | Passes when |
|---|---|
| provenance | built from the template by his scripts only; the script scan clean; every asset in the licence table; no image file from outside the project |
| rebuild | rebuilt from his scripts within 1e-6 (`slice/accept_delivery.py`) |
| socket | the head's ring equals the default head's within 1e-6; the child composited in a slice shot passes the round-trip (D7) and the seam criterion |
| channels | every channel the default head moves visibly moves the child (`slice/channel_reference.py`) |
| tone | the skin's albedo is the assigned tone (measured on the material and on a flat-lit render) |
| eyes and lids | added 2026-10-25 (five of the nine children's lids failed on the eye while every other gate passed): at rest and at every lid extreme no lid vertex inside the eyeball (contact within 0.05 mm); shut (blink, `lid_aperture` −1) nothing of the eye visible from the front or 35° to either side; shut, the lid lies on the eye (median standoff ≤ 2.8 mm, PROVISIONAL — calibrated on the default head and 26 child builds, `slice/measurements/eye_lid_2026-10-25/`); the close-up sheet seen by us (`slice/measurements/eye_lid_check.py`) |
| mouth | added 2026-10-28 (the lower teeth out through both mouth corners at the SHOT_001 laughter peak and the upper teeth ahead of the lip in the SHOT_002 profile — on the default head of the accepted master shots and on all seven children, while every gate and the full check passed; found on our expression sheet): on any frame of the three shots no part of the teeth or the tongue seen by the shot camera outside the lips; the mouth close-ups (smile, open mouth, laughter, the SHOT_002 profile) seen by us. The tool is ours, given to him before his fix comes back; the lower teeth and the tongue move as a rigid body (owner, 2026-10-28, Q66) |
| hair, glasses | the class declared and visible; the forehead crossing where assigned; glasses present on their children in every shot and seated (above); on any frame of the three shots and at the channel extremes, no glasses triangle crossing the skin, brows, eyes or body, no hair triangle crossing the brows, eyes or body, and the hair's crossings with the head skin only on the faces that cross at rest — its own seating on the scalp; by face set, not by the number of pairs, which moves on the same faces (owner, 2026-10-26; the default head's cheek strand is pressed onto the cheek by design and has its own gate, Q31); the gaps reported (`slice/measurements/accessory_clearance.py`) — except the master's own SHOT_003 hand window, excluded from the metrics of the children with a fringe or glasses (owner, 2026-10-24; `benchmarks/bakeoff/01J7B000000000000000BAKEXP/declared_exclusions.json`); the fingertips under the edge of short hair without a fringe (06, 07; the default head's own 44 pairs) are not a fringe — the window is kept for them (owner, 2026-10-28) |
| features | the **minimum difference** (owner, 2026-10-24, replacing the same day's 12-mm feature sum): every child's face differs from the default head's and from every other child's by **≥ 2.0 mm** — the RMS of the per-vertex displacement over the face, the same topology vertex to vertex, translation removed (`slice/measurements/face_shape_distance.py`); faces stay natural (no extreme target weights to buy the difference) and the owner sees the sheet of faces; the feature table (face width, interocular, nose wing width — the contractor's `face_measure.py` v2) is a description, matched to the plan within 2 mm, not the rule |
| home advantage | the residual of the best MPFB fit reported per child (not a gate until a calibration exists) |
| packet | 3–5 scenes per child render deterministically on our GPU; no metadata in the files; in `open_shade` no sun reaches any vertex of the child — the set shades the whole child, ray-tested against the set's geometry over the sun's disc; each child's top at least ΔE76 10 from every other child's in the same light, 01 the pilot's mustard (owner, 2026-10-27, Q64; `slice/measurements/packet_scene_check.py` per scene, `packet_set_check.py` over the set) |
| controls | the variants differ from their source in the one property and nothing else (content hash per object); the hair swapped between two children of different classes — a class's hair is one function of the head (`hair_on_head.py`), so a swap within a class changes nothing (06 and 07 wear the same cut) |

Every pair is accepted by the same steps, one command each (`slice/measurements/accept_pair.sh <run dir> cpu`, then
`render` and `full` on the GPU): his checksums; every earlier child and every scene he did not re-save must not move
under his changed scripts; the gates above; the newest scenes of every child for the packet row. The expression sheet
(item 5) is ours: `slice/expression_sheet.py` places each shot's lighting reference in the head's frame at the
reference's sampled frame and keys the master's own face at the peak of each state's window; its neutral front view
in SHOT_001's light equals his turntable's first view (2026-10-27: silhouette IoU 1.0, mean difference 1e-5; the smile
against the same view 6·10⁻³ — `slice/measurements/expression_sheet_2026-10-27/`); `slice/expression_sheets.sh`
renders the set.

## Delivery in two steps

1. **One pilot child end to end** — the head on the socket, the rig, one packet scene, the turntable — through every gate,
   and the owner looks at the packet and the truth. The estimate of the rest is made against it.
2. **The other eight and the controls.**

## Records we keep

`reference_set_manifest.json` (version, `reference_set_hash`, per child: the parameter table, tone, hair, glasses,
provenance, file hashes) in the bake-off record; one `AVATAR` per child with `canonical_ref: ref:synthetic/<set>/<child>`
(the dry run's shape); the renders on the archive disk; the pre-registration's §3 filled from it.

## Decided with the contractor (the owner's answers to his Q52 questions, 2026-10-02)

- Curly hair: volume over the envelope — he gives the volume and reports where and by how much it leaves the envelope
  (the envelope is not a gate for hair on the synthetic set).
- The child's eyes are the child's: iris colour is a parameter of `subject_NN.json` (`subject_01`: brown).
- The character file wears the master's dress; the child's own simple clothes appear only in the parent-photo scene.
- 2026-10-23 (owner, after the pilot): the master's skirt visible below the child's own top in the parent-photo scene is kept
  as is — it touches no measurement; the same for all nine.
- 2026-10-26 (owner, Q63, after the show of 01, 02, 03): the expression sheet (item 5) is ours — rendered on our GPU from his
  character files in the three shots' lighting, not part of his work; the turntable stays his. The other six come in
  pairs (04–05, 06–07, 08–09), each stopping for our acceptance; the three new packet lights come with the first pair, the
  negative controls and the final report with the last. The master's palm through a fringe in the SHOT_003 window is
  accepted as is (the exclusion of 2026-10-24) — measured and reported for 04, 05, 09, never fixed in the asset.
- 2026-10-27 (owner, Q64, after the first pair): the four packet lights (window daylight, warm evening indoor, overhead
  panel, open shade) look right — accepted. In `open_shade` no direct sun reaches the child (the sky only; his first cut
  had the sun in front, a hard shadow on the wall behind — fixed). Each of the nine children wears their own top colour,
  none repeated (01 keeps the pilot's mustard).
- 2026-10-28 (owner, Q65, after the second pair): the palm in the SHOT_003 window passes under the edge of 06's and 07's
  short hair (no fringe; 59 and 62 pairs, the default head 44; on camera the fingertips go under the hair, nothing seen
  through it) — **kept as is, the window not excluded for them**; it stays measured on 01, 06, 07, 08. **The teeth through
  the skin** (the mouth row above) **are fixed by the contractor in the common head build**, once for all — 01–07 rebuilt
  by script, 08–09 built with the fix; his diagnosis and estimate first, within the 40-h cap. **The default head of the
  master's shots keeps the defect for now — recorded, not fixed** (SHOT_001 v02 laughter, SHOT_002 v03 profile; the
  teeth cross skin faces they do not cross at rest on SHOT_001 1041–1120, SHOT_002 1136–1240, SHOT_003 up to 12 faces —
  `slice/measurements/burst3_pair_06_07_2026-10-28/teeth_probe/`).
- 2026-10-28 (owner, Q66, after his diagnosis — confirmed by our measurement: the upper teeth fixed in the socket on
  every frame, the lower teeth and tongue one translation linear in `jaw_open`, no rotation, 8.6 mm at 0.97; the arch's
  half-width 33.8 mm, wider than the mouth in the laughter): **fix as he proposes — the arch narrowed and the lower teeth
  set back until nothing crosses at rest, ≥ 1.5 mm to the corners — with one change: the lower teeth and the tongue move
  as a rigid body** (a rotation about the jaw hinge plus a translation, fitted to the chin and lower lip's motion, for
  `jaw_open` and `jaw_lateral`; their shape within 0.2 mm of a rigid motion on every frame), never vertex by vertex;
  zero new crossings is his target, the mouth row the gate. **The pilot's `window_day` scene changes** with the teeth —
  accepted, its new file the pilot's reference. **His quick `check_asset.sh` on SHOT_001 of all seven and SHOT_002 of 01.**
  **Our check after the fix:** each of the 21 shots compared with the accepted one — only the teeth and the tongue may
  change; the mouth rule on every frame of the three shots; the full `check_asset.sh` at 100 % on 01's SHOT_001 and
  SHOT_002 only — the earlier full checks stand for everything but the mouth (instead of ~20 GPU hours on all 21).

## The pilot, accepted 2026-10-18 (`slice/measurements/subject_01_acceptance_2026-10-18.json`)

`subject_01` (the darkest tone, curly high-volume hair) passed every gate above except one that is ours: the D7 round-trip's
nine-instant shutter integration cannot follow a thousand thin curls on the fastest frame (p95 1.35 px of 0.5; the same
export at 33 instants 0.25 px). Two consequences for the set and the bake-off: **the default head's envelope is too small
for voluminous hair** (this child leaves it by 35–60 mm, by the owner's decision) and **the round-trip needs a rule for
thin hair** before candidates' heads with their own hair are measured — an ADR-0002 D7 amendment for the owner.

- 2026-10-24 (owner, after the checkpoint of subject_02 and subject_03): the minimum difference between faces — first
  as a 12-mm sum over three features, then the same day, once the nose was found mis-measured (the contractor's
  face_measure v1 and our subject_measure both measured the cheeks beside the nose) and the sum could be met only with
  extreme faces, **as the whole face: ≥ 2.0 mm RMS** (the features gate); the nose wing width (v2) is a description only;
  the plan is the order and is re-planned, not re-declared to what came out; the hair moved into its own function (`hair_on_head.py`, 2–3 h within the cap); **long
  straight hair ends at the collar** — rigid hair on the socket cannot be longer through the head turns (longer hair would
  need simulated hair, a later product question); the cap for the eight: 40 h.

- 2026-10-24 (owner, Q56 → Q57): **the plan of faces 03–09 accepted** — targets only, weights ≤ 0.4, natural faces;
  every pair of the ten heads ≥ 2.0 mm by `face_shape_distance.py` on the trial builds (worst child pair 2.391 mm),
  the contractor's linear model within 0.022 mm of it; **each of 03–09 still carries its own sculpted deviation outside
  the targets** (2–3 bumps of 1.5–3 mm, as on 01 and 02 — the home-advantage guard above), checked again on the built heads.

## Decided and open

- Decided 2026-10-02 (owner): the route — 3D; the tones — the three above.
- The contractor's estimate (2026-10-02): the pilot ~21–29 h, with two early checkpoints (after the head with its channels; after the first parent-photo frame); the other eight ~36–52 h, final after the pilot. Open: the owner's cap on the pilot.
