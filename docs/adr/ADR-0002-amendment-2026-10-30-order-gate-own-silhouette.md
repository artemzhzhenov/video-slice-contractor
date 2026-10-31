# ADR-0002 amendment — the per-order composite holds a head to its own silhouette

## Status

**APPROVED — 2026-10-30, by the owner** («Предлагаю голову мерить по заказу по собственным силуэтам из масок … силуэт
головы по умолчанию требует только у шва»), on the proposal raised the same day when the bake-off's first FaceBuilder run
met the gate. Merged into ADR-0002 (Status). The contract version is unchanged: no plate, part or delivered format
changes; the per-order composite gains one required input and its gate one reference.

## What was wrong

The per-order composite's `unfilled` gate (`slice/conventions.json → compositor.per_order.gate`) counted the pixels of
the DEFAULT head's silhouette (`HEAD_HOLDOUT`) where the order's head layer is transparent, at most 0.2 %. Every head with
another silhouette fails it whatever its quality: the bake-off's FaceBuilder run on subject_01 (narrower at the jaw — a
one-photo fit — and with curly class hair far wider than the default bob) read 0.040 unfilled and 29 % beyond the default
silhouette (2026-10-30). Behind those pixels the composite is right: the body plate (`L_BODY`, the head excluded) shows
what is behind the head. The 2026-10-29 note that child 01's truth head fails this gate "as a property of that head, which
no order composites" was wrong for the same reason: a head unlike the default one is what an order composites.

## The decision

- **The head layer is held to its own head's silhouette.** `slice/composite_order.py compose --head-silhouette` is
  required: `default-head` when the order's head is the default head (its silhouette IS `HEAD_HOLDOUT`), or a directory
  of `head_silhouette.####.exr` — the order head's coverage as `L_HEAD` sees it (every `C_HEAD` and `C_HAIR` mesh nearer
  than `C_BODY` and `C_ENV`; the hand does not cut the head layer), written by `bakeoff/metrics/extract_geometry.py
  mattes`. `unfilled_fraction` counts that silhouette's pixels where the head layer's alpha < 0.5 — holes, read without
  the silhouette's contour band of `own_silhouette_edge_px` = 1 (8-neighbour): a geometric contour and a filtered
  render's differ by up to a pixel.
- **The default head's silhouette is required at the seam only.** `seam_unfilled_fraction` counts the default
  silhouette's pixels inside the seam zone (`compositor.seam_extend`) where the head layer is transparent — there the body
  plate shows the open neck — read without the default silhouette's contour band of `seam_edge_px` = 1: another head's
  neck contour may lie a pixel inside the default one's at the zone's ends (FaceBuilder on SHOT_003 1241: 34 of 1354 seam
  pixels at 0 px, none at 1 px; the body plate under them not dark — no open neck), a gap is still a gap. Its limit is the
  unfilled gate's own, 0.002, `PROVISIONAL`.
- The default silhouette beyond the zone is reported, never gated (`default_silhouette_unfilled_fraction`,
  `beyond_default_silhouette_fraction`).

The pure computation is `slice/order_inputs.head_fill` (CI-tested: a narrower head that fills itself passes; a hole inside
its own silhouette fails; at the seam the default silhouette still binds and a gap there fails; a one-pixel contour
difference is not a hole, in the silhouette or at the seam).

## Measured

- The geometric silhouette against `HEAD_HOLDOUT` on the default head, the package's nine video frames: IoU
  0.9989–0.9996 (`archive/runs/stage_scripts_2026-10-30/silhouette_check`).
- The default head's own layer against its geometric silhouette: 0.0004–0.0011 unfilled without the contour band — the
  reason for `own_silhouette_edge_px`.

## Does not change

The seam extension (it still replaces the back only inside `HEAD_HOLDOUT` within the seam zone — every head meets the same
ring, D1), the multiply gate, the formula, the delivered layers. What a head technology must deliver is unchanged; the
silhouette input is made by the order path from the order's own shot file.
