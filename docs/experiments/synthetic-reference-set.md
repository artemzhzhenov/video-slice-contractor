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
| hair, glasses | the class declared and visible; the forehead crossing where assigned; glasses present on their children in every shot and seated (above); on any frame of the three shots and at the channel extremes, no glasses triangle crossing the skin, brows, eyes or body, no hair triangle crossing the brows, eyes or body, and the hair's crossings with the head skin only on the faces that cross at rest — its own seating on the scalp; by face set, not by the number of pairs, which moves on the same faces (owner, 2026-10-26; the default head's cheek strand is pressed onto the cheek by design and has its own gate, Q31); the gaps reported (`slice/measurements/accessory_clearance.py`) — except the master's own SHOT_003 hand window, excluded from the metrics of the children with a fringe or glasses (owner, 2026-10-24; `benchmarks/bakeoff/01J7B000000000000000BAKEXP/declared_exclusions.json`) |
| features | the **minimum difference** (owner, 2026-10-24, replacing the same day's 12-mm feature sum): every child's face differs from the default head's and from every other child's by **≥ 2.0 mm** — the RMS of the per-vertex displacement over the face, the same topology vertex to vertex, translation removed (`slice/measurements/face_shape_distance.py`); faces stay natural (no extreme target weights to buy the difference) and the owner sees the sheet of faces; the feature table (face width, interocular, nose wing width — the contractor's `face_measure.py` v2) is a description, matched to the plan within 2 mm, not the rule |
| home advantage | the residual of the best MPFB fit reported per child (not a gate until a calibration exists) |
| packet | 3–5 scenes per child render deterministically on our GPU; no metadata in the files |
| controls | the variants differ from their source in the one property and nothing else (content hash per object) |

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
