# ADR-0002 amendment — the order's video render: the head in its screen box, the shadow at half resolution

## Status

**APPROVED in substance — 2026-10-29, by the owner's two decisions of that day: (a) the head layer rendered in its screen
box («принять сейчас») and (b) the order's shadow layer at half resolution («идем по пути Б»); the owner's go for the
render built that way («да, начни с рендера, делай аккуратненько»).** The engineering inside them is the TD's: the
bilinear return (`slice/measurements/shadow_upsample_2026-10-29/`), the denominator as a master plate, the render-context
gate, the box's margin and cut rule, the completion of the boxed layer. Merged into ADR-0002 (Status, D3, D5, §Validation);
`master_contract_version = 6` — additive: every v5 plate, part and consumer is unchanged, the master gains one plate.
Implemented and validated — §Implemented, §Validation.

## What was decided, and why it needs the contract

An order renders two layers with its head in the master's scene: `L_HEAD` (the head, its vectors and depth) and
`L_BODYSHADOW` (the master's body under the order's head; `HEAD_SHADOW_MULTIPLY = L_BODYSHADOW / L_BODY`). Measured on the
M4 (2026-10-23/24): 34.5 s per close-up 4K frame in one call, ≈ 47 h per order; the body under the shadow costs more than
the head (30.5 s against 13.3). The owner chose two ways down:

- **(b)** the shadow layer at half resolution — 64 spp, the multiply formed there and returned to 4K. A multiply is a
  ratio of two renders: it is clean only when both are rendered with the same seed, so that wherever the head shadows
  nothing they trace the same paths and the ratio is exactly 1. The full-resolution master's `L_BODY` (`BODY_BEAUTY`)
  cannot be that denominator at half resolution: its paths are another resolution's. So the master renders its `L_BODY`
  once more, at the order's shadow resolution and samples — a new plate.
- **(a)** the head layer rendered in its screen box — it pays only with (b), once the head renders in a call of its own
  (2026-10-29: the shadow itself cannot be boxed on the slice's shots — the close-up's reaches the frame's edge, the wide
  shot's camera-side fill spreads it over 70 % of the frame). The head layer the composite receives must still be the
  full-frame layer: Blender leaves 10000 in the Vector pass outside a border, which the post-composite blur would read as
  10000-px paths.

## Decision

1. **D5 gains row 15, `ORDER_SHADOW_DENOMINATOR`** — the master's `L_BODY` at the order's shadow resolution (video:
   50 % of the profile's), the profile's samples, rendered once per master version (`MASTER_COST`) from the master's own
   shot file in the master's render context. Consumer: a head technology that renders its head's shadow in the master's
   scene at that resolution. Bundle: HEAD_RENDER (the head technology's inputs). One RGBA part, half, premultiplied, the
   render's colour declared, with a manifest that binds it to the bundle manifest (the master version), the source file's
   sha256 and its render context.
2. **D3, the order's multiply in the video profile** is formed at half resolution by the master's own formula
   (`compositor.derived.HEAD_SHADOW_MULTIPLY` — one function, `slice/order_inputs.shadow_multiply`, which the master's QC
   multiply now uses too) against row 15; **its pixels that can see the hidden back are filled** from those that cannot —
   the back under the order's opaque head layer or the master's opaque front plate, a half pixel seeing it when its
   footprint touches it or lies within the render's pixel filter of it, within the band a visible pixel along the head's
   outline reads; a visible hole deeper inside the head (the mouth seen in profile, a gap in the hair) shows the surface
   the head hides around it and keeps its own value, counted (`order_render.hidden_back`); then it is returned
   to the profile's resolution **bilinearly** (×2, pixel centres aligned, edges held). Without the fill the half
   resolution carries the body's open neck — in deep shadow under the head — onto the visible collar, and
   `SEAM_EXTEND` grows the back under the head's edge from it: a dark line on the seam (§Validation). The still profile
   renders the shadow at full resolution against `BODY_BEAUTY`, as before (the owner's (b) was the order's video).
3. **The render context is a precondition of the order's shadow.** The order's shot file must equal the master's in
   everything that is not the head and changes the body's pixels: every object outside `C_HEAD` / `C_HAIR`, their
   materials, the world, the view layers, the scene's settings except the per-call ones (`conventions.json →
   order_render.render_context`); the per-call settings (resolution, samples, determinism, time stretch, EXR depth and
   codec), the device and Blender must be the denominator's for the shadow and the bundle's for the head. A difference
   stops the order before anything renders and names what differs. Without it a head technology that moved a light, a
   sleeve or a render setting would have its own noise and its own light divided by the master's body — a wrong shadow
   that passes every per-order gate.
4. **D5 row 14, the head layer may be rendered in its screen box** — the box from every render-visible object of
   `C_HEAD` / `C_HAIR` at the instant the frame renders, widened by a margin (2 % of the frame, PROVISIONAL) to whole
   pixels and given to Blender a quarter pixel past each pixel edge (Blender keeps a border as float32 and truncates
   border × size: an edge given exactly as 971/3840 rendered from column 970 — found on SHOT_002 1121). Delivered completed: outside the box colour 0, vectors 0 and the empty depth — what
   a full-frame `L_HEAD` holds wherever the head's alpha is 0 — read from the box's own empty pixels. Refused, never
   guessed: a region other than the one asked for, colour outside it, the head's alpha on a side of the box that is not
   the frame's edge (the box cut it), empty pixels that disagree on the depth or carry motion. The delivered head layer,
   its vectors and depth keep their format: nothing downstream changes.

What does not change: the per-order composite (`slice/composite_order.py`) and its gates, the post-composite blur, the
seam extension, the re-tint, every master plate of contract v5, the still profile.

## Alternatives

- **The master's full-resolution `L_BODY` downsampled as the denominator** — no new plate, but the ratio of a 64-spp
  half-resolution render to a box-filtered full-resolution one carries the half render's whole noise into every pixel of
  the body.
- **The denominator rendered per order** — the 8–11 s per frame (measured here) that (b) exists to save.
- **Nearest (pixel repetition)** — measured 2026-10-29: 16–17 % more error on both lights and 2-px steps on hard shadow
  edges; catmull-rom and lanczos3 between the two.
- **OpenImageIO's resize ('triangle')** — the interpolation measured on 2026-10-29, but in float32 coordinates that drift
  with the width (1.35e-4 at 1920 px); computed in float64 instead (3e-8 from exact).
- **The head layer delivered boxed, with its box** — every consumer of the head layer would learn a new format; the
  completion keeps the contract's layer and costs 0.1–0.3 s.
- **The render context checked by the build (the head technology's adapter) alone** — the adapter's check is where a
  change would be made; the order render is where it would do harm, so it checks before it renders.
- **The render context in the file's own vertex order** — refused the contractor's child files for a ball whose faces
  were stored in another order (`PROP_A`, the same 514 vertices and 530 faces); **in `blend_content_hash`'s canonical
  form alone** — that form sorts a face's vertices and so loses its winding (a flipped face shades differently), its
  smooth flag and its UVs. Kept: canonical vertex order with each face's loop rotated, not sorted (`oriented_faces`).
- **For the seam line: a bilinear return weighted by the back's visibility** (normalized convolution) — measured on the
  three probe frames: it trades the sign, not the size (the pixel next to the head 2–3× lighter than the reference);
  **filling only the half pixels whose footprint touches the hidden back** — the seam criterion −0.027 / −0.015 / −0.034
  (the pixel filter still mixes the next pixel); **filling within twice the filter's reach** — +0.012 / −0.000 / −0.009,
  an overshoot. Kept: the footprint and the filter's reach (+0.002 / −0.001 / −0.005).

## Validation

On the slice's package (`../../slice/measurements/order_render_2026-10-29/summary.json`): the nine frames it carries
(SHOT_001 1001 / 1094 / 1101, SHOT_002 1121 / 1210 / 1217, SHOT_003 1241 / 1286 / 1338), 4K, 64 spp, the M4; two heads —
the default head (the master's own files; the package's own layer and multiply are its reference) and burst 3's child 01
(its full-frame one-call render is its reference). Each variant through the per-order composite onto the package bundle.

- **The per-order composite's gates pass on the decided inputs**: the default head 15/15 compositions (unfilled ≤ 0.0009),
  child 01 on SHOT_002 4/4. Child 01 fails `unfilled` on SHOT_001 and SHOT_003 in every variant, the reference included
  (0.0041 / 0.0046 against 0.002): the contractor's truth head does not fill the default head's silhouette — a property
  of that head, not of this configuration. (Corrected 2026-10-30: such a head IS what an order composites — the gate held every head to the default head's silhouette; `ADR-0002-amendment-2026-10-30-order-gate-own-silhouette.md`.)
- **(a) costs nothing in the picture**: the boxed head layer is the full-frame one within the render tolerance on 18/18
  frames, exactly outside the box; the FINAL with (a) alone is within the render tolerance on 12/12 frames with the seam
  criterion 0.0000 — what a second full-frame render of the reference configuration gives (9/9, 0.0000). No frame cut.
- **(b) costs what the owner chose it for**: the FINAL is not a re-render's equal (0.75–0.88 of the support within the
  render tolerance); the shadow region's error mean 0.01–0.03, p99 0.03–0.10 — coarser grain, softer edges, the hard
  shadow band on SHOT_002 1210's collar the blotchiest. No misalignment (±½ px shifts change the error ≤ 0.3 %), no
  brightness offset (the light the shadow removes agrees within 0.01–0.09 % over the frame).
- **The seam (criterion 3's seam criterion, bound 0.04, against the reference FINAL)**: −0.0052 … +0.0021 on all 12
  frames; the rings 2–4 px outside the head near the seam −0.7 … +1.1 %. Without the hidden-back fill it read
  −0.003 … −0.060, three of nine frames beyond the bound, and the rings −2.5 … −7.4 % — a dark line on the neck, found by
  this validation (Decision 2).
- **Time per frame**: 11.3–16.3 s of render calls (15.3–18.4 s per frame for the whole job in jobs of three frames)
  against 33.5–42.9 s (35.6–41.5) for one full-frame call — the ratio of the means 0.39 (0.43); the denominator
  7.3–11.0 s per frame once per master version. Per order (4 920 frames, ESTIMATE): 15.4–25.1 h of head layers against
  45.8–58.6 h.
- **Refusals exercised on the real files**: the rendered-region rule stopped SHOT_002 1121 when an exact border landed a
  pixel short (Decision 4's quarter pixel); the render-context gate stopped the contractor's child files (the child's tone
  in HERO_SKIN_BODY) before anything rendered.

Images: `archive/reviews/order_render_2026-10-29/` (the reference, the decided FINAL, their difference ×10; the seam at 1×
and 2×; `before_hidden_back_fill/`).

## Implemented (2026-10-29)

`slice/order_render.py` (`context`, `denominator`, `order`; the per-call settings and render context checked before
anything renders; idempotency key, resumable staging, the job's declaration in its manifest), `slice/order_inputs.py`
(`upsample2_bilinear`, `shadow_multiply` — `slice/composite.py`'s master multiply now calls it, bitwise unchanged on
SHOT_001 1094, SHOT_002 1210, SHOT_003 1338 — `fill_hidden_back`, `pixel_rect`, `border_of`, `complete_boxed_head`, the
output directory), `slice/conventions.json → order_render` and `master_contract_version = 6`; tests
`tests/test_order_inputs.py` (CI) and `tests/test_order_render.py` (Blender, the template at 10 %: both configurations end
to end, the denominator's noise cancellation across two sessions, the delivered multiply equal to the declared formula
bit for bit, and the refusals — another light, a face turned over, a box that cuts the head, a denominator of other
settings, another order in the directory — with a reordered mesh passing). The bake-off's estimate recomputed from these
seconds (`bakeoff/stage_cost_estimate.py`: 74–145 Mac hours at R = 3 against the cap of 220).

Not yet: row 15 for every frame of the package — rendered in Stage 3 with the package's frames (≈ 0.7–1.1 h for the 360
frames of the three shots); the order render through `bakeoff/ledger.py` in the bake-off's stage scripts.

## Does not solve

- The hard-light cost of (b): a shadow edge finer than two pixels cannot be carried at half resolution (on the template
  at 10 % a one-pixel contact line: 0.27 → 0.61). The owner chose (b) after the comparison images; §Validation measures
  it on the slice's hard key.
- A head technology that does not render in the master's scene produces its shadow its own way; row 15 serves the ones
  that do.
- The order's money: machine hours have no price yet (`cost-model.md`), and `ORDER_COST_CAP` waits for Phase 9.
- The premise of (b) holds pixel for pixel only as far as the GPU repeats itself. Measured 2026-10-30
  (`slice/measurements/metal_determinism_2026-10-30/summary.json`): Cycles on Metal is not bit-exact across sessions even
  idle — a few pixels per frame differ by about one half step in the multiply — and now and then one pixel takes another
  sample path (0.035 in the multiply). The design's own bounds (means and fractions) hold through it; the reference test's
  per-pixel maximum does not: since 2026-10-30 (owner, (A)) it allows isolated pixels — within 2e-3 everywhere but at
  most a ten-thousandth of the frame with no neighbour off, those within 0.05.
