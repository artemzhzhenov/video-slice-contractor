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
- Derivation is refused when the probe:
  - is not a skin-probe render;
  - misses a frame;
  - is not at the conventions' tone in every toned material;
  - was rendered with other settings than the master's;
  - has direct diffuse light on the skin more than `direct_light_match_max` off the master's — the albedo cannot change
    it, so it is not the master's render at another albedo.

**D3. Per order.**

    g = a_t / a_m        w = (a_t − a_m) / (a_p − a_m)        (per channel)
    LAYER' = LAYER + (g − 1)·SKIN_DIFFUSE + w·REST + g·w·BOUNCE

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
  REST and BOUNCE as such. The gate's blocks average them; `direct_light_match_max` is a mean.
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
