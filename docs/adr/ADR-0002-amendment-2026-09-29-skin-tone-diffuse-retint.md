# ADR-0002 amendment — the body's skin tone re-tinted through the diffuse light (diffuse passes and a skin matte per layer)

## Status

**APPROVED — 2026-09-29 by the owner («утверждаю»); merged into ADR-0002 the same day (D4, D5),
`master_contract_version = 5`.** The owner chose option 2 of the Phase 0.5 exit review's step 5 B ("согласен, пиши текст
поправки вариант 2"). It changes D5 (the frozen pass set: three passes and a matte on two beauty layers, two derived parts)
and makes D4's re-tint concrete (CLAUDE.md §9: changing an approved ADR). The evidence:
`slice/measurements/skin_tone_retint.py`, results and sheets in `slice/measurements/skin_tone_retint_2026-09-29/` and
`<the archive disk>/reviews/skin_tone_2026-09-29/`. Implementation: §Implemented (to follow).

## What was found

D4 asks for a skin ID and an unbaked grade "so re-tinting is possible at all", and CLAUDE.md §3 personalises the tone of
all exposed hero skin. It does not say how the per-order compositor re-tints, and it never did: SKIN_ID was derived and
gated but not consumed (exit criterion 4 open). The method was measured on the three accepted shots (25 %, the QC frames):
the body re-rendered with HERO_SKIN_BODY at three synthetic tones is the truth; each method re-tints the master's own
render; the error is the mean of the largest channel difference over the visible skin after the blur gate's 4×4 low-pass,
relative to the truth.

| Tone (scene-linear albedo) | option 2 — the diffuse light re-tinted | option 1 — a 2D gain by the skin matte | no re-tint |
|---|---|---|---|
| lighter (0.90, 0.72, 0.62) | 0.3–0.4 % | 2–9 % | 22–35 % |
| dark (0.40, 0.24, 0.16) | 0.7–0.9 % | 10–38 % | 124–160 % |
| very dark (0.20, 0.11, 0.07) | 1.1–1.4 % | 25–78 % | 290–384 % |

SHOT_002 (the strong coloured key) 1121 / 1210 / 1217 and SHOT_003 1338 (the body and the hand in front); the master's
tone is (0.80, 0.55, 0.45). The 2D gain paints the skin's white specular with the tone: on dark skin under SHOT_002's key
the orange rim on the neck goes out and the neck turns muddy grey (the sheets). Re-tinting only the diffuse light —
`Combined + (DiffCol·gain − DiffCol)·(DiffDir + DiffInd)` from Cycles' Diffuse Color, Diffuse Direct and Diffuse Indirect
passes — leaves the specular white and lands within 1.4 % on every tone, the coloured key included.

Found while measuring: the skin matte comes from the full render, where the hand in front carries the same skin material,
so the body behind the hand read as skin (the first SHOT_003 body numbers were 6–37 % off for option 2 until the hand's
footprint was excluded). The full render also cannot see the neck under the default head, which a different child's head
may uncover. A skin matte per layer is needed.

## Proposal

**C1. Passes (D5).** On the two beauty layers that carry hero body skin — L_BODY (the back) and L_FG (the front plate) — the
master renders Cycles' Diffuse Color, Diffuse Direct and Diffuse Indirect passes and the material cryptomatte of that
layer. Render settings only: the character asset, its materials and the contractor's files do not change.

**C2. Derived once per master (the compositor's derivation, beside STATIC_PRECOMP).** Per frame and layer,
`SKIN_DIFFUSE_<layer> = skin(layer) · DiffCol · (DiffDir + DiffInd)` (RGB, half, declared scene-linear), with skin(layer)
the coverage of the body-skin material in that layer's own cryptomatte. SKIN_DIFFUSE_BACK and SKIN_DIFFUSE_FRONT join the
COMPOSITE bundle's derived parts; the raw passes stay in the master's archive and are not read per order. The master's
skin albedo (the body-skin material's base colour) is recorded in the package.

**C3. Per order.** `gain = target_albedo / master_albedo` per channel, from the order's approved skin tone. The back and
the front are re-tinted before compositing and before the blur:
`BACK = (BODY_BEAUTY + (gain − 1)·SKIN_DIFFUSE_BACK) × SHADOW_MULTIPLY_ORDER`,
`FRONT = PRECOMP_FRONT + (gain − 1)·SKIN_DIFFUSE_FRONT`. A tone outside the master's supported range is a qualification
reject (D4), never clamped. The head's skin is the head technology's; how head and body tones meet is bake-off metric M7.

**C4. The supported tone range is measured (D4).** Per master version, the body is rendered at the tones that bound the
intended range and at its middle, on the frames that show the most body skin in each shot, and the re-tint is measured as
above. The range the master supports is where the error stays within a PROVISIONAL bound (proposed 3 %; measured ≤ 1.4 %);
no re-tint must fail it (the negative control). These truth renders are a `MASTER_COST` line, never per order.

## Cost

- **Render:** none measurable — the same paths feed the three passes (7.4–8.7 s against 7.3–8.5 s per 25 % beauty frame
  in the experiment).
- **Storage:** the raw beauty EXR grows ~14 % (+3.7–3.9 MB per frame at 25 %); the two derived parts are zero outside the
  skin and compress well — the per-order read grows by them only.
- **Per order:** one multiply-add per layer before compositing — negligible beside the blur (15–74 s per 4K frame).
- **Master:** the C4 truth renders — about four bodies × the chosen frames per shot per master version.
- **No contractor work.**

## Alternatives

- **Option 1, a 2D gain by the skin matte** — measured 25–78 % off on very dark skin.
- **Re-render the body per order** — exact, but the beauty render costs ~110 GPU-seconds per 4K frame on the project's M4;
  even the body layer alone over ~4 900 frames is tens of GPU-hours per order — the marginal cost of one cartoon the
  reusable master exists to avoid (CLAUDE.md §2).
- **Master variants at a few fixed tones** — the tone quantised to the variants, N× the master's render and storage.
- **A custom skin-irradiance shader output (AOV)** — the same quantity, but a material change in the character asset; the
  standard passes and a per-layer cryptomatte need none.

## Does not solve

- **Skin that bounces light onto itself:** the indirect term carries the master's albedo — second order, inside the
  measured 1.4 %.
- **Subsurface scattering:** this skin has none. A master whose skin scatters needs the subsurface passes in the same way;
  re-measure (C4) before relying on it.
- **Skin textures or makeup** multiply correctly (the gain scales the albedo), but a tone-dependent pattern (freckles) is
  not a tone.
- **The head's tone and the neck seam's colour match** — the head technology's and the bake-off's (M7).

## Validation after approval

`render_passes.py` renders the passes and the per-layer cryptomatte (conventions: the pass table, the bundle's parts);
`composite.py` derives SKIN_DIFFUSE_BACK / FRONT and records the master albedo; `composite_order.py` takes the order's skin
tone (`--skin-tone`), refuses one outside the master's range, re-tints before compositing and the blur, and records it;
`slice/check_skin_tone.py` makes C4 a gate with its negative control. Tests: a synthetic scene whose truth is known passes,
no re-tint fails, a tone outside the range is refused. Then the slice's conformant runs again, the package re-hashed, and
C4 on the three shots.

## Implemented (2026-09-29)

- **C1** `slice/render_passes.py`: the beauty group turns on Diffuse Color / Direct / Indirect and the material cryptomatte
  (depth 6) on L_BODY and L_FG and records the skin material (`skin_material`: base colour, subsurface, textured → status
  RE-TINTABLE or not); `slice/split_bundles.py` writes them as SKIN_BUNDLE (`skin.####.exr`), each cryptomatte part carrying
  only its own layer's manifest (three layers now carry a material cryptomatte).
- **C2** `slice/composite.py`: `layer_skin` (the body-skin coverage in a layer's own cryptomatte), `skin_diffuse`, `retint`;
  SKIN_DIFFUSE_BACK / FRONT among the derived parts; the master's albedo in `derived.skin_tone`. A render without SKIN_BUNDLE
  (before contract v5) is refused, not skipped.
- **C3** `slice/composite_order.py --skin-tone R,G,B | master` (required): the gain applied through `composite.retint` on the
  back before the shadow and on the front, before compositing and the blur; refused without a PASS/VACUOUS gate on the
  bundle, outside its range, for a skin a gain cannot describe, or malformed; the tone in the idempotency key and the manifest.
- **C4** `slice/check_skin_tone.py`: the gate as specified; tones and bound in `conventions.json → skin_tone.gate`
  (PROVISIONAL). **Found on the first real run:** measured on each layer's own matte, the back also counted the open neck
  under the head — the body plate shows it, lit mostly by the skin's own inter-reflection, which a gain describes badly
  (3–21 % off there; the experiment, on the full render's matte, never saw it). No head lets it through (the per-order
  unfilled gate), so the gate measures the back where neither the front plate nor the head's holdout covers it. Results on
  the conformant v5 renders: SHOT_002 PASS (worst 1.07 %), SHOT_003 PASS (worst 1.36 %; the body and the hand), SHOT_001
  VACUOUS (a close-up: no body skin outside the head); no re-tint 22–383 % on every case.
- **Measured cost on the conformant v5 renders:** SKIN_BUNDLE 45–61 MB per 4K video frame (+18–22 % on the COMPOSITE
  bundle's 250–272 MB; the master's archive, not read per order); the per-order composite's time unchanged (14–17 s per
  4K video frame with the blur, 36–75 s on the fastest; 1.4–1.8 s per still). The order composites of the three shots at the
  master tone still equal the QC path's blurred frames within two half steps; at the middle and darkest tones the skin
  changes and nothing else does (`<the archive disk>/reviews/skin_tone_2026-09-29/order_*.png`). The slice
  package holds the v5 renders, the gate records and the order composites (`package_hash` faa1096a).
