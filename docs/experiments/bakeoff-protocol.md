# Head Architecture Bake-Off — protocol (Phase 1)

Layer: Core (`../architecture/layering.md`) — a platform experiment; the only Kids values it
reads are the ones cited. Source: `../qc/evidence-and-experiments.md` (§Required Head
Architecture Bake-Off, the three exit metrics, tiers, negative controls), ADR-0002
(`../adr/ADR-0002-master-head-interface.md`, the socket the candidates must consume and the
Phase 0.5 slice), comic spec §8 (STILL tier), `../architecture/avatar-pipeline.md` (the four
candidate families and the evaluation axes). Written 2026-09-10 to close gate G7. Every rule
here is binding in the sense of `../process/definitions.md` (must / must not / not required
before Phase N); every number is either cited or marked ESTIMATE / PROVISIONAL.

Read before planning, costing, running, reviewing or recording any part of Phase 1.

## 0. What the bake-off decides, and what it does not

**Decides** — by ADR-0003 (head representation), written from the record this protocol
produces: the head technology for the `HUMAN_FACE` identity adapter, as one PRIMARY and one
RUNNER-UP; the values of the hair-class enumeration (ADR-0002 §D3); the
`relative_to_head_tech` value that makes the slice's `head_replacement_difficulty` grades
non-stale; the first named calibration set for every `PROVISIONAL` threshold in the avatar
qualification gate.

**Does not decide** — and must not be used to reopen: that the master is 3D (CLAUDE.md §4.4);
the personalization boundary (§3); the raw-photo rule (§5); the master ↔ head contract
(ADR-0002) — a candidate that needs the contract changed has excluded itself, invariant 15.

**The question, stated once.** Which head representation produces the same recognizable
synthetic child across the slice's three shots, in both render profiles, at the lowest total
marginal cost per acceptable cartoon — cleanup minutes included — without receiving the source
photos more than once?

## 1. Preconditions — all must hold before the first run

| # | Precondition | Evidence that it holds |
|---|---|---|
| P1 | The Phase 0.5 reference slice is delivered and has passed all eight exit criteria of ADR-0002 §Validation (the eighth, blur fidelity, since the 2026-09-22 amendment) and the brief's three | The eleven results (`docs/experiments/phase-0-5-exit-review.md`), plus `t_comp`, `S_frame` per bundle and `worker_warmup_minutes`, are written into the bake-off record (§10). A slice that has not round-tripped (§D7) is not an input. |
| P2 | The synthetic reference set exists in the composition of §3, content-hashed and versioned | `reference_set_manifest.json` in the record; one `AVATAR` per subject with `canonical_ref` under `ref:synthetic/` (`../../fixtures/bakeoff_dry_run/avatar.1.json` is the shape) |
| P3 | Every candidate is a `MODEL_REGISTRY_ENTRY` in status `TESTING` with capability `HEAD_RENDER` (and `DERIVATION` when it performs its own photo → identity step), `receives_child_data: false` for the duration of the bake-off | Registry fixtures committed with the record. A candidate that is not registered does not run. |
| P4 | The result-row schema exists | `schemas/bakeoff_result.json` validates the row of §10; `fixtures/bakeoff_result/` holds valid rows and `fixtures/_invalid/bakeoff_result/` the rejected ones; the dry run carries one row. Present since 2026-09-14. |
| P5 | The owner has set `BAKEOFF_COST_CAP` | A single-source-of-truth config value; `UNKNOWN` today. No paid stage of §5 starts while it is a sentinel. |
| P6 | Pre-registration is committed | `preregistration.md` in the record (§10) — hypotheses, the candidate list, every separation criterion, the pilot plan for repeat counts, the cleanup ceiling, the reviewer discrimination floor, `MIX_PROVISIONAL` — committed **before any candidate output exists**. A criterion added after the numbers are visible is a defect (`../process/definitions.md`, meaningful degradation). |
| P7 | The three slice performance tracks cover every benchmark state | `state_map.json` (§4) has every state mapped to at least one shot and frame range. A tier with zero covered states is `NOT_EVALUATED` for every candidate and the slice is amended before the bake-off starts, not after. |

## 2. Candidates

At least three, spanning at least two of the four families in `../architecture/avatar-pipeline.md`
— A 2D rig, B 3D head, C neural avatar, D hybrid. Each candidate declares, in the registry entry
and in `preregistration.md`:

- where AI runs: **once per child**, **once per shot**, or **once per frame** — the declaration
  the working hypothesis in avatar-pipeline.md is tested against;
- how it is driven: directly by the project performance track (ADR-0002 §D8), or through a
  project-owned adapter that translates the track — the adapter is then part of the candidate,
  and its cost and its determinism are the candidate's;
- which of the 14 base passes it consumes (`pass_dependency`, §6) and whether it needs any pass
  outside the frozen set — an incremental pass request is recorded, not granted;
- exact version, weights hash or API version, license, `self_hosted_weights`, and the privacy
  block — sentinels are permitted during the bake-off because no child data is involved, and
  they block `QUALIFIED` afterwards exactly as G8 says.

**Candidate 0 — the default head** (ADR-0002 §D2) is not a candidate. It is the known-good
baseline for the seam, lighting and composite metrics and the negative-control substrate; it is
run through every stage so that every metric has a floor to be compared with.

### Exclusion criteria — decided at Stage 0, on paper and by the contract-fit test

An excluded candidate is a **result** with a recorded reason. It is never silently dropped.

| Code | Excluded when | Rule violated |
|---|---|---|
| `EXCLUDED_BY_BOUNDARY` | The candidate needs the source photographs, or a re-identifiable derivative of them (photoreal crop, face embedding, biometric template), at any step after its own derivation — per shot, per frame, or "as a reference" | CLAUDE.md §5; `raw_photo_external_calls_cap: 1` in `../policy/kids-policy.md` |
| `EXCLUDED_BY_CONTRACT` | The candidate cannot consume the socket transform, camera and holdout of ADR-0002 §D1/§D7; or cannot deliver a head layer terminated at the socket curve, scene-linear, premultiplied alpha, at the video and still resolutions of §D6; or cannot deliver that layer **sharp with its own per-layer motion vectors and depth** (amendment 2026-09-22 — the master applies motion blur after compositing, so a candidate no longer matches blur but must supply vectors), and, if it delivers geometry, with the §D1 overlap margin below the socket curve; or cannot deliver the personalized head+hair shadow onto the body against the collision proxy and lighting reference (§D3 — the master's pass 9 is the default head's shadow and is not a per-order input) | ADR-0002; invariant 15 |
| `EXCLUDED_BY_PERFORMANCE` | The candidate cannot be driven by the performance track, directly or through a costed adapter, and must supply its own acting | Invariant 6 — the master owns the performance |
| `EXCLUDED_BY_SCALE` | The candidate expresses identity by scaling the head outside the socket envelope | ADR-0002 §D1 |

Exclusion at Stage 0 costs nothing. Discovering the same fact at Phase 8 costs a master.

## 3. The synthetic reference set

The children in the bake-off are not real. This is what lets the set be committed, shared with
reviewers and vendors, held identical across candidates for years, and used to build negative
controls — none of which is possible with a customer's frames (`../privacy/retention.md`).

**Provenance.** Every reference identity is generated by the project from a synthetic source;
no photograph of a real person is an input, a seed, or a style reference to any of them. License
and generation method are recorded per subject. A reference whose provenance cannot be stated is
removed from the set.

**Each subject provides two things**, and the distinction is what makes the identity metric
honest:

- the **upload packet** — the photographs a parent would upload, in the format and quality
  parents produce (phone camera, mixed lighting, three to five images, per the intake spec of
  Phase 2 once it exists; until then, the packet composition is recorded in the manifest). This
  is what every candidate receives, and it is all a candidate receives.
- the **ground truth** — a turntable and an expression sheet of the same synthetic identity
  rendered in the slice's lighting reference. Candidates never see it. Likeness is measured
  against it, never against the upload packet.

**Composition — minimum rows.** A set missing any row is not a reference set, whatever its size.

| Dimension | Required coverage | Basis |
|---|---|---|
| Skin tone | Both ends and the middle of the master's supported tone range (ADR-0002 §D4) — at least three values, one of them at each boundary | CLAUDE.md §3 — the tone must match; the boundary is where a clamp would hide |
| Hair | At least: short straight; long straight; curly high-volume; one subject whose hair crosses the forehead in the neutral pose | ADR-0002 §D3 — the enumeration's values are set from these results |
| Glasses | At least one subject with `glasses: PRESCRIPTION`; that subject appears in every tier | CLAUDE.md §4.9; avatar-pipeline.md — glasses are a benchmark case in their own right |
| Facial features | Documented variation in face shape, eye spacing, nose form — the variation is stated per subject, not assumed from the count | evidence-and-experiments.md |
| Age and body presentation | Within the slice master's `age_range` and matching its `body_presentation` | Separate masters per gender, §4.3; the slice is one master |

The count `N_ref` is recorded in `preregistration.md`. It is not prescribed here: it is the
smallest count that fills every row above with the tone and hair dimensions crossed, and it is
the number the wall-clock of §5 is planned against.

**Held identical.** The set is content-hashed as a whole (`reference_set_hash`) and per subject.
Any change bumps `reference_set_version`; results across versions are not comparable and are
not placed in one table.

**Reuse.** The same set is what staging runs (`../architecture/platform.md`), what negative
controls are built from, and what visual regression cases reproduce on
(`../privacy/retention.md`). It is a durable project asset.

## 4. The benchmark matrix

### Tiers and states

The fifteen benchmark states of `../qc/evidence-and-experiments.md` map onto the four video
difficulty tiers as follows. The mapping is ENGINEERING JUDGMENT and `PROVISIONAL`: a state whose
observed failure rate contradicts its tier is remapped after the bake-off, and the remap is
recorded with the result that caused it.

| Tier | States |
|---|---|
| EASY | front neutral; smile; gaze shift; blink |
| MEDIUM | 3/4; laughter; fear; sadness; head turn; open mouth / interjection |
| DIFFICULT | profile; strong light; profile + strong emotion |
| STRESS | hand over face; fast movement |
| STILL | one still per slice shot per subject at print resolution (comic spec §3.3, ADR-0002 §D9); inspected at 100 % zoom or as a print, never as video |

The glasses subject crosses every tier as a subject dimension, not as a state.

### How states are realized

The slice's three shots (EASY / DIFFICULT / STRESS by shot design — camera, occlusion, lighting)
are the bake-off's shot set. States are realized as **performance-track content on those
shots**: `state_map.json` lists, per state, the shot triple `(master_id, master_version,
shot_id)` and the frame range in which the state occurs. The track is project-owned (ADR-0002
§D8), so this costs authoring, not rendering. Every state appears in at least one shot (P7).

### Units and size

    run  = (candidate, subject, shot, render_profile, repeat_index)
    size = C × N_ref × 3 shots × (1 video + 1 still) × N_rep

`C` ≥ 3 candidates plus candidate 0. `N_rep` is not a universal number: it is set per metric by
the pilot of §5 Stage 3 from observed variance and the pre-declared separation margin, and
recorded before Stage 4. One run is not evidence; a conclusion drawn from one run is labelled
`UNVERIFIED` wherever it appears.

## 5. Procedure — cheapest discriminating stage first

Each stage is a cost checkpoint: before it starts, `sum(cost_records[experiment_id]) +
estimated_cost_of_stage > BAKEOFF_COST_CAP` stops the bake-off with `BAKEOFF_COST_CAP_EXCEEDED`
and hands the decision to the owner — never a silent continuation. Stages 1–4, 6 and 7 are
PAID (`../process/definitions.md`: billable external calls, render capacity, or human time) and
carry the full paid-stage declaration of `../costs/cost-model.md`.

| Stage | What runs | Cost class | Records |
|---|---|---|---|
| 0 Contract fit | Each candidate re-imports the **default head's own identity** and composites it through the slice's socket, holdout, shadow, depth and skin-ID passes on one shot; the §D7 round-trip is repeated with the candidate's head layer in place. Exclusion criteria (§2) applied. | FREE | `contract_fit: PASS | EXCLUDED_*` per candidate, `pass_dependency` |
| 1 Onboarding | Each candidate turns each subject's upload packet into its identity representation. Run twice per subject. | PAID | `onboarding_minutes`, `onboarding_cost`, `external_crossings` (the §5 counter, per subject), `human_touch_minutes`, determinism of the two runs |
| 2 STILL tier | One still per shot per subject per candidate. The cheapest full-fidelity signal; gross failures (envelope, tone out of range, glasses missing or invented) surface here. | PAID | Still results stand on their own — they decide `COMIC` qualification (comic spec §4.3). **No candidate is eliminated on stills**; the owner may stop a candidate at any checkpoint on cost, and that stop is recorded. |
| 3 Pilot | One subject — named in pre-registration — × 3 shots × `n_pilot` repeats per candidate, video profile. | PAID | Observed variance per metric → `N_rep` per metric, written to the record before Stage 4 |
| 4 Full matrix | Every run of §4 at `N_rep`. | PAID | One result row per run (§10) |
| 5 Metrics + negative controls | Every automated metric of §6 on every run, and on every negative control. | FREE | Metric values; per-metric `VALIDATED | NOT_VALIDATED` from the separation criterion |
| 6 Cleanup | Every failed shot repaired by a human to the acceptance checklist (§7, X1). | PAID (human) | `cleanup_minutes_to_acceptable` or `UNRECOVERABLE` per shot |
| 7 Blind review | §8, on raw outputs **and** on cleaned outputs, with planted negatives. | PAID (human) | Review sessions; reviewer discrimination |
| 8 Extrapolation and decision | §7 X2 and X3; ADR-0003 drafted from the record. | FREE | `decision.md`, the ADR |

Stage order is fixed. Running Stage 4 before Stage 3 has set `N_rep` is a defect, because the
repeat count would then be a guess.

## 6. Metrics

Every automated metric carries, in pre-registration: what it measures, its input, its negative
control, and its **separation criterion** — margin and repeat count, declared before the run.
A metric whose known-good and known-bad distributions overlap is `NOT_VALIDATED` and is reported
but **not used for ranking**. Every threshold that comes out of the bake-off is `PROVISIONAL`,
with this record as its named calibration set.

| ID | Metric | Measured against | Negative control (synthetic subjects only) |
|---|---|---|---|
| M1 | `identity_likeness` — per state | The subject's ground-truth sheet in the same state and lighting. Two estimators run side by side: a face-embedding distance, which is `UNVALIDATED` on stylized faces until it passes this row's control (`../qc/evidence-and-experiments.md`); and a landmark-geometry deviation on the project's own rig. | Identity swap: candidate output for subject A scored against subject B's ground truth |
| M2 | `identity_stability_over_performance` | M1 in each state relative to M1 in front neutral, per subject | Same as M1 |
| M3 | `temporal_stability` | Frame-to-frame change inside the head holdout, per shot | Injected flicker on the default-head composite |
| M4 | `seam` | Luma/chroma discontinuity and edge alignment along the `NECK_PROXY` curve, against the default-head composite | Head scale ± a declared step (`HEAD_SCALED`); edge shifted by a declared number of pixels (`SEAM_SHIFTED`) |
| M5 | `hair_silhouette` | Ground-truth hair class and silhouette; hair-crossing-forehead handled | Hairstyle swapped between two subjects |
| M6 | `occlusion` | Depth-correct ordering against the foreground plate and hand, per frame | Head rendered over the hand |
| M7 | `skin_tone_match` | Δ between head skin and body skin inside the skin-ID pass, after the same display transform, per tone value | Body tone shifted one declared step |
| M8 | `lighting_match` | Head under the shot's lighting reference against the default head | Key light rotated on the head layer only |
| M9 | `glasses` | Present when the subject wears them, absent otherwise; specular and shadow plausibility — human-only in this bake-off | Glasses removed from the glasses subject |
| M10 | `determinism` | Same inputs twice: output hashes equal, or the per-pixel variance recorded | None — it is its own control |

Operational measures, recorded per candidate and used in §7:

    O1 onboarding_minutes (per subject)       O5 human_touch_minutes (onboarding)
    O2 render_seconds_per_frame, per_still    O6 pass_dependency[] (which of the 14 passes)
    O3 cost_per_frame, cost_per_still         O7 vendor_portability: self-hosted weights |
       — actual, or UNKNOWN with reason           API-only | licensed export
    O4 external_crossings per subject         O8 production_complexity — ENGINEERING JUDGMENT,
       (must be ≤ 1)                              written as a list of moving parts, not a score

Do not let one metric measure several phenomena: M1 is masked to the head holdout so that camera,
body and background cannot move it.

## 7. The three mandatory exit metrics

A candidate that cannot produce all three has not passed, whatever its pictures look like
(`../qc/evidence-and-experiments.md`).

### X1 — `cleanup_minutes_to_acceptable`

- **Acceptable** is defined before the run by the **acceptance checklist** in
  `preregistration.md`, signed per shot by the TD of record: identity reads as the ground-truth
  sheet; seam invisible at 100 %; no flicker at speed; hair silhouette matches the class; occlusion
  correct; skin tone matches the body; glasses correct. The checklist is later checked against
  the blind review (§8) — a checklist the reviewers contradict is recalibrated and the
  contradiction recorded.
- **Failed shot** = any shot below a `PROVISIONAL` threshold or flagged by the TD on the raw
  output.
- **Who repairs:** the same compositor or compositors for every candidate; shot order
  randomized; the compositor does not know which candidate produced the shot wherever the
  artifact allows it, and the record says whether it did.
- **What is counted:** wall-clock from first opening the shot to checklist sign-off, render
  iterations included; tools used are recorded.
- **Ceiling:** `cleanup_ceiling_minutes` per shot, declared in pre-registration. A shot that
  reaches it is `UNRECOVERABLE` — counted as such, never folded into a mean. An unrecoverable
  shot is what "shot redesign required" means in `../qc/evidence-and-experiments.md`. A repair
  halted by an owner cost stop (§5) is recorded as `STOPPED` with the minutes spent; it is
  neither acceptable nor unrecoverable and is excluded from X1 with that label.
- **Reported** per candidate × tier × subject. Each repair also produces a failure-database record
  with a `defect_type` from the taxonomy in `../qc/evidence-and-experiments.md`.

### X2 — cost and wall-clock per finished cartoon

An ESTIMATE, carrying source, date, formula and assumptions (`../costs/cost-model.md`), never
a bare number. Per candidate, per subject, then reported as the **range across subjects** —
the worst subject is the number that matters, because that is the child whose order costs the
most.

    per_child_cost(candidate, subject) =
        onboarding_cost
      + Σ_tier  frames(tier) × cost_per_frame(candidate, subject, tier)
      + Σ_tier  frames(tier) × P_fail(candidate, subject, tier) × cleanup_cost_per_failed_frame
      + comic:  panels × cost_per_still + cleanup for stills

    wall_clock(candidate, subject) = critical path of the same terms, with
        worker_warmup_minutes and t_comp taken from the slice record (P1)

Inputs and their status:

| Input | Where it comes from | Status |
|---|---|---|
| `frames(tier)` | `MIX_PROVISIONAL` — the declared shot-difficulty mix of a full master, set by the TD and the owner in pre-registration, because no storyboard exists yet | ESTIMATE; replaced by the real mix at Phase 8 |
| total head-render frames | ~4,300 (`../architecture/master-spec.md`) | ESTIMATE until the storyboard exists |
| comic panels | 40–60 (comic spec §5) | ESTIMATE |
| `cost_per_frame`, `cost_per_still` | Stage 4 and Stage 2, actual provider or compute cost | measured, or `UNKNOWN` with reason |
| `P_fail(tier)` | fraction of Stage 4 runs that needed cleanup, per tier | measured |
| `cleanup_cost_per_failed_frame` | X1 minutes × operator rate | minutes are measured; the rate is `UNKNOWN` until the owner supplies it — until then X2 is reported in **money for machine cost plus minutes for human cost**, two columns, never summed into one |

An X2 that hides which column is measured and which is estimated is a defect.

### X3 — per-subject results

Every table in the record is per subject × per tier. Averages across subjects, or across tiers,
are forbidden in the record and in the ADR. A candidate with a missing subject × tier cell has
not passed: the cell is `NOT_EVALUATED` with a reason, and the candidate's status is
`INCOMPLETE`, not `PASSED`.

## 8. Negative controls and blind human review

### Negative controls

Every control is constructed from the synthetic set; the default head (candidate 0) supplies the
known-good side for M3, M4, M6, M7 and M8; for M1, M2 and M5 the known-good side is the subject's
own §3 ground truth (the sheet scored against itself across states), because the default head
carries no subject identity and no subject hair class (defect found by the pre-registration form,
2026-09-16). The construction is per metric in §6. In addition, the review set (below)
contains **planted known-bad artifacts** — identity-swapped, flicker-injected, seam-shifted,
wrong-hairstyle, head-over-hand, wrong-skin-tone — at a rate declared in pre-registration and
unknown to reviewers.

### Blind review — session template

Every review session is recorded with these fields; the template is the schema of the
`review_session` file in the record.

    session_id, reviewer_id (pseudonymous), reviewer_role (naive | TD | animator | other),
    medium (VIDEO_24FPS | STILL_100PCT | STILL_PRINT), tier,
    items[]:
        artifact_code            — random; the candidate ↔ code map is sealed until Stage 8
        subject_id, shot, states[]
        ground_truth_shown       — the subject's sheet is visible to the reviewer
        likeness_to_ground_truth — declared scale
        alive_and_expressive     — the character must not be static to pass (avatar-pipeline.md)
        seam, hair, skin_tone, glasses, artifacts — declared scale each
        ship (yes | no)
        defect_types[]           — from the failure taxonomy
        ab_pair (optional): other_artifact_code, preferred, confidence
    planted_negatives_caught / planted_negatives_total

**Reviewer discrimination.** The floor — the fraction of planted negatives a reviewer must catch —
is declared in pre-registration. A reviewer below the floor has that session's ratings discarded,
and the discard is recorded. Reviewers include at least one person who has never seen the
pipeline and the TD of record; the count is recorded, not prescribed here.

**Media.** Video is reviewed as video at 24 fps; STILL items at 100 % zoom or as a print. A
still reviewed as a scaled-down video frame has not been reviewed.

**AI judges** may be run on the same items only as a candidate metric under §6's rules —
calibrated on clearly-good, clearly-bad and borderline items first, and never as ground truth
(`../qc/evidence-and-experiments.md`).

## 9. Cost, spend control and environment

- **Ledger.** Every cost of the bake-off is `PLATFORM_COST` with `entity_ref.experiment_id` and
  `amortization_basis: PER_MASTER` — the decision it buys applies to every master. Stage names
  in the cost records: `bakeoff_onboarding`, `bakeoff_still`, `bakeoff_pilot`, `bakeoff_matrix`,
  `bakeoff_cleanup_minutes`, `bakeoff_review`, and `bakeoff_control_render` (the PAID control re-renders of §6 and our
  ground-truth sheets; added 2026-10-29). The slice's own render is booked as
  `bakeoff_slice_render` (`../../fixtures/bakeoff_dry_run/cost_record.1.json`), also
  `PLATFORM_COST` — owner decision 2026-09-11, recorded in ADR-0002 §Validation.
- **Cap.** `BAKEOFF_COST_CAP` is set by the owner before Stage 1 and evaluated at every stage
  checkpoint (§5). Human minutes count toward it at the operator rate once one exists; until
  then they are reported alongside it.
- **Environment.** The bake-off runs in the `bakeoff` environment — a separate cloud project
  (`../architecture/platform.md`) holding only the synthetic set and the slice. No real
  subject's artifact of any class exists there.
- **External calls.** `schemas/spend_control.json` fixes `EXTERNAL_CALLS_ENABLED` and
  `PAID_STAGES_ENABLED` to `false` in every environment except `prod`, `bakeoff` included. As
  encoded today, **no candidate that requires a billable external call can run in the bake-off**:
  only candidates on project-controlled compute — self-hosted weights, the DCC, local renderers —
  are runnable. This is an owner decision, recorded OPEN in PROJECT_STATE:
  - (a) keep the constraint — the bake-off admits self-hosted candidates only, which pre-decides
    the vendor-portability axis before it is measured; or
  - (b) amend `spend_control` so that `bakeoff` may set both flags `true` only when
    `BAKEOFF_COST_CAP` and `platform_spend_alert` are non-sentinel, with `provider_mode`
    recorded per call. **Recommended**: it keeps the kill switch and lets the bake-off measure
    what it exists to measure.
  Under either answer, an external call during the bake-off carries synthetic inputs only, and
  the receiving vendor's registry entry has `receives_child_data: false` — it becomes `true`
  only through the G8 privacy gate before Phase 2, which the winning candidate must pass or
  yield to the runner-up.

## 10. The bake-off record — what is committed

    benchmarks/bakeoff/<experiment_id>/
        preregistration.md          §1 P6 — committed before any output exists
        reference_set_manifest.json §3 — subjects, provenance, packet composition, hashes
        avatars/*.json              AVATAR per synthetic subject (schema exists)
        state_map.json              §4 — state → shot triple → frame range
        slice/                      shot manifests, performance tracks, the eight ADR-0002
                                    validation results and the brief's three, t_comp, S_frame,
                                    worker_warmup_minutes
        registry/*.json             MODEL_REGISTRY_ENTRY per candidate (schema exists)
        results/*.json              one row per run and tier (`schemas/bakeoff_result.json`)
        negative_controls/*.json    one row per control run, same schema, control kind set
        cleanup_log.json            §7 X1 per shot
        review_sessions/*.json      §8
        cost_records/*.json         COST_RECORD (schema exists)
        jobs/, render_units/        JOB and RENDER_UNIT as issued (schemas exist)
        decision.md                 §11 — the input to ADR-0003

`fixtures/bakeoff_dry_run/` (gate G9) is this record with sentinels in place of measurements:
the dry run proved the existing schemas hold it without a field added. The one artifact added
for Phase 1 is the result row (`schemas/bakeoff_result.json`), whose fields are:

    experiment_id, run_id, candidate_id, candidate_version, subject_id,
    shot {master_id, master_version, shot_id}, render_profile, tier, states[],
    repeat_index, inputs_hash, output_ref,
    metrics {M1 … M10: value | UNKNOWN | NOT_VERIFIED},
    reasons_if_sentinel {field: reason} — one entry per sentinel field, none on a measured row,
    control_kind (NONE | …), control_detail {against_subject_id, declared_step, note} when not NONE,
    cost (money), wall_clock_seconds,
    cleanup {minutes, outcome: ACCEPTABLE | UNRECOVERABLE | STOPPED, operator_id, checklist_signed},
    review_session_ids[], recorded_at

A **row is one run × one tier**: a shot whose states span two tiers (SHOT_002 carries MEDIUM
and DIFFICULT states) yields two rows with the same `run_id`, each with the states of its own
tier and metrics computed over that tier's frame ranges from `state_map.json`. The schema
rejects a state outside its row's tier, so the X3 tables cannot be miscategorized by hand.

Outputs rendered from synthetic subjects may be committed; they are the benchmark. No frame of
a real person enters this directory under any circumstances (`../privacy/retention.md`).

## 11. Exit criterion, decision, stop criteria

**A candidate has PASSED the protocol** — which is not the same as winning — when all of:

1. `contract_fit: PASS` (Stage 0);
2. every subject × tier cell has X1 and the X2 inputs, per subject (X3);
3. every automated metric used for ranking is `VALIDATED` by its negative control under its
   pre-declared separation criterion;
4. blind review exists from reviewers above the discrimination floor, on raw and cleaned output;
5. M10 determinism is recorded;
6. `external_crossings` ≤ 1 for every subject;
7. every cost is recorded as actual or as a sentinel with a reason — no `0`, no blank.

**The decision** (`decision.md` → ADR-0003) ranks passed candidates on **total marginal cost
per acceptable cartoon, worst subject** — X2 with X1 folded in — and names PRIMARY and
RUNNER-UP. Where two candidates are within the observed variance of each other, the answer is
another repeat on the discriminating tier, not a preference. The ADR also fixes: the hair-class
enumeration values; `relative_to_head_tech` for the slice shots and `stale: false`; the
`qualified_against_head_tech_version` string format; the first `PROVISIONAL` thresholds with
this record as their calibration set; and what Phase 2 must verify about the winner's privacy
block before any real photograph exists.

**Stop criteria.** The bake-off stops, and the owner decides, when: `BAKEOFF_COST_CAP` would be
exceeded; any real person's imagery is found anywhere in the environment or record (this is an
incident, `../privacy/threat-model.md`); the slice fails an ADR-0002 exit criterion after the
bake-off has started (ADR-0002 reopens first); no candidate passes.

**What this bake-off cannot establish** — write these into the ADR as its limits: quality on
real parents' photographs (phone optics, lighting, age, expression at upload); parent
satisfaction with a likeness; behaviour across twelve scenes with secondary characters rather
than three shots with one; hair-simulation cost at the full hair variety of real children; the
stability of any vendor's terms; performance at 10, 50 or 100 concurrent orders. Each is a later
phase's question and is listed so nobody reads the ADR as answering it.

## 12. Definition of Done — where each experiment field lives

`../process/definition-of-done.md` requires an experiment to record thirteen fields. Their
homes in the record:

| Field | Where |
|---|---|
| question, hypothesis | `preregistration.md` (§0, §2 per candidate) |
| input | `reference_set_manifest.json`, `slice/`, `state_map.json` |
| variants | `registry/` — the candidates |
| repeat_method | `preregistration.md` pilot plan; `N_rep` per metric after Stage 3 |
| metrics, negative_controls | §6, `results/`, `negative_controls/` |
| human_review | `review_sessions/`, `cleanup_log.json` |
| cost | `cost_records/`, X2 |
| results | `results/`, the X1–X3 tables |
| limitations | §11 "cannot establish", copied into the ADR |
| decision, next_action | `decision.md`, ADR-0003 |
