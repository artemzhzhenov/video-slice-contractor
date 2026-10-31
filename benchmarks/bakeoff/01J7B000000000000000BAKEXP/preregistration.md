# Pre-registration — Head Architecture Bake-Off `01J7B000000000000000BAKEXP`

**Status: FORM, PARTIALLY FILLED — `frozen: false`.** Created 2026-09-15 so that the first
candidate is registered against a form that already exists (protocol §1 P6, PROJECT_STATE next
action 3). 2026-09-16: the fields a TD of record can fill without a candidate or a reference
set are drafted by the agent in the TD role and marked `(agent, drafted in the TD role,
2026-09-16 — pending TD affirmation)`: they become the form's values only when the owner-named TD
of record affirms each one explicitly before the freeze; none is adopted by silence. Numbers in
them are ENGINEERING JUDGMENT with their rationale (no labelled set exists yet, so none is
PROVISIONAL in the sense of `docs/process/definitions.md`) and are validated at Stage 3/5 like
every threshold. Separation margins (§6) stay `TO FILL` until the first candidate is
registered — the form's own rule.
**2026-10-31:** the TD of record — the owner, by signature (§12) — affirmed the drafted fields one by one on the table `td_affirmation_2026-10-31.md` in this record (prepared by the slice contractor, an AI agent; sha256 `8622ff8019e5a060858df81ef0b5a9a606a8f601ce1ab51b5497d6be6ff08a24`): every marker below names its row; where a row adds to or edits a field, the row's text (quoted, translated from the table's Russian, which is the original) governs; one draft is struck. The §2 rows of candidate B1 filled by the agent in the TD role carried no marker and are not affirmed by the table (its §6) — marked below, they wait for the TD's affirmation like any draft.
Every remaining `TO FILL` waits for the named person. Nothing in this file may
be written after a candidate output exists: at the moment the first Stage 0 artifact is
produced, this file is frozen — its sha256 is written into `decision.md`, `frozen` becomes
`true`, and any later change is an appendix in §13 with a date and a reason, never an edit of
a filled field. A criterion that appears after the numbers are visible is a defect
(`docs/process/definitions.md`, meaningful degradation).

Authority: `docs/experiments/bakeoff-protocol.md` (the protocol) — where this form and the
protocol differ, the protocol wins and this form is the defect. Field homes: protocol §12.

Who fills what: **owner** — cost, cap, mix, spend-control decision, sign-off; **TD of record**
— candidates' technical declarations, metric criteria, pilot plan, acceptance checklist,
cleanup ceiling, reviewer floor; **agent** — pre-filled facts from the repository, marked as such.

---

## 0. The question and the working hypothesis

- **Question (protocol §0, verbatim):** which head representation produces the same
  recognizable synthetic child across the slice's three shots, in both render profiles, at the
  lowest total marginal cost per acceptable cartoon — cleanup minutes included — without
  receiving the source photos more than once?
- **Working hypothesis under test** (`docs/architecture/avatar-pipeline.md`): a parameterized
  representation where AI runs mainly **once per child** beats once-per-shot and once-per-frame
  on total marginal cost at equal acceptability. Each candidate's own hypothesis: §2.
- **What would refute it** (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 1 of `td_affirmation_2026-10-31.md`), with: «lower on **each** X2 column read separately — machine cost (Mac hours, repair included, and money), agent repair (minutes, operations), human minutes (signing, onboarding); lower on some and not on others is a mixed result, recorded as a refutation with every column; nothing weighted or summed») — stated over the §2 declaration "where AI runs", not
  over families: the hypothesis holds only if a candidate declared *once per child* reaches
  PASSED under §10 and, on the worst subject, is lower on **both** X2 columns (machine money and
  human minutes, each read separately, never summed) than every passing candidate declared once
  per shot or once per frame — and at least one such comparator of a different declared
  frequency must have PASSED, otherwise the outcome is `NOT_TESTED`, never "holds". Any other
  outcome refutes it: no once-per-child candidate passes while another does; or the best
  once-per-child candidate is lower on one column and not on the other (a mixed result —
  recorded as a refutation with both columns shown, never resolved by weighting). The
  refutation is written in `decision.md`; the decision still ranks whatever
  passed, and ADR-0003 states that the working hypothesis of `avatar-pipeline.md` did not hold
  on this record.

## 1. Preconditions (protocol §1) — state at the time of freezing

| # | Precondition | State | Evidence |
|---|---|---|---|
| P1 | Slice delivered, eight ADR-0002 exit criteria and the brief's three passed, `t_comp` / `S_frame` / `worker_warmup_minutes` in the record | `MET` 2026-09-29 — the three shots delivered and accepted (burst 2 closed 2026-09-29); the exit review: all eleven met, the render tolerance of criterion 7 and the gates' thresholds PROVISIONAL (SHOT_002's rows re-run at v03 2026-10-02; the render tolerance passed its first independent test there) — `docs/experiments/phase-0-5-exit-review.md` | `slice/package_manifest.json` in this record (`package_hash` pinned by `master.json`; `measurements` holds `t_comp`, `S_frame`, `worker_warmup_minutes`) |
| P2 | Synthetic reference set exists, hashed, versioned | `NOT MET` | `reference_set_manifest.json`, `TO FILL` |
| P3 | Every candidate is a `MODEL_REGISTRY_ENTRY` in `TESTING`, `receives_child_data: false` | `PARTIAL` 2026-10-17 — one registered: `registry/keentools_facebuilder.json` (TESTING, no child data). The owner's fork of 2026-10-17: FaceBuilder first; LAM, SOAP, Avatar SDK and Reallusion Headshot picked but FROZEN (registered on the return to the fork). The protocol's minimum (three across two families) is NOT met by one — a FaceBuilder-only run is a feasibility pilot, not the bake-off | `registry/*.json`; the survey `docs/experiments/head-candidates-survey-2026-10-17.md` |
| P4 | Result-row schema exists | `MET` 2026-09-14 | `schemas/bakeoff_result.json`, fixtures |
| P5 | `BAKEOFF_COST_CAP` set by the owner | `MET` 2026-10-29 — **220 Mac hours** (owner, «три повтора, 220 часов»; §9) | §9, PROJECT_STATE Open Decisions |
| P6 | This pre-registration committed before any output | `FORM EXISTS, PARTIALLY FILLED` — TD fields 2026-09-16; owner fields, candidates, reference set and separation margins open | this file |
| P7 | The three slice performance tracks cover every benchmark state | `MET` 2026-09-29 — `slice/state_map.json` FINAL, all fifteen states measured `STATES_OK` on the accepted shots (SHOT_002 re-run at v03 2026-10-02: 17/0) | `state_map.json` |

Rule: no PAID stage (§5) starts while any row reads `NOT MET`.

## 2. Candidates (protocol §2)

At least three, across at least two of the four families (A 2D rig, B 3D head, C neural
avatar, D hybrid). One block per candidate; copy the block. Candidate 0 is pre-filled.

### Candidate 0 — the default head (baseline, not a candidate)

- `candidate_id`: `default_head` · family: B (the slice's own 3D head) · registry: not required
- Role: known-good floor for M3, M4, M7, M8 and the substrate of every negative control;
  run through every stage.
- Where AI runs: nowhere. Driven by: the performance track directly.

### Candidate B1 — KeenTools FaceBuilder → our Blender rig (registered 2026-10-17)

Every row below filled by `TD` was written by the agent in the TD role (2026-10-17 → 2026-10-30) — pending the TD of record's affirmation, row by row, before the freeze (found by the contractor's table, §6, 2026-10-31).

| Field | Value | Filled by |
|---|---|---|
| `candidate_id`, `candidate_version` | `keentools-facebuilder-blender`, `2026.3.1` — the add-on and the Core library (built 2026-08-27), sha256-pinned in `scripts/keentools/keentools.lock.json`; installed and activated 2026-10-23 (Freelancer Monthly, node-locked to the M4), smoke check passed (`scripts/keentools/smoke_2026-10-23.json`) | TD (agent) |
| Family (A / B / C / D) | B — a 3D head: photo-fitted mesh with 51 ARKit-compatible blendshapes, rendered by our Cycles pipeline | TD |
| Registry entry | `registry/keentools_facebuilder.json`, `TESTING`, `HEAD_RENDER` (performs its own photo → mesh derivation) | TD |
| Where AI runs | once per child (the fit); per frame nothing but our render | TD |
| Driven by | **Owner's decision 2026-10-23 (after Stage 0): variant B1-M** — FaceBuilder's fitted identity carried on the master's head topology (`bakeoff/facebuilder/build_shot.py`, the default `--expressions master`), driven by the master's own channel keys from FACE_CTRL; the gaze point → the master's eyes. Registered originally: our 26 channels → the 51 ARKit shapes plus custom keys (`arkit_map.json`) — failed on expression at Stage 0, kept as the record. The adapter's cost and determinism are the candidate's | TD + owner |
| `pass_dependency` | the HEAD_RENDER bundle (camera, socket, lighting reference, performance track, holdout); no pass outside the frozen set | TD |
| Exact version, licence, `self_hosted_weights` | add-on and Core 2026.3.1; Freelancer Monthly, $19.99/mo, held by the owner since 2026-10-23; weights closed in the Core library (`self_hosted_weights: false`, runs locally). EULA 2026-08-20: commercial use permitted; Freelancer only for a private individual's own use (a legal entity needs Studio); the contractor may not use this licence; §13.2 on minors → legal Q15 (production only, not the bake-off) | TD |
| Privacy block | sentinels (synthetic inputs only during the bake-off) | TD |
| `vendor_portability` (O7) | licensed desktop tool; the fitted mesh and shapes are ours to keep (exported geometry) — portability of the FIT, not of the tool | TD |
| Candidate hypothesis | it should win on contract fit (native Blender passes, shadow, holdout, 4K) and on cost; it loses if the fixed topology prior cannot carry a child's likeness (M1/M2 on the synthetic set) or if 51 shapes plus custom keys cannot reach the slice's extremes (laughter, fear) — the second clause met at Stage 0 for the ARKit drive. **For B1-M (2026-10-23):** it loses if the likeness does not survive the wrap onto the master's topology (M1/M2), or if the master's channel keys on a child's identity break the lids or the mouth on faces unlike the default head (the channel reference and the extremes, per subject) | TD |
| Exclusion risk on paper | none of the four: the mesh is the derivative (BOUNDARY), the layer is contract-native (CONTRACT), driven through the adapter (PERFORMANCE), the head fitted inside the envelope (SCALE — checked at Stage 0) | TD |
| Expected cost class per stage | Stage 0: the subscription month (~$20, owner) + TD hours on the M4; Stages 1–2: TD hours per child (the fit is interactive) — ESTIMATE, measured on the pilot child. **2026-10-29:** the fit scripts headless (0 human minutes on Stage 0's packet); the stages are Mac hours — `stage_cost_estimate.json` (ESTIMATE) | TD + owner |

**Stage 0 — 2026-10-23 (owner's «поехали»; record `stage0/keentools-facebuilder-blender/`): `contract_fit: PASS`.**
The default head re-imported headless (4 of 5 views auto-pinned, 1.9 s, no human touch, two fits bitwise identical),
placed by one constant similarity (`bakeoff/facebuilder/placement.json`, calibrated on the default head), carried on the
master's head topology with the ring vertex-identical; every slice gate at 100 % and the order composite onto the
master's own package plates PASS; head render per order frame 34.5 s on the M4. **Deviation, recorded after the outputs
existed:** the registered "Driven by" (our channels → FaceBuilder's 51 ARKit shapes) fails on expression — the lids do not
close over the master's larger stylized eye (≤ 8.8 mm of travel where 10.4 mm is needed), the open jaw tears the lips
(FaceBuilder's mouth is closed at rest), the smile creases. Variant **B1-M** carries FaceBuilder's identity on the
master's own channel keys and is clean; the gates ran on it. **The owner chose B1-M for Stage 1 on 2026-10-23.**

**Stage 1 tooling, declared 2026-10-24 before any Stage 1 output (agent, TD role; the owner may overrule):**
- *The packet a candidate receives:* each parent-photo scene rendered on our GPU as the contractor set it (128 spp,
  denoised), then a Gaussian blur of 0.6 px, Gaussian noise of 1.2 % of the display range (seeded per photo), JPEG
  quality 88, every metadata attribute erased (`bakeoff/packet/render_packet.py`); the camera's truth stays in our
  manifest. The same packet goes to every candidate.
- *Onboarding (Stage 1) for B1:* `bakeoff/facebuilder/onboard.py` — two fits per subject, the focal left to the candidate
  (no EXIF), the record: views pinned, machine minutes, human touch 0, external crossings 0, determinism of the two runs.
- *The order's attributes are GIVEN, not derived by the candidate:* skin tone, iris and brow colour, hair class and
  colour, glasses — from each subject's declared parameters, the same for every candidate, as a parent's confirmed
  choice would be. The bake-off measures the head technology's face and performance; how attributes are read from a
  photo is a separate question for Phase 2. The hair is the class's hair from the contractor's `hair_on_head.py`, never
  the subject's own (that is the truth).
- *Before Stage 1 runs on the set:* `BAKEOFF_COST_CAP` must be set by the owner (protocol §9); Stage 1 is a PAID stage by
  definition (render capacity). Until then the tooling is exercised on the pilot only and nothing is recorded as a result.

**Frozen at the owner's fork of 2026-10-17** (picked, not registered; registered on the return): C1 LAM (Gaussians, Apache-2.0
code, CUDA), B2 SOAP (FLAME mesh, EMOCA → SMIRK swap, CUDA), B5 Avatar SDK, B4 Reallusion Headshot (Windows). Their survey
rows: `docs/experiments/head-candidates-survey-2026-10-17.md`.

### Candidate `TO FILL` (copy per candidate)

| Field | Value | Filled by |
|---|---|---|
| `candidate_id`, `candidate_version` | `TO FILL` | TD |
| Family (A / B / C / D) | `TO FILL` | TD |
| Registry entry (`registry/<id>.json`, status `TESTING`, capabilities) | `TO FILL` | TD |
| Where AI runs: once per child / once per shot / once per frame | `TO FILL` | TD |
| Driven by: the performance track directly / through a project-owned adapter (adapter = part of the candidate; its cost and determinism are the candidate's) | `TO FILL` | TD |
| `pass_dependency` — which of the 14 base passes it consumes; any pass outside the frozen set is a recorded request, not granted | `TO FILL` | TD |
| Exact version, weights hash or API version, license, `self_hosted_weights` | `TO FILL` | TD |
| Privacy block (sentinels allowed during the bake-off; block `QUALIFIED` afterwards, G8) | `TO FILL` | TD |
| `vendor_portability` (O7): self-hosted weights / API-only / licensed export | `TO FILL` | TD |
| Candidate hypothesis: why it should win, and what result would show it lost | `TO FILL` | TD |
| Exclusion risk on paper (`EXCLUDED_BY_BOUNDARY` / `_CONTRACT` / `_PERFORMANCE` / `_SCALE`) and why it is not excluded | `TO FILL` | TD |
| Expected cost class per stage (ESTIMATE with source) | `TO FILL` | TD + owner |

## 3. The synthetic reference set (protocol §3)

- `N_ref` = **9** (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 2 of `td_affirmation_2026-10-31.md`)) — the design minimum from the table below: 3 tone values (both
  ends and the middle of the master's range) × the 3 named hair classes (short straight, long
  straight, curly high-volume), fully crossed; "hair crossing the forehead in neutral" is a
  property, not a class — assigned to 3 of the 9 (one per tone, different classes);
  `glasses: PRESCRIPTION` on 2 of the 9 (one at a tone boundary, one in the middle, different
  classes), so a glasses subject is present in every tier through every shot; face shape, eye
  spacing and nose form varied per subject by a parameter table in the manifest, no two subjects
  sharing a row. The hair-class enumeration of ADR-0002 §D3 is an *output* of this bake-off; the
  three classes here are the protocol's §3 coverage, not the enumeration. The wall-clock of §5 is
  planned against 9; the subjects themselves are `TO FILL` below once the set exists.
- `reference_set_version` = `TO FILL`; `reference_set_hash` = `TO FILL` (whole set) — from
  `reference_set_manifest.json`.
- No subject is derived from any real person's photograph. Provenance per subject is in the
  manifest; the statement is signed in §12.

| Dimension | Required coverage | Subjects covering it | Filled by |
|---|---|---|---|
| Skin tone | both ends and the middle of the master's tone range (≥ 3 values, one at each boundary) | darkest (albedo 0.20 / 0.11 / 0.07) — 01, 02, 03; middle (0.55 / 0.38 / 0.28) — 04, 05, 06; lightest (0.90 / 0.72 / 0.62) — 07, 08, 09: both ends and the middle of the master's range (gate C4's tones, PROVISIONAL until the product range) | TD, 2026-10-31 (`td_affirmation_2026-10-31.md` §2) |
| Hair | short straight; long straight; curly high-volume; hair crossing the forehead in neutral | short straight — 02, 06, 07; long straight — 03, 05, 08; curly high-volume — 01, 04, 09 (one class per tone, fully crossed); across the forehead in neutral — 02, 05, 09 (one per tone, different classes) | TD, 2026-10-31 (`td_affirmation_2026-10-31.md` §2) |
| Glasses | ≥ 1 subject `glasses: PRESCRIPTION`, present in every tier | `PRESCRIPTION` — 03 (boundary, darkest, long straight) and 04 (middle, curly), on all three shots; the `hand_over_face` window is excluded for both (declared), so STRESS covers glasses only through `fast_movement` after 1337 — recorded | TD, 2026-10-31 (`td_affirmation_2026-10-31.md` §2) |
| Facial features | stated variation in face shape, eye spacing, nose form — per subject | each subject its own targets and bumps (`subjects_plan.json`); pairwise RMS over FACE ≥ 2.0 mm on 45 of 45 pairs (the nearest 2.011 mm, default–02); width, eye spacing, nose and brow–chin height per head in `td_affirmation_2026-10-31.md` §2 (a description, not the rule) | TD, 2026-10-31 |
| Age and body presentation | within the slice master's `age_range` and `body_presentation` | girls 7–9; body, dress and rig of all nine bit-identical to v04.1 — within `master.json` (`age_range` 7-9, `body_presentation` girl; the file was missing from the contractor's copy, not from the record) | TD, 2026-10-31 (`td_affirmation_2026-10-31.md` §2) |

## 4. Benchmark matrix (protocol §4)

- States → tiers → shots → frames: `state_map.json` in this record, copied from
  `slice/state_map.json` at freeze. Pre-filled today (PROVISIONAL, agent):
  EASY — front_neutral, smile, gaze_shift, blink (SHOT_001); MEDIUM — three_quarter, laughter,
  fear, sadness, head_turn, open_mouth; DIFFICULT — profile, strong_light,
  profile_strong_emotion (SHOT_002); STRESS — hand_over_face, fast_movement (SHOT_003).
  **Declared exclusion (owner, 2026-10-24, before any candidate output on these subjects):** SHOT_003 frames 1303–1337 —
  the whole `hand_over_face` window and the first five frames of `fast_movement` — are excluded from the metrics of
  every subject with a fringe or glasses (in set v1: 02, 03, 04, 05, 09): the master's palm passes through their rigid
  hair and glasses. `hand_over_face` is measured on subjects 01, 06, 07, 08. Machine-readable:
  `declared_exclusions.json`.
  MEDIUM-window rule (no occlusion, head angular velocity below the shot's declared threshold):
  threshold **T = 140 °/s** — `slice/state_map.json` → `head_angular_velocity_threshold_deg_s`, FINAL (owner, Q46, 2026-09-27): MEDIUM windows ≤ 0.8·T = 112 °/s, `fast_movement` ≥ 1.5·T = 210 °/s (TD, 2026-10-31, `td_affirmation_2026-10-31.md` §2).
- Render profiles: video (3840×2160, 24 fps) and still (per shot: 1050 / 1215 / 1290).
- `MIX_PROVISIONAL` — the declared shot-difficulty mix of a full master, for X2:

| Tier | `frames(tier)` of ~4,300 head-render frames | Basis |
|---|---|---|
| EASY | `TO FILL` | owner + TD, ESTIMATE; replaced by the real mix at Phase 8 |
| MEDIUM | `TO FILL` | |
| DIFFICULT | `TO FILL` | |
| STRESS | `TO FILL` | |
| Comic panels (stills) | `TO FILL` (40–60 per comic spec, ESTIMATE) | |

## 5. Pilot plan and repeat counts (protocol §5 Stage 3)

- Pilot subject: **subject_09** (agent, in the TD role, 2026-10-30 — TD-affirmed 2026-10-31 (row 3 of `td_affirmation_2026-10-31.md`), with: «the pilot starts only after subject_09 v02 is accepted (Q74); if it is rejected the pilot waits for the accepted version, and `reference_set_version` includes the accepted 09»: the one child of the set
  with curly high-volume hair at a tone boundary (lightest), hair crossing the forehead and no glasses — `subjects.json`; its
  v02 is in rebuild (Q70), the pilot waits for its acceptance) — one named subject from §3, chosen by this rule (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 4 of `td_affirmation_2026-10-31.md`), with: «recorded: subject_09 has a fringe, so the `hand_over_face` window (SHOT_003 1303–1337) is excluded for it by the declared exclusion — M6 gets no variance from the pilot (row 6)»): the
  subject hardest on paper — curly high-volume hair at a tone boundary, forehead-crossing
  property, no glasses — because X2 is decided by the worst subject and the pilot's variance
  must not come from an easy one.
- `n_pilot` = **3** (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 5 of `td_affirmation_2026-10-31.md`)), ENGINEERING JUDGMENT — repeats per candidate × 3 shots, video
  profile: the smallest count with a defined sample standard deviation (n − 1 = 2); a larger
  pilot would be paid before the variance that justifies it is known, and the two-degree-of-
  freedom estimate is compensated by the confidence bound in the rule below. Hash-identical
  repeats (M10) give `s = 0` and the rule's floor of 2 — never fewer (CLAUDE.md §7.11).
- Rule that turns the pilot's observed variance into `N_rep` per metric — declared here, applied
  after Stage 3, written to the record before Stage 4 (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 6 of `td_affirmation_2026-10-31.md`), with: «added: a metric with no values on the pilot subject (M6 on subject_09 — a declared exclusion; M9 — human only) has its `N_rep` written `UNKNOWN` with the reason, R is computed over the metrics that have values, and that metric is read over the R runs of Stage 4 — recorded as a known gap»):
  per metric used for ranking, `s` = the sample standard deviation of the metric over the pilot
  repeats, computed per shot and per candidate, pooled over the 3 shots and over the candidates
  by the **maximum** (the noisiest shot and candidate are where separation is decided), then
  replaced by its 80 % upper confidence bound `s_u = s · sqrt((n_pilot − 1) / χ²_{0.20,
  n_pilot − 1})` (factor 2.12 at `n_pilot = 3`); `m` = that metric's separation margin from §6;
  `N_rep(metric) = max(2, ceil(2 · (3 · s_u / m)²))` — the factor 2 because §6 compares two
  means and the standard error of their difference is `s · sqrt(2 / N)`, so that the margin is at
  least three standard errors of the difference wide. `N_rep` is written **per metric** to
  `n_rep.json` with every `s`, `s_u` and `m` it came from (protocol §4). A Stage 4 run serves
  every metric, so the stage repeats every cell `R = max N_rep over the metrics used for
  ranking` times and each metric is evaluated on all `R` repeats. The still profile is not
  piloted (the pilot is video only, protocol §5 Stage 3); it inherits `R`, and that inheritance
  is recorded in `n_rep.json` as a known gap. Cap check before Stage 4 (protocol §5):
  `sum(cost_records[experiment_id]) + Σ over candidate 0 and every candidate of
  (N_ref × 3 shots × 2 profiles × R × estimated_cost(one run, that candidate)) + the PAID control
  runs of §6 > BAKEOFF_COST_CAP` stops the bake-off with `BAKEOFF_COST_CAP_EXCEEDED` and the
  owner decides — `R` is never reduced and no metric is dropped from ranking to fit the budget.
- **Three repeats (owner, 2026-10-29: «три повтора, 220 часов»):** `R = max(3, max N_rep)` — the owner's floor of three
  over the rule's floor of two; a pilot that asks for more is still obeyed, and the cap check before Stage 4 then decides
  whether it fits.
- **Candidate 0 rendered once per cell, not per subject** (agent, in the TD role, 2026-10-29, before any Stage 1 output;
  the owner may overrule): the default head carries the master's tone and no subject's identity, so its render is the
  same for every subject — nine renders of it would be nine noise repeats counted as subjects. It is rendered once per
  shot × profile × repeat (3 × 2 × R) and composited per subject wherever a metric pairs it with one; its known-good
  side (M3, M4, M6–M8) stays "candidate 0 over the R repeats". With it, R = 3 is 161–220 Mac hours against the protocol
  count's 248–315 (`stage_cost_estimate.json`; recomputed 2026-10-29 from the order render measured on the package's 18
  frames: 158–237 against 242–343 without (b), 74–145 with it).
- **The order render measured from Stage 3 is the owner's production configuration** (2026-10-29, «идем по пути Б»):
  the head layer in its screen box (completed outside it: colour 0, vectors 0, the empty depth), the shadow layer at half
  resolution, its multiply over the master's L_BODY at the same half resolution and samples, its pixels that see the back
  hidden under the head filled, returned to 4K bilinearly — the video profile; the stills at full resolution
  (`slice/order_render.py`, ADR-0002 amendment 2026-10-29). The master's half-resolution L_BODY is rendered once for the
  three shots (7.3–11.0 s per frame measured, ≈ 0.7–1.1 h).
- Stage order is fixed; Stage 4 before `N_rep` is written is a defect.

## 6. Automated metrics and separation criteria (protocol §6)

One row per metric. Negative controls are the protocol's (pre-filled). The separation
criterion — margin, repeat count, statistic — is `TO FILL` per metric, before the run. A metric
whose known-good and known-bad distributions overlap is `NOT_VALIDATED`: reported, not used for
ranking. `Used for ranking` is declared here, not decided after.

| ID | Metric | Input | Negative control (synthetic subjects only) | Separation criterion (margin, N, statistic) | Used for ranking | Filled by |
|---|---|---|---|---|---|---|
| M1 | `identity_likeness` per state | subject sheet, same state and lighting; two estimators side by side — face-embedding distance (`UNVALIDATED` on stylized faces until it passes this row's control) and landmark-geometry deviation on the project rig | identity swap: A's output vs B's ground truth, every unordered pair of the `N_ref` subjects once (36 at `N_ref` = 9); scoring only, FREE | `m` = 1.0 mm (half the set's minimum difference between two children, 2.0 mm); N = R of `n_rep.json` (≥ 3); the statistic below (agent, drafted in the TD role, 2026-10-30, before any candidate output — TD-affirmed 2026-10-31 (row 7 of `td_affirmation_2026-10-31.md`); reasons and the dry reading: `bakeoff/metrics/README.md`) | landmark estimator: yes, if VALIDATED at Stage 5; embedding estimator: no — reported only until it passes this control on stylized faces (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 8 of `td_affirmation_2026-10-31.md`), with: «worded as built: the geometric estimator (RMS of the FACE vertices' displacement, frame-matched) — yes, if VALIDATED; the embedding estimator — no, reported only until it passes a control on stylized faces») | TD |
| M2 | `identity_stability_over_performance` | M1 per state relative to front neutral | as M1 | `m` = 1.0 mm (as M1); N = R; the statistic below (agent, drafted in the TD role, 2026-10-30, before any candidate output — TD-affirmed 2026-10-31 (row 9 of `td_affirmation_2026-10-31.md`); reasons and the dry reading: `bakeoff/metrics/README.md`) | yes, if VALIDATED; the one metric burst-2 acting quality feeds — the record says which state moved it (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 10 of `td_affirmation_2026-10-31.md`)) | TD |
| M3 | `temporal_stability` | frame-to-frame change inside the head holdout | injected flicker on the default-head composite, two levels (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 11 of `td_affirmation_2026-10-31.md`), with: «gross — ±3 % luma on alternate frames inside `HEAD_HOLDOUT`; near-boundary — ±1 %; the 1-px edge jitter is M4's control, not M3's (M3 cannot see it — the dry run of 2026-10-30)»), ENGINEERING JUDGMENT: gross — ±3 % scene-linear luma on alternate frames inside `HEAD_HOLDOUT`; near-boundary — ±1 % luma and, separately, a 1-px alternating edge jitter; a composite-domain operation, FREE; the metric's value on both levels is recorded | `m` = 0.04 (what the near-boundary ±1 % flicker reads: 4·0.01/(1 ± 0.01)); N = R; the statistic below (agent, drafted in the TD role, 2026-10-30, before any candidate output — TD-affirmed 2026-10-31 (row 12 of `td_affirmation_2026-10-31.md`), with: «recorded: the near-boundary ±1 % is not distinguishable from fast motion (known-good 0.015, up to 0.048 in fast motion; gross 0.120)»; reasons and the dry reading: `bakeoff/metrics/README.md`) | yes, if VALIDATED | TD |
| M4 | `seam` | luma/chroma discontinuity and edge alignment along the NECK_PROXY curve vs the default-head composite | displacement magnitudes borrowed from the D7 round-trip's own controls (repository `slice/conventions.json` → roundtrip.negative_control at the freeze commit — the record's own `slice/` directory carries the frozen copy; measured on the placeholder only, `smoke_test_only`, to be recalibrated on the real head) (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 13 of `td_affirmation_2026-10-31.md`), with: «the magnitudes affirmed, the remark replaced: recalibrated on the default head v04.1 on 2026-10-30 (dry run) — shift 5 → 1.92 px, scale +5 → 4.90 px; 1 px → 0.39 / 0.97 px»): `HEAD_SCALED` — the head's effective silhouette radius grown by 5 px at the run's resolution about the silhouette centroid, focal scale recomputed per frame as `1 + 5 / r_eff` (gross) and by 1 px (near-boundary); `SEAM_SHIFTED` — the head displaced 5 px along the camera x axis at the run's resolution (gross) and 1 px (near-boundary). Fixed in pixels at the run's resolution, as D7 does; both are composite-domain operations on the default-head layer (scale and shift in the comp), FREE; the metric's value on both levels is recorded | the value is the head edge's mean displacement along the seam against the default head's (px at the run's resolution; the luma in the zone moves with the body's tone and is recorded beside it); `m` = 1.0 px; N = R; the statistic below (agent, drafted in the TD role, 2026-10-30, before any candidate output — TD-affirmed 2026-10-31 (row 14 of `td_affirmation_2026-10-31.md`); reasons and the dry reading: `bakeoff/metrics/README.md`) | yes, if VALIDATED | TD |
| M5 | `hair_silhouette` | ground-truth hair class and silhouette | hairstyle swapped between two subjects of different hair classes (short straight ↔ curly high-volume) (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 15 of `td_affirmation_2026-10-31.md`), with: «every pair of subjects of different hair classes (short / long / curly), frame-matched — as built») — subject A's ordinary output scored against subject B's sheet; scoring only, FREE | `m` = 0.10 IoU (ENGINEERING JUDGMENT); N = R; the statistic below (agent, drafted in the TD role, 2026-10-30, before any candidate output — TD-affirmed 2026-10-31 (row 16 of `td_affirmation_2026-10-31.md`); reasons and the dry reading: `bakeoff/metrics/README.md`) | yes, if VALIDATED | TD |
| M6 | `occlusion` | depth ordering vs foreground plate and hand, per frame | head rendered over the hand in SHOT_003's `hand_over_face` window (C_HAND_FG plate composited under the head instead of over it) (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 17 of `td_affirmation_2026-10-31.md`), with: «recorded: measured on subjects 01, 06, 07, 08 only (the window is excluded for 02, 03, 04, 05, 09)»); composite-domain, FREE | `m` = 0.5 of the overlap (ENGINEERING JUDGMENT: the head over the hand reads ~1, the correct order ~0); N = R; the statistic below (agent, drafted in the TD role, 2026-10-30, before any candidate output — TD-affirmed 2026-10-31 (row 18 of `td_affirmation_2026-10-31.md`), with: «added: a bad frame is an overlap fraction ≥ 0.5 (= m), PROVISIONAL»; reasons and the dry reading: `bakeoff/metrics/README.md`) | yes, if VALIDATED — per frame pass/fail, a shot fails on its first failing frame | TD |
| M7 | `skin_tone_match` | Δ head vs body skin inside the skin-ID pass after the display transform, per tone | body tone shifted, two levels (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 19 of `td_affirmation_2026-10-31.md`)): gross — one step of the §3 tone ladder (the distance between adjacent ladder values, middle ↔ either end, of the master's recorded range); near-boundary — a quarter step; applied to the body skin inside the skin-ID cryptomatte through the unbaked CDL in the comp (the grade is separate by contract, master-spec), a composite-domain operation, FREE, not a re-render; the metric's value on both levels is recorded | `m` = 2.0 ΔE00 (twice a just-noticeable CIEDE2000 difference); N = R; the statistic below (agent, drafted in the TD role, 2026-10-30, before any candidate output — TD-affirmed 2026-10-31 (row 20 of `td_affirmation_2026-10-31.md`); reasons and the dry reading: `bakeoff/metrics/README.md`) | yes, if VALIDATED | TD |
| M8 | `lighting_match` | head under the shot's lighting reference vs the default head | key light rotated on the head layer only, azimuth about the socket's up axis (+Y), key only, fill untouched, two levels (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 21 of `td_affirmation_2026-10-31.md`)), ENGINEERING JUDGMENT: gross — 30°; near-boundary — 10°. This control is a **re-render of the head layer** (candidate 0 only, 2 levels × 3 shots × 2 profiles), PAID render capacity booked as a Stage 5 sub-step with its own estimate and included in the §5 cap check; the metric's value on both levels is recorded | `m` = 0.05 radius units (ENGINEERING JUDGMENT; kept after its PAID control was read 2026-10-30 — recorded per shot as well); N = R; the statistic below (agent, drafted in the TD role, 2026-10-30, before any candidate output — TD-affirmed 2026-10-31 (row 22 of `td_affirmation_2026-10-31.md`), with: «the verdict is per shot: M8 ranks only on the shots where its verdict is VALIDATED; the pooled verdict is recorded and does not rank»; reasons and the dry reading: `bakeoff/metrics/README.md`) | yes, if VALIDATED | TD |
| M9 | `glasses` | present iff the subject wears them; specular and shadow plausibility — human-only in this bake-off | glasses removed from the glasses subject | n/a (human review, §8) | no — human review only (§8); a wrong glasses state fails the X1 checklist (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 23 of `td_affirmation_2026-10-31.md`)) | TD |
| M10 | `determinism` | same inputs twice: hashes equal or per-pixel variance recorded | none — its own control | n/a | reported | TD |

Criterion form for M1–M8, declared now (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 24 of `td_affirmation_2026-10-31.md`), with: «recorded: for M1, M2 and M5 the 'As built' paragraph governs (known-good 0 / IoU 1, frame-matched); the sheet against front neutral is the embedding's only»); the margins `m` are written with the first
candidate. Known-good: for M3, M4, M6, M7, M8 — candidate 0 (the default head) over the `N_rep`
repeats; for M1, M2, M5 — the subject's own ground truth from protocol §3, nothing rendered by
any head technology: the subject's expression sheet in the state, scored by the estimators
against the same subject's sheet in front neutral (the estimators' own noise on one identity is
the known-good floor; the default head carries no subject identity and no subject hair class,
so it cannot be known-good there — protocol §8's "candidate 0 supplies the known-good side" is
restricted to M3/M4/M6–M8 in the protocol text as of 2026-09-16, a defect the form found).
Known-bad: the row's control on the same items, at its gross level; the near-boundary level is
recorded, not part of the criterion. Statistic — the one the `N_rep` rule of §5 sizes for:
`VALIDATED` when the mean of the known-good values and the mean of the known-bad values differ
by at least `m` in the good direction and the difference is at least three standard errors of
the difference (`s · sqrt(2 / N_rep)`) wide; the overlap of the two ranges is recorded beside the
means; otherwise `NOT_VALIDATED`, reported, not used for ranking. "Yes, if VALIDATED" above means exactly this
test, on this record, per metric.

**As built** (agent, in the TD role, 2026-10-30, before any candidate output — TD-affirmed 2026-10-31 (row 25 of `td_affirmation_2026-10-31.md`);
`bakeoff/metrics/README.md`): the geometric estimators of M1, M2 and M5 read the child's truth **in the same frame of the
same shot** (frame-matched; both files must play the same performance — their FACE_CTRL channels are compared and a
difference refuses the pairing), so their known-good — the truth against itself — is exactly 0 mm and IoU 1: a geometric
estimator has no noise of its own on one identity. The sheet-against-front-neutral reading above stays the embedding
estimator's (deferred by the owner 2026-10-30 until a named local model and its licence): on geometry it would read the
expression, and the part of the face the channels leave still is too small to carry identity (two children 0.69 mm apart
there against 2.43 mm over the whole FACE, measured 2026-10-30). M2's swap is the identity swapped inside the state while
front neutral stays the child's own. M6 compares FINAL with the default head's composite of the same frame where the
front plate is opaque over the head (the post-composite blur moves a moving hand off its sharp plate). M7 reads pairs
across the seam (two bands' medians read the light across the neck). The statistic is `bakeoff/metrics/separation.py`
(the pooled standard deviation of the two sides — `s · sqrt(2 / N)` at equal sizes; one value on a side is
`NOT_VALIDATED`); result rows, the verdict read from rows and `n_rep.json` are `bakeoff/metrics/record.py`. M8's control renders are
`bakeoff/metrics/control_render.py` (the key turned about the socket's up axis through its origin, per frame; L_HEAD only;
the order render's own head call on the master's own file), booked as `bakeoff_control_render`; read dry 2026-10-30 the
30° turn separates pooled but reads at or under the margin under SHOT_001's and SHOT_003's soft key, so Stage 5 records
M8 per shot beside the pooled verdict. M3 cannot see the 1-px edge jitter (its near-boundary level reads the
known-good exactly): a head sliding against the body is M4's.

Operational measures O1–O8 are recorded per candidate as the protocol lists them; O4
`external_crossings` must be ≤ 1 per subject.

## 7. Exit metrics (protocol §7)

### X1 — `cleanup_minutes_to_acceptable`

- **Acceptance checklist** (signed per shot by the TD of record (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 26 of `td_affirmation_2026-10-31.md`), with: «the items affirmed, the signer edited: the owner signs as the TD of record (§12); the agent attaches its evidence to every item (the metric values, the frames of largest motion, the still at 100 %, the subject's sheet); the signer decides»); every item is a
  human pass/fail — a checklist item is not a scale and no metric is its gate: protocol §7
  defines *acceptable* by the signed checklist, and every threshold this bake-off produces is at
  most PROVISIONAL, which `docs/process/definitions.md` keeps out of acceptance gates; the item's
  metric is recorded beside it, and a shot whose
  item and VALIDATED metric disagree is flagged `CHECKLIST_METRIC_CONFLICT` and recalibrates the
  checklist — a NOT_VALIDATED metric is simply recorded). Judged on the shot as video at 24 fps
  and, for the still tier, at 100 % zoom: identity reads as the ground-truth sheet — with the
  sheet beside the shot the signer answers "this is that child" yes, in every state of the shot;
  seam invisible at 100 % — no line, step or colour change along the neck at 100 % zoom on the
  shot's still frame and on the frame of largest head motion; no flicker at speed — nothing
  pulses inside the head at 24 fps; hair silhouette matches the class — the hair class equals the
  subject's and the silhouette reads as the sheet's; occlusion correct — the hand and the
  foreground plate are in front of the head on every frame of their windows; skin tone matches
  the body — no tone step at the neck; glasses correct — present iff the subject is
  `glasses: PRESCRIPTION`, drawn with a shadow and a specular. A checklist the §8 reviewers
  contradict is recalibrated and the contradiction recorded.
- **Failed shot** (the trigger for Stage 6, protocol §7) (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 27 of `td_affirmation_2026-10-31.md`), with: «the signer flags (the agent may propose a flag with its evidence); per protocol §7 a failed shot is also one past a PROVISIONAL threshold — none exists before Stage 5, so that condition is empty in this bake-off, recorded»): a Stage 4 run whose raw
  output the TD flags on any checklist item above, the flag written with the item's name before
  any repair starts; `P_fail(tier)` of X2 is the fraction of Stage 4 runs so flagged, per tier.
  One repair per failed **cell** (the first flagged repeat is repaired; the others stay counted
  in `P_fail`), never one per repeat.
- `cleanup_ceiling_minutes` per shot = ~~**120**~~ (replaced, row 28) (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 28 of `td_affirmation_2026-10-31.md`), with: «replaced (owner, 2026-10-31, В3): per shot — 3 render iterations on the Mac over the affected frame range or 180 agent minutes, whichever comes first; per still — 2 iterations or 45 minutes; PROVISIONAL; at the ceiling `UNRECOVERABLE`, never folded into a mean; the repair's minutes and iterations counted once per shot in X2. The worst case for §9 (every cell failed, every repair to the ceiling, N_ref = 9): ≈ 31–50 Mac hours of video re-render and < 1 of stills, ≈ 101 agent hours, per candidate — it replaces the 67.5 h below»), ENGINEERING JUDGMENT — one minute
  per frame of a 120-frame shot: past that a repair is re-animation, i.e. "shot redesign
  required", not cleanup; per still = **30** (a quarter of the shot ceiling — a still has no
  frames to re-animate). Every shot is multi-tier in `state_map.json` (SHOT_001 EASY + MEDIUM,
  SHOT_002 MEDIUM + DIFFICULT, SHOT_003 MEDIUM + STRESS): a shot's minutes are shown whole on
  each of its tier rows in the X3 tables (reporting, never split) and counted **once per shot**
  in X2 (no tier row adds them twice). Implied worst case for the owner's cap row in §9, one
  repair per failed cell: video `N_ref × 3 shots × 2 h` + stills `N_ref × 3 × 0.5 h` = 67.5 h
  per candidate, candidate 0 included, at `N_ref = 9`. At the ceiling a shot is
  `UNRECOVERABLE`, never folded into a mean.
- Who repairs: **an agent repairer, the same for every candidate** (owner, 2026-10-31, В2; confirmed «поехали» the same day): which agent and on which machine is decided before Stage 6 — not the agent that launches the candidates' runs, which knows every code. X1 is four columns, never summed (protocol §7, amended 2026-10-31): agent minutes, operations (commands and, separately, render iterations), the Mac hours of the repair's render iterations (booked `bakeoff_cleanup`, inside `BAKEOFF_COST_CAP`; at the cap — the checkpoint stops, the owner decides), and the human minutes of the TD's sign-off. Stage 6 is `PAID (machine + human signing)`; the agent time's money is `UNKNOWN` with its reason until the owner names a rate. ~~TD note (agent, drafted in the TD role, 2026-09-16): if the owner names the agent-led pipeline as the repairer, its minutes are machine wall-clock, go into a separate non-monetizable column, and X1 human minutes read `UNKNOWN` — X2 then cannot price cleanup, which is the quantity the bake-off exists to compare.~~ (struck 2026-10-31, row 29 of `td_affirmation_2026-10-31.md`: the decision replaced its 'if'; the repair's Mac hours and operations are measurable and comparable across candidates.) Shot order randomized by a
  seeded Fisher–Yates shuffle, seed = sha256 of `experiment_id + ":" + stage + ":" +
  session_id`, seed and order written to the record before the first shot is opened. Blind to
  the candidate, per artifact class (the repairer's, 2026-10-31, `td_affirmation_2026-10-31.md` §2): video frames and stills — blind for
  the candidates, not for candidate 0 (the master's own head, known on sight): files under the artifact code, no paths,
  `candidate_id`, `run_id` or metadata; head geometry, if a repair is made in 3D — blind for B1-M (the master's
  topology), not for a candidate of another topology (recorded); the repair log — blind (no record or registry file in
  the repair packet). The repairer knows the candidate list from the form, so blind means 'not by the file'; with one
  registered candidate the only distinction is candidate 0 against not — recorded. Whoever repaired a shot cannot
  review its cleaned output blind (§8).
- What is counted: the four columns above — agent minutes from first opening the shot to submission for sign-off;
  operations; the repair's Mac hours; the signing minutes; tools recorded.
- Operator rate for X2 (the signing minutes) and the agent's rate: `TO FILL (owner)` or `UNKNOWN` — until then
  minutes and Mac hours are reported beside money, never summed.

### X2 — cost and wall-clock per finished cartoon

Formula as in the protocol §7; inputs and their status at freeze:

| Input | Value | Status | Filled by |
|---|---|---|---|
| `frames(tier)` | §4 `MIX_PROVISIONAL` | ESTIMATE | owner + TD |
| total head-render frames | ~4,300 | ESTIMATE (master-spec) | agent, pre-filled |
| comic panels | 40–60 | ESTIMATE | agent, pre-filled |
| `worker_warmup_minutes`, `t_comp`, `S_frame` | from the slice record (P1) | measured — the package's `slice/package_manifest.json` (P1); the row read `UNKNOWN` after P1 was met, corrected 2026-10-31 (the TD table §6) | TD |
| operator rate | `TO FILL` | `UNKNOWN` | owner |

Reported per candidate × subject as the range across subjects; the worst subject decides.

### X3 — per-subject results

Every table per subject × per tier; no average across subjects or tiers anywhere in the record
or the ADR. A missing cell is `NOT_EVALUATED` with a reason and the candidate is `INCOMPLETE`.

## 8. Negative controls and blind review (protocol §8)

- Planted known-bad artifacts in every review set (identity-swapped, flicker-injected,
  seam-shifted, wrong-hairstyle, head-over-hand, wrong-skin-tone): rate = **1 planted per 5
  genuine items, at least 2 per session** (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 30 of `td_affirmation_2026-10-31.md`), with: «replaced: the number planted in a session, k, is drawn by the sealed salt uniformly from [2, max(2, ⌈0.3 × genuine⌉)] — the form states only the range; each of the six kinds at least once per cycle; the salt (≥ 128 bits) and the code map are held by a **third party who reviews in no session** (`TO FILL (owner)`, before the first session; the owner now reviews), its sha256 in the record before the first session, revealed at Stage 8; every session is recorded as 'the range is known to the reviewer'»), every one of the six kinds planted at least
  once per review cycle (a cycle = the set of sessions that covers every candidate's outputs of
  one kind, raw or cleaned, once); positions drawn from a seeded shuffle whose seed is a
  **secret salt** of at least 128 random bits generated and held by ~~the **owner**, who reviews
  in no session~~ a third party who reviews in no session (row 30) (not the published X1 seed), sealed by its committed sha256 before the first
  session and revealed at Stage 8 exactly like the artifact map below; unknown to every
  reviewer, the TD of record included. A session holds at least 10 genuine items.
- **Reviewer discrimination floor** = **80 %** (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 31 of `td_affirmation_2026-10-31.md`), with: «with a variable k: a reviewer catches ⌈0.8·k⌉») — the fraction of planted negatives a
  reviewer must catch, rounded up (`ceil(0.8 × planted)`: with 2 planted, both; with 3, all
  three; with 5, at least 4); and a **false-alarm ceiling** of 20 % — a false alarm is a
  `defect_types[]` entry of a planted kind (identity, flicker, seam, hair, occlusion, skin tone)
  on a genuine item in the session template of protocol §8; a reviewer with more than
  `floor(0.2 × genuine)` of them (at least 2 at the 10-item minimum) is not discriminating
  either. Below the floor or above the ceiling the session's ratings are
  discarded and the discard recorded with the reviewer's pseudonymous id.
- Reviewers: count `TO FILL (owner)`; roles — at least one naive person and the TD of record;
  ids pseudonymous. TD note (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 32 of `td_affirmation_2026-10-31.md`), with: «replaced: reviewers are people only — the owner (TD of record), at least one naive person, if possible one more person; the count is the owner's. The agent (the repairer, also the burst-2 animator) is not a reviewer: an AI reviewer is an AI judge, which protocol §8 does not admit. The owner's sessions on **cleaned** outputs are not blind (he signed the repairs) and are excluded from every blind conclusion; on raw outputs they are blind only as far as the codes conceal — the candidates' runs are launched on his machine, recorded»), a proposal, not a commitment: three — the TD of record,
  the burst-2 animator as `animator`, one naive person who has never seen the pipeline. The TD
  of record's sessions on **cleaned** outputs are not blind (the repairs are recognizable) and
  are excluded from every blind-review conclusion; recorded as such.
- Scales (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 33 of `td_affirmation_2026-10-31.md`)), declared once, used in every session — five points, anchored, only the
  anchors below are shown to reviewers: `likeness_to_ground_truth` 1 = a different child, 3 =
  resembles the sheet, 5 = the child on the sheet; `alive_and_expressive` 1 = a static mask, 3 =
  moves but reads flat, 5 = alive, the expression reads; `seam` 1 = the head is visibly attached,
  3 = a line is visible when looked for, 5 = nothing to find at 100 %; `hair` 1 = wrong class, 3 =
  right class, silhouette off, 5 = matches the sheet; `skin_tone` 1 = a different tone from the
  body, 3 = a step is visible at the neck, 5 = one skin; `glasses` 1 = wrong state (present or
  absent against the sheet), 3 = right state, no shadow or specular, 5 = right state, plausible;
  `artifacts` 1 = distracting on every viewing, 3 = visible when looked for, 5 = none; `ship`
  yes/no is the reviewer's own verdict, asked last.
- Media: video at 24 fps; STILL at 100 % zoom or as a print. Per tier (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 34 of `td_affirmation_2026-10-31.md`)): EASY,
  MEDIUM, DIFFICULT, STRESS — `VIDEO_24FPS`, the whole shot once, then each state window of the
  tier looped three times; the still tier — `STILL_100PCT` on a display set to the profile's
  display transform (repository `slice/conventions.json` → colour at the freeze commit: Rec.709
  for video, `display_print` for the still profile) for every subject, plus `STILL_PRINT` at A4 300 dpi for one subject per
  candidate, the same subject for all.
- The candidate ↔ `artifact_code` map is sealed until Stage 8: sealed by hash (agent, drafted in the TD role, 2026-09-16 — TD-affirmed 2026-10-31 (row 35 of `td_affirmation_2026-10-31.md`), with: «added: the map is written by a script run by the salt holder; the owner receives coded packets only; if the holder cannot run the script and the owner does, the owner's sessions are recorded as not blind») —
  `artifact_map.json` is written outside the record when the codes are assigned, its sha256 is
  committed to the record as `artifact_map.sha256` before the first review session, and at Stage
  8 the map itself is committed and must hash to that value; a mismatch voids every session.
- AI judges: only as a §6 metric with its own control and calibration; never ground truth.

## 9. Cost, cap and environment (protocol §9)

| Item | Value | Filled by |
|---|---|---|
| `BAKEOFF_COST_CAP` | **220 Mac hours** — the M4's wall-clock of the bake-off's render and composite jobs from Stage 1 on, summed at every checkpoint against the next stage's estimate (`stage_cost_estimate.json`); sized for three repeats (owner, 2026-10-29: «три повтора, 220 часов»). Money is not in it: past the FaceBuilder subscription already running, any new spend goes to the owner first. Human minutes (Stages 6–7) are reported alongside until an operator rate exists (protocol §9). Machine-readable in `cap.json` (the one source; a test holds this row to it); every paid Mac job booked by `bakeoff/ledger.py` into `cost_records/` (`machine_time`), checked before each stage by `bakeoff/checkpoint.py` (2026-10-29) | owner |
| Spend-control decision: (a) self-hosted candidates only, or (b) amend `spend_control` so `bakeoff` may enable external calls under the cap and alert — recommended (b) | `OPEN` — `TO FILL` | owner |
| Ledger | `PLATFORM_COST`, `amortization_basis: PER_MASTER`, `entity_ref.experiment_id` = this id; stage names per protocol §9 | agent, pre-filled |
| Environment | `bakeoff` project: synthetic set and slice only; no real subject artifact of any class | agent, pre-filled |
| Estimated cost per stage (0–8), with source and date — required before each checkpoint | `stage_cost_estimate.json` (2026-10-29, agent in the TD role; `bakeoff/stage_cost_estimate.py`): FaceBuilder alone with candidate 0, 9 subjects; the plan (R = max(3, N_rep), candidate 0 rendered once per cell, §5): with the owner's order render ((b) the shadow at half resolution, (a) the boxed head, 2026-10-29) **74–145 Mac hours at R = 3** against the cap of 220, 91–181 at R = 4 — from the order render measured on the package's 18 frames the same day (11.3–18.4 s per frame against 33.5–42.9 for one full-frame call; `slice/measurements/order_render_2026-10-29/`); the first estimate that day, from one close-up's per-layer seconds, was 112–165 / 139–206; without (b) 158–237 / 197–298; the protocol's own count without (b) 242–343 at R = 3. Stages 6–7 human minutes and Stage 5's metric CPU `UNKNOWN`; recomputed with R after Stage 3 and at every checkpoint | TD + owner |
| Stop rule | cap exceeded → `BAKEOFF_COST_CAP_EXCEEDED`, owner decides; never a silent continuation | agent, pre-filled |

## 10. Pass and decision rules — restated so nobody re-derives them later

A candidate has PASSED when all seven conditions of protocol §11 hold. The decision ranks
passed candidates on total marginal cost per acceptable cartoon, worst subject (X2 with X1
folded in), and names PRIMARY and RUNNER-UP; two candidates within observed variance get
another repeat on the discriminating tier, not a preference.

## 11. What this bake-off cannot establish (protocol §11, copied into ADR-0003 as its limits)

Quality on real parents' photographs (phone optics, lighting, age, expression at upload);
parent satisfaction with a likeness; behaviour across twelve scenes with secondary characters;
hair-simulation cost at the full hair variety of real children; the stability of any vendor's
terms; performance at 10, 50 or 100 concurrent orders. What a human compositor's cleanup minutes would be: cleanup is
measured as an agent's repair, in its four columns (owner, 2026-10-31). An independent human technical review of this
pre-registration: its technical fields were drafted by the project's agent and checked by a second agent (the slice
contractor), and the owner signed them as the TD of record on the agents' evidence (2026-10-31).

## 12. Sign-off and freeze

| Field | Value |
|---|---|
| TD of record | **The owner, by signature** (owner, 2026-10-31, В1; confirmed «поехали» the same day). The slice contractor — an AI agent — prepared the affirmation table `td_affirmation_2026-10-31.md` (sha256 `8622ff80…`, in this record); the owner signed it on 2026-10-31 («поехали», answering the agent's request to sign the table and the statement below). An agent affirming an agent's drafts is not an independent check; the signature is a person's (§11 records the limit). In the records under a pseudonymous id (`operator_id`, a ULID), never a name. The role: the party who signs every X1 checklist and the freeze. The fields marked "drafted in the TD role" became the form's values only by this affirmation, field by field; the struck draft is struck, not adopted |
| Owner | `TO FILL` |
| Statement: no subject in §3 is derived from any real person's photograph | **Signed by the owner (TD of record), 2026-10-31** («поехали»). Grounds — the contractor's (`td_affirmation_2026-10-31.md` §5): the nine heads built by `build_character.py` from MPFB2 / MakeHuman (CC0 assets, `contractor/burst-1/LICENSES.md`), targets by table and bumps by seed; procedural materials, no textures; the parents' 'photos' are renders of the same heads; no photograph of a person as input, seed or reference. Ours: every head rebuilt from his scripts and compared (burst 3), and the build scripts load no image (scanned 2026-10-31) |
| `frozen` | `false` |
| Frozen at (date, commit) | `TO FILL` |
| sha256 of this file at freeze (also written into `decision.md`) | `TO FILL` |

## 13. Amendments after freeze

Dated appendix only; each entry states what changed, why, and which results (if any) it
affects. None yet.
