# ADR-0002 amendment — the skin tone re-tinted between the master and a probe render (skin-to-skin light)

## Status

**APPROVED — 2026-10-31, by the owner («поехали»).** The owner approved option (A) as proposed the same day, after the
master's full-range render stopped at SHOT_003's skin-tone gate.

- This amends the 2026-09-29 amendment (`ADR-0002-amendment-2026-09-29-skin-tone-diffuse-retint.md`): its C2 (one more
  derived bundle), C3 (the per-order formula) and C4 (the gate). It also retires the first bullet of that amendment's
  "Does not solve".
- It is merged into ADR-0002 (Status, D4, D5).
- `master_contract_version` goes from 6 to 7. The change is additive: every v6 plate and part is unchanged. The master
  gains a derived bundle, and the per-order re-tint gains a required input — without it, no tone but the master's is
  re-tinted.
- Evidence: `slice/measurements/skin_tone_interreflection_2026-10-31/` and
  `<the archive disk>/reviews/skin_tone_SHOT_003_2026-10-31/`.

## What was found

The full-range gate measured SHOT_003 on 14 frames instead of 2026-09-29's three. On frame 1291, the darkest tone, the
hand in front of the face was 0.0316 off against the bound 0.03.

**It is not noise.** The run is deterministic: 1338 repeats the 2026-09-29 value exactly. The direct diffuse light, the
diffuse colour and the skin matte are identical in master and truth.

**The whole error is light that reached the skin off skin.** At the darkest tone, the truth's indirect diffuse light on
the hand falls to 0.76–0.85 of the master's; at the lightest it rises to 1.03–1.08. Part of it bounced off the body's own
skin first — the other fingers, the arm — and so carries the tone. The skin's specular reflection of skin adds about a
third (0.009 of 0.032 at 1291).

C3 keeps the master's indirect light and scales it by the gain. The 2026-09-29 amendment named this "second order, inside
the measured 1.4 %". On these frames it is not:

- **The mean hides a local defect.** At 1291, darkest tone, the 99th percentile of the 4×4-block error is 38 % and the
  maximum 60 %, in the gaps between the fingers. At the middle tone the 99th percentile is 13 % and the maximum 23 %.
  SHOT_002, which passed, reaches 6–9 % at the 99th percentile on the darkest.
- **SHOT_001's gate was VACUOUS, yet the shot has skin to re-tint.** The body shows 6,500–18,000 px of neck skin at 100 % on
  every frame. The strip is too thin for the gate's 4×4 low-pass at 25 %, which counted a block only when all 16 pixels
  were skin. Measured over blocks of 8 skin pixels, C3 is 5–7 % off there on average and 15–32 % at the 99th percentile.

**The fix was measured on the gate's own renders, with no new render.** One more render of the master at another tone —
a probe — makes the indirect light and the rest linear in the albedo between two known points. On the tones held out of
the probe:

- the gate mean falls from ≤ 0.0114 to ≤ 0.0039;
- at 1291, middle tone, the 99th percentile falls from 13.3 % to 1.6 % and the maximum from 23.5 % to 2.7 %.

A probe at the middle tone extrapolated to the darkest amplified the sampling noise 2.4× and did not hold on the body. The
probe belongs beyond the dark end.

## The decision

**D1. The probe render.**

- Per master version and profile, the shot file is copied with every hero skin material at `skin_tone.probe.tone`
  (0.15, 0.08, 0.05): HERO_SKIN_BODY and HERO_SKIN_HEAD, both plain base colours (`slice/skin_probe.py set-tone`).
  - The tone is darker than the gate's darkest in every channel.
  - The head is toned too: CLAUDE.md §3 makes all exposed skin the child's, so the light the default head throws on the
    body darkens with the body.
- Only the two layers that carry body skin are rendered — L_BODY and L_FG, render group `skin_probe`
  (`slice/render_passes.py --skin-probe`). They are rendered exactly as the plates' beauty group renders them: samples,
  scale, seed, gaze, exports.
- It is not a plate: `split_bundles.py` refuses it.

**D2. SKIN_PROBE_BUNDLE, derived once per master** (`slice/skin_probe.py derive`, the formulas in `slice/skin_retint.py`).

- Per frame and layer (BACK = L_BODY, FRONT = L_FG), with skin the layer's own body-skin coverage (C2), C the layer's
  Combined, m the master and p the probe:

      BOUNCE = skin · DiffCol_m · (DiffInd_p − DiffInd_m)
      REST   = skin · [(C_p − skin·DiffCol_p·(DiffDir_p + DiffInd_p)) − (C_m − skin·DiffCol_m·(DiffDir_m + DiffInd_m))]

- The parts are RGB half, declared `data`, zero off the skin, in `skin_probe.####.exr` beside the master's bundles. The
  bundle manifest records them with pixel hashes and the probe's albedo and render.
- Amended 2026-11-01 (§Amended 2026-11-01 — the skin's edge): per layer also SHARED, the pixels the skin shares with
  another surface, and EDGE = C_p − C_m on them.
- Derivation is refused when the probe:
  - is not a skin-probe render;
  - misses a frame;
  - is not at the conventions' tone in every toned material;
  - was rendered with other settings than the master's;
  - has direct diffuse light on the skin more than `direct_light_match_max` off the master's — the albedo cannot change
    it, so it is not the master's render at another albedo. Measured inside the skin, by blocks (2026-11-01, see
    Implemented): at the skin's edge and per pixel the albedo does move Cycles' direct pass;
  - has no layer of any frame where that can be measured;
  - a refused derivation leaves the bundle that was there (it is written beside and put in place whole).

**D3. Per order.**

    g = a_t / a_m        w = (a_t − a_m) / (a_p − a_m)        (per channel)
    LAYER' = LAYER + (g − 1)·SKIN_DIFFUSE + w·REST + g·w·BOUNCE

- Amended 2026-11-01: on the SHARED pixels `LAYER' = LAYER + w·EDGE` instead (§Amended 2026-11-01).
- It is applied on the back before the order's shadow multiply and on the front plate, before compositing and the blur.
- It is exact where light reached the skin off skin once. The residual is the light that did so twice.
- At the master's tone (w = 0) nothing changes; at the probe's (w = 1) the probe is reproduced.
- `composite_order.py` refuses every tone but `master` without SKIN_PROBE_BUNDLE and a passing gate of the probe method.

**D4. The gate (C4 amended)** (`slice/check_skin_tone.py`).

- Per shot, at the gate's scale and samples, it renders:
  - the master;
  - its probe, derived through D2;
  - the truths — the shot with every hero skin material at each gate tone. The probe is not a gate tone: every gate tone
    is held out of it.
- The master is re-tinted through D3.
- It is measured over 4×4 blocks holding at least `block_min_skin_px` (8) of visible skin, each block's mean taken over
  those pixels alone. A frame, tone and layer counts with `min_skin_blocks` (20) blocks.
- **PASS** needs all three:
  - every mean within `relative_error_max` (3 %);
  - every 99th percentile within `relative_error_p99_max`;
  - no re-tint fails the mean bound — the negative control.
- `relative_error_p99_max` is set by the owner after the first measurement with the probe. Until then the gate measures,
  records and refuses a verdict (NOT_JUDGED).
- The first-order re-tint is recorded beside each case as evidence, not judged.

**D5. The master's full-range stage** (`bakeoff/stages/master_full_range.py`).

- `probe` renders the probe in resumable chunks.
- `gate` merges them, derives the bundle and runs the gate. A gate measured on the first-order re-tint is moved aside
  (`skin_tone.first_order`), never deleted.
- `package` takes a shot only when its skin-tone gate is of the probe method.

## Cost

- **Probe render:** two of the plates' six layers — expected about a third of the plates' render. The plates took
  4.1–5.0 Mac h a shot. A `MASTER_COST` line per master version, never per order. Measured on the first shot and recorded
  in the stage's cost estimate.
- **Storage:** four RGB half parts per frame, zero off the skin. The raw probe render stays in the run, outside the
  package.
- **Per order:** one more file read per frame (the probe's parts) and two multiply-adds per layer — beside the blur,
  negligible.
- **Gate:** one more render per shot at 25 % — the probe, two layers.
- **No contractor work; no asset change.**

## Alternatives

- **(B) a looser bound for the darkest tone** — rejected by the owner: the finger gaps of dark-skinned children stay
  lighter.
- **(C) the darkest tone out of the supported range** — contradicts CLAUDE.md §3.
- **A probe at the middle tone, extrapolated** — measured: it does not hold on the body (noise ×2.4).
- **A per-shot correction fitted to the gate's truths** — it fits the frames it is judged on, and the skin-to-skin light
  varies per pixel.
- **The body re-rendered per order** — the marginal cost the reusable master exists to avoid (CLAUDE.md §2).

## Does not solve

- **Light that reached the skin off skin twice** — the residual, measured ≤ 0.4 % mean on held-out tones.
- **Clothing lit by skin** keeps the master's bounce. REST is applied on the skin alone; elsewhere it would carry the two
  renders' noise into every order.
- **The order's head is not the default head.** The light the head throws on the body is the default head's shape at the
  order's tone.
- **Metal does not repeat a frame pixel for pixel** (Known Risks). Two renders differ in rare isolated pixels, which enter
  REST and BOUNCE as such. The gate's blocks average them; `direct_light_match_max` is a mean over blocks.
- **The still profile.** The package's stills of SHOT_001 and SHOT_003 were rendered before the gaze amendment
  (2026-09-30). A probe rendered now follows it, and its settings would not be the stills', so D2 refuses the pair. The
  stills need a fresh render and their own probe before a still order can be re-tinted. Until then a still re-tints
  nothing (`master` only).
- **Subsurface:** none on this skin, as before.

## Validation

- **CI** (`tests/test_skin_retint.py`), on a synthetic layer whose light is linear in the albedo:
  - the probe re-tint is exact and the first-order one is not;
  - the master's and the probe's tones are reproduced;
  - nothing changes off the skin, and alpha never changes;
  - a probe with another direct light, or at the master's albedo in a channel, is refused;
  - blocks measure a thin strip.
- **Gate verdicts** (`tests/test_check_skin_tone.py`): a local defect fails while the mean passes; NOT_JUDGED without the
  owner's bound.
- **Stage** (`tests/test_bakeoff_master_full_range.py`): the probe merge, the first-order gate moved aside, and packaging
  only by the probe method.
- **Blender:**
  - the probe render holds only the two skin layers and its tone, and is never bundled (`tests/test_slice_render.py`);
  - on the smoke frame, the order is refused without the probe and without a probe-method gate; with both, the skin
    changes and nothing else does (`tests/test_slice_composite.py`).
- **Controls on the master, before the probe renders:**
  - the probe rendered at the master's own tone, a few frames at 100 % — REST and BOUNCE ≈ 0, which also measures
    `direct_light_match_max`;
  - then the gate on the three shots.

## Implemented

2026-10-31, the files named above; the conventions in `slice/conventions.json → skin_tone` and
`render_groups.skin_probe`. Measured results follow the probe renders.

2026-11-01 — the D2 guard on the direct light, after the three shots' probes were refused at 1.1–2.1 % against 0.002
(`slice/measurements/skin_tone_interreflection_2026-10-31/README.md`, "The probe renders and the guard on the direct
light"). The figure was the pixel mean over all the skin. It held two effects of the albedo:
- sampling noise inside the skin, 0.5–0.9 % per pixel with a zero mean;
- at pixels the skin shares with cloth, Cycles' direct pass is the light weighted by each surface's colour, 3.5–11 %.

The guard now takes the skin's interior and its 16 px blocks, at 100 % and scaled with the render
(`skin_tone.probe.direct_light_interior`). There the probe measures 1.2–2.0e-4 and the probe's next frame 0.0034–0.75.
The bound is unchanged. The decision (D1–D5) is unchanged.

## Amended 2026-11-01 — the skin's edge

**APPROVED — 2026-11-01, by the owner** (decision 13, option (A): «идем по пути, который ты рекомендуешь»). It amends D2
and D3; D1, D4 and D5 are unchanged. `master_contract_version` stays 7: no v7 package exists yet, the renders are
unchanged, and only the derived bundle's parts change — derived again from the same renders.

**What was found.** The gate on the three shots with the probe stopped NOT_JUDGED — the 99th percentile's bound is not set
(`slice/measurements/skin_tone_interreflection_2026-10-31/README.md`, "The gate with the probe, and the edge"):
- darkest tone, worst mean: SHOT_001 0.0625 (13 of 39 cases over 0.03), SHOT_002 0.0189, SHOT_003 0.0274; the 99th
  percentile 0.23–0.40;
- inside the skin the probe holds: ≤ 0.0056 mean, ≤ 0.022 at the 99th percentile;
- 86–100 % of the body's error lies in blocks holding a pixel the skin shares with another surface — the cloth at the
  collar and the sleeves.

There C2's `SKIN_DIFFUSE = skin·DiffCol·(DiffDir + DiffInd)` takes the pixel's Diffuse Color — the surfaces' colours mixed
by coverage — for the skin's, and the gain scales the cloth's share of the light too. The cause is 2026-09-29's C2, not
the probe; the gate's blocks of 8 skin pixels (2026-10-31) made it visible.

**The decision.**
- **D2:** per layer two more parts (`slice/skin_retint.edge_parts`):
  - `SHARED_<side>`, Y half: 1 on the pixels the skin shares with another surface — skin coverage above 0 and below
    `skin_tone.probe.edge.coverage_min` (0.999), or the probe's Diffuse Color over the master's off the albedos' ratio by
    more than `edge.colour_ratio_off_max` (0.01) in a channel;
  - `EDGE_<side>`, RGB half: `C_p − C_m` on those pixels, zero elsewhere.
- **D3:** on the SHARED pixels `LAYER' = LAYER + w·EDGE`; elsewhere unchanged. Exact where the pixel's light is linear in
  the albedo. At the master's tone (w = 0) nothing changes; at the probe's (w = 1) the probe is reproduced, the edge too.
- **A bundle derived before this** — other parts, or the edge by other thresholds (`slice/skin_probe.derived_by_current_rule`):
  - no order uses it: `composite_order.py` refuses it;
  - no gate is judged on it: `check_skin_tone.py --recompare` derives the gate's own again, and the full-range stage
    derives the master's again (`--replace`) and runs its gate again;
  - the older rule's records are kept beside (`*.older_rule.*`), never overwritten.
- **The count of layers with skin:** a layer whose cryptomatte carries the material but has no pixel more skin than not is
  NO_SKIN. SHOT_001 recorded 240 such layers where 120 have any skin.

**Evidence, before the code** (8 frames × 3 tones a shot; `edge_two_point_SHOT_00n.json`; sheets in
`<the archive disk>/reviews/skin_tone_edge_2026-11-01/`). Worst mean / 99th percentile:

| tone | the probe formula | with the edge | the two-point on all the skin |
|---|---|---|---|
| lightest | 0.0101 / 0.058 | 0.0043 / 0.023 | 0.0066 / 0.062 |
| middle | 0.0133 / 0.082 | 0.0042 / 0.028 | 0.0108 / 0.111 |
| darkest | 0.0625 / 0.404 | 0.0063 / 0.030 | 0.0089 / 0.077 |

The two-point is worse inside the skin, where the probe formula carries the light skin throws on skin. The edge alone takes
it.

**Cost.**
- **No render.** Derivation again on the CPU: the three shots' full-range bundles and the gates' own.
- **Storage:** two more RGB half and two Y half parts per frame, zero off the edge.
- **Per order:** the same file read, one select per pixel.

**Does not solve.**
- **Clothing lit by skin** keeps the master's bounce, as before: the edge rule acts only where the skin covers part of the
  pixel.
- **At an edge pixel, light that is not linear in the albedo** — skin to skin twice — is the residual, as inside.
- **The two thresholds are the prototype's:** set by what half-quantised passes can tell (the albedos' ratio holds to
  ~1e-3 on skin alone), not fitted to the gate.

**Validation.**
- **CI** (`tests/test_skin_retint.py`):
  - on a ring of pixels the skin shares with cloth, the re-tint is exact where the pixel's light is linear, and the probe
    formula there is not;
  - a fully covered pixel whose colour is off the ratio is shared, one within it is not;
  - non-finite edge parts are refused;
  - the master's and the probe's tones are reproduced, the edge included.
- **CI** (`tests/test_skin_probe.py`, `tests/test_bakeoff_master_full_range.py`): a bundle of an older rule is not
  current; the stage derives it again and runs its gate again.
- **Blender smoke** (`tests/test_slice_composite.py`):
  - EDGE and SHARED are written and their pixels counted;
  - the empty front plate is NO_SKIN;
  - an order on a bundle of the older rule is refused.
- **Then** the gate `--recompare` on the three shots, and the owner's bound for the 99th percentile.

**Measured** (2026-11-01, `ed147d6`; `slice/measurements/skin_tone_interreflection_2026-10-31/README.md`, "The gate with
the edge"). The three shots' bundles were derived again and the gate re-run: 0.71 Mac h on the CPU, no render.
- Over 126 cases, the worst mean is 0.0063, where it was 0.0625.
- The worst 99th percentile is 0.0302, where it was 0.404: SHOT_003 1291, darkest, the body. It is the only case over
  0.03; 95 % of the cases are ≤ 0.021.
- The negative control holds, at ≥ 0.21.
- What is left is the hand before the face at the middle tone (max 0.083, unchanged by the edge) — the residual named
  above.
- The gate is NOT_JUDGED until the owner sets `relative_error_p99_max`.
