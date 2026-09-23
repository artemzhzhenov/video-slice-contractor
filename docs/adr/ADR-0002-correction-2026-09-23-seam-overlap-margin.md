# ADR-0002 correction — the seam overlap margin (D1) rests on a measurement error

## Status

**APPROVED by the owner — 2026-09-23, and merged into ADR-0002 the same day** (D1's overlap-margin
bullet and the Status line). It corrects A1 of the amendment of 2026-09-22 (`ADR-0002-amendment-2026-09-22-motion-blur-after-composite.md`), which the
owner approved on my evidence. The motion-blur half of that amendment (A2, A3) is unaffected and
stands. Escalation (CLAUDE.md §9): changing an approved ADR.

## What happened

D1 gained an "overlap margin" rule: head geometry continuing below the socket boundary curve must
lie at least 2 mm inside the body neck on every frame. The evidence was a measurement of the
contractor's v03 head: a 16 mm band below the curve, sitting between 0 and 6.7 mm *outside* the
body skin, whose removal lifted the calm-frame precomp reproduction from 0.954 to 0.971.

That band does not exist. The measurement read the socket curve as the vertices whose
`SOCKET_BOUNDARY` weight exceeds 0.5. **The weight in that group is the ring order** — `i/N`;
`export_shot.py` refuses non-distinct weights precisely because the order defines the polyline. So
the read kept one contiguous half-arc: 21 of 42 vertices, spanning z 1.1972–1.2108 while the real
curve runs 1.1813–1.2108. Ordinary head skin above the low part of the curve then looks like a band
hanging below it.

Measured after the fix, on the delivered SHOT_001 v01:

| | |
|---|---|
| head vertices below the curve | **0** |
| body vertices above the curve | **0** |
| head ring to body ring distance | **0.000 mm** |

The head and the body both end exactly at the curve and meet vertex to vertex. There is nothing to
tuck, and nothing was overlapping.

The rule as written is also unsatisfiable on such a head: 21 of the 45 phantom band vertices *were*
the welded ring itself, and they cannot move 2 mm inside without breaking `rest_gap = 0`, which
`check_exports` enforces. Either the seam or that gate — which is what the contractor hit.

Found by the contractor on 2026-09-23 while doing the v04 work order, in 1.2 h of his 3 h cap. He
was right to stop and say so.

## Why the controls did not catch it

`check_seam_margin.py` shipped with a positive and a negative control (a band outside the neck must
fail, the same band tucked in must pass). Both were built with the same half-ring read, on the
placeholder — whose socket ring is **flat**, so the two reads agree there. The controls tested the
gate's arithmetic, not its reading of the asset. Two further asset-specific assumptions hid in the
same place: the fixture built its band in the posed frame while the gate classifies in the rest
pose, and the region of interest was a fixed 0.08 m taken from the real neck, which excludes
everything on a placeholder whose ring radius is 0.099 m.

## Correction (approved and merged)

1. **D1's overlap-margin bullet becomes conditional and loses its false premise.** Proposed text:

   > **Overlap margin** (amendment 2026-09-22, corrected 2026-09-23). A head technology may
   > continue its shell below the boundary curve to close cracks from inside; the default head does
   > not, and neither is required to. **Where such geometry exists**, it lies inside the body neck
   > on every frame of every shot: signed distance ≤ −M, ramped from 0 at the curve to M at depth R
   > below it, so that the body wins the depth test below the curve at every sample. `PROVISIONAL`:
   > M = 2 mm, R = 2 mm — not yet calibrated against any head that has such a band. A head that
   > ends at the curve passes vacuously, and the gate records that it measured nothing.

2. **The evidence paragraph in the 2026-09-22 amendment is struck** — the 16 mm band, the 0–6.7 mm
   outside, and the calm-frame improvement attributed to tucking it. The seam line at the laugh peak
   is explained by the composite order alone, which is what A2 fixes and what the 100 % run confirms.

3. **No v04 of the head is required for this.** The rule binds head technologies in the bake-off,
   where a candidate that does deliver an overlap band must keep it inside; on our default head it
   is vacuous.

4. The gate keeps its place in `check_asset.sh` (step 1c) with the curve read by membership, the
   region of interest measured from the curve's own radius, and a regression test that makes the
   ring dip before checking that nothing is invented.

## What this does not change

A2 and A3 of the 2026-09-22 amendment — motion blur applied after compositing, per-layer vectors,
the sharp-domain precomp gate and the blur-fidelity criterion — rest on render measurements that
never used the socket curve. They were re-confirmed at 100 % on 2026-09-23, after the ring bug was
known: composite gate 0.950 at the laugh peak against 0.843 with blurred layers, blur fidelity
PASS on two discriminating frames.

## The lesson worth keeping

A gate is two things: arithmetic, and a reading of the asset. Controls that are built from the same
reading test only the arithmetic. Any future gate that interprets an asset convention states where
that convention is defined, and its controls vary the asset in the dimension the convention lives
in — here, a ring that dips.
