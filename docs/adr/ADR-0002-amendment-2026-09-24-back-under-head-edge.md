# ADR-0002 amendment — what lies under the head's lower edge (the neck-seam line)

## Status

**APPROVED by the owner — 2026-09-25, and merged into ADR-0002 the same day** (D5's composite
formula, §Validation criterion 3, the Status line; `master_contract_version` 2 → 3). Proposed
2026-09-24 (CLAUDE.md §9: changing an approved ADR). Implemented the same day in
`slice/seam_extend.py`, called by `slice/composite.py` (criterion 3, the default head) and
`slice/composite_order.py` (every order); parameters in `slice/conventions.json →
compositor.seam_extend` and `precomp_reproduction_test.pass_rule`. The trial measurements below
were made with the scripts in `slice/measurements/` before the implementation existed; the
implementation's own numbers are in §Implemented.

## What was found

Accepting the contractor's SHOT_002 v01 (burst 2, 2026-09-24), `check_asset.sh` failed at the
composite step on the three-quarter frames at both scales (criterion 3, inside-band fraction 0.894
at 25 % and 0.896 at 100 % on frame 1121, against a floor of 0.9). Split by kind, the failing band
pixels are two different things:

1. **A thin dark line along the neck seam** in the layered composite, absent from the full render.
   The head and the body meet vertex to vertex at the socket ring (what D1 allows since the
   2026-09-23 correction), so nothing of the body lies behind the head's lower edge: the body
   plate under the head holdout shows the **open neck of the body** — the dark interior of the
   torso. The head layer's edge pixels have partial coverage, and `HEAD over BACK` lets that
   interior through in proportion to 1 − α. Seen at 100 % in
   `~/Downloads/SHOT_002_v01_review/seam_SHOT_002_f1121_100pct.png` (not in the repository — the
   repository keeps no images).
2. **Zero-mean channel noise along the silhouette against the wall** under SHOT_002's hard
   coloured key and rim at 64 spp: about 7–8 % of the non-seam band beyond 5e-2 in some channel,
   with a signed mean of 0.000. The known edge residual of two separately filtered layers,
   magnified by contrast.

Neither alone fails the gate — at 25 % on frame 1121 the band is 0.926 without the seam failures
and 0.968 without the silhouette noise. The line is the finding; the noise only pushed the sum
over the floor.

**The line is not new.** The contractor's SHOT_001 v01, accepted on 2026-09-21, carries it more
strongly, and the gate passed there because it counts the whole band: the seam is about 5 % of the
band (frame 1090 at 25 %: 305 of 6082 px) yet held 280 of the frame's 305 failing pixels, while the
rest of the edge under neutral light was clean. An aggregate hid a localised systematic error —
the same lesson as the 2026-09-23 correction, one level up.

**It is on every order, not only the default head.** The per-order composite puts the order's
head layer over the same plate (`BODY_BEAUTY × SHADOW_MULTIPLY_ORDER`), so any head's edge at the
seam mixes with the neck interior wherever the neck is in view and not hidden by a collar.

**It is not the contractor's.** The character follows the contract; what the plate holds under the
head's edge is an interface question, ours.

### Measured on the seam band (head and body material both present in the 2-px band)

Signed mean = composite − full render (a systematic darkening is a line; noise averages out).

| Shot, scale | Frame | Seam px | Signed mean | Median error | Darker by > 0.05 | BACK − full |
|---|---|---|---|---|---|---|
| SHOT_001 v01, 25 % | 1001 / 1090 / 1100 | 306 / 305 / 304 | −0.205 / −0.224 / −0.186 | 0.241 / 0.246 / 0.175 | 85 / 89 / 77 % | — |
| SHOT_001 v01, 100 % | 1001 / 1090 / 1100 | 1199 / 1210 / 1200 | −0.210 / −0.225 / −0.184 | 0.244 / 0.246 / 0.174 | 89 / 91 / 74 % | −0.78 / −0.71 / −0.62 |
| SHOT_002 v01, 25 % | 1121 / 1209 / 1210 | 281 / — / — | −0.153 / −0.091 / −0.086 | 0.160 / 0.101 / 0.081 | 77 % (1121) | −0.68 (1121) |
| SHOT_002 v01, 100 % | 1121 / 1144 / 1164 / 1185 / 1209 / 1210 / 1228 | 1097–1430 | −0.154 / −0.140 / −0.098 / −0.114 / −0.092 / −0.084 / −0.107 | 0.079–0.154 | 48–75 % | — |

Every one of the 16 measured frames of both shots is darker on the seam.

## Proposal

**A1. The composite extends the back under the head's edge at the seam, before the over.**

    FINAL = FRONT over (HEAD over SEAM_EXTEND(BACK))

`SEAM_EXTEND` replaces the back plate only inside the head holdout and only within the seam zone,
with the body's own surface grown from outside the holdout (edge extend, N px). Outside the seam
zone the plate is untouched: behind the silhouette against the environment it is already right, and
an unrestricted extend was measured worse there (below). The same operation runs in the
precomp-reproduction test with the default head (criterion 3) and in the per-order composite with
the order's head, so the test keeps testing what production does. It is deterministic, costs a band
of a few thousand pixels per 4K frame, and needs no re-render of the master, no geometry change and
no contractor work.

- **Seam zone:** the pixels within **6 px** of the projected socket boundary rings — the head ring
  carried rigidly by the socket and the body ring as exported per frame (`socket_boundary.json`
  through `socket.json` and `camera.json`, centre samples, the profile's intrinsics scaled to the
  render), **only the segments on the ring's visible side**: a ring point counts when its outward
  radial normal (from the ring's centroid, in the ring's plane) faces the camera, within a grazing
  tolerance at the neck's silhouette — the back arc, hidden behind the neck and seen only through
  the open neck in the body plate, adds nothing. Geometry, not the depth pass, so no depth
  convention is assumed. The trial approximated the zone by the material cryptomatte (head and body
  material both present in the 2-px band, dilated by 3 px — about 5 px from the ring); the
  implementation reads the rings, and its tests make the ring dip (the 2026-09-23 lesson) and hide
  the back arc. **And only where the seam is closed**: the head ring's point (carried by the socket)
  and the body ring's corresponding point within 0.1 mm. Where the rings are apart the master's own
  seam is open, the full render shows that gap, and painting over it would hide a master defect —
  those segments are left alone and every frame reports them (`OPEN_SEAM`).
- **N = 6 rings of growth**, from the pixels outside the head only — the body the edge actually
  borders; the plate under the head outside the zone is neither a source nor changed. Both numbers
  are **render pixels at every scale**: the edge that mixes with the back is the reconstruction
  filter's width, a pixel quantity. `PROVISIONAL` (the trial used 4 rings into a ~5-px zone; 6 covers
  the 2-px band plus projection tolerance).

**A2. Criterion 3 gains a seam criterion.** Besides the aggregate inside-band floor, the signed mean
error over the seam's **mixed pixels** — the boundary band inside the seam zone where the head's
coverage is fractional (0.01–0.99), the only pixels where `HEAD over BACK` lets the back through —
must lie within **±0.04** on every tested frame. `PROVISIONAL` — basis: −0.084 … −0.225 without A1
on all 16 frames above, −0.026 … +0.006 with it (the trial's material-cryptomatte seam band selected
the same mixed pixels). A systematic line then fails on its own instead of hiding in the band. The
whole 5-px band inside the zone would not do: its fully covered and fully uncovered pixels carry no
error and dilute the line about threefold (measured on the implementation: SHOT_002 1210 at 25 %,
−0.040 over the band against −0.097 over its mixed pixels).

## Trial (not the pipeline)

`slice/measurements/precomp_seam_edge_extend_trial.py`, N = 4, the delivered plates:

| Shot, scale, frame | Criterion 3 band | Seam signed mean | Seam median error | Non-seam band |
|---|---|---|---|---|
| SHOT_001 100 % 1001 | 0.956 → **0.975** | −0.210 → **+0.002** | 0.244 → 0.046 | 0.996 → 0.995 |
| SHOT_001 100 % 1090 | 0.950 → **0.969** | −0.225 → **−0.003** | 0.246 → 0.054 | 0.996 → 0.995 |
| SHOT_001 100 % 1100 | 0.955 → **0.967** | −0.184 → **+0.006** | 0.174 → 0.056 | 0.996 → 0.994 |
| SHOT_001 25 % 1090 | 0.950 → 0.963 | −0.224 → −0.026 | 0.246 → 0.076 | 0.996 → 0.994 |
| SHOT_002 25 % 1121 | 0.894 → **0.905** | −0.153 → **+0.005** | 0.160 → 0.049 | 0.923 → 0.921 |
| SHOT_002 100 % 1121 | 0.896 → **0.911** | −0.154 → **+0.001** | 0.154 → 0.039 | 0.925 → 0.923 |
| SHOT_002 100 % 1144 | 0.898 → **0.910** | −0.140 → **−0.000** | 0.142 → 0.037 | 0.923 → 0.921 |
| SHOT_002 100 % 1164 | 0.906 → 0.917 | −0.098 → +0.001 | 0.094 → 0.035 | 0.928 → 0.927 |
| SHOT_002 100 % 1185 | 0.908 → 0.917 | −0.114 → +0.001 | 0.118 → 0.039 | 0.931 → 0.928 |
| SHOT_002 100 % 1209 | 0.904 → 0.910 | −0.092 → +0.001 | 0.086 → 0.044 | 0.930 → 0.927 |
| SHOT_002 100 % 1210 | 0.901 → 0.908 | −0.084 → +0.000 | 0.079 → 0.042 | 0.931 → 0.927 |
| SHOT_002 100 % 1228 | 0.908 → 0.918 | −0.107 → −0.002 | 0.102 → 0.039 | 0.932 → 0.930 |

The darkening disappears on every frame; the rest of the band moves by at most 0.004; outside the
band nothing changes (0.9999 both ways). An **unrestricted** extend along the whole holdout edge
was measured first and degraded the silhouette band (SHOT_002 1121 at 25 %: 0.923 → 0.877) — hence
the seam zone.

## Alternatives

- **A neck "stump" in the body, continuing up inside the head.** Rejected: in the shadowed body
  plate it sits inside the default head's shadow and renders about as dark as the open neck, so it
  does not fix the default-head test; it also binds every head technology to cover it, and it is a
  character change while the character is frozen in burst 2.
- **Require head technologies to overlap below the ring (alpha 1 at the ring).** Rejected: D1 made
  the overlap optional on 2026-09-23 because the default head meets the body vertex to vertex; making
  it mandatory pushes a master-side defect onto every bake-off candidate.
- **Loosen the criterion-3 floor.** Rejected: it would pass the line, which is the defect.
- **Do nothing.** A dark line on the neck of every personalized cartoon wherever the neck is in view.

## Does not solve

- **The silhouette noise under strong coloured light at 64 spp.** With A1, SHOT_002 passes the
  aggregate floor at 0.908–0.918 — narrowly. The floor stays; it is calibrated at the conformant
  sample count (its own `PROVISIONAL` note), not loosened for a smoke setting.
- **The post-composite blur on fast close-up motion** (amendment 2026-09-22): on SHOT_002 1209 the
  head travels 77 px within the shutter and the blur's head error is 0.057 against 0.02; the
  blur-fidelity gate also misjudges a frame where only the eyelids move (1185). A separate
  investigation, reported before SHOT_003's acceptance.

## Cost

Per order: one edge extend over the seam zone per frame — negligible beside the post-composite blur
(15–36 s per 4K frame). Master: none. Contractor: none.

## Validation after approval

`SEAM_EXTEND` in `slice/composite.py` (criterion 3) and `slice/composite_order.py` (per order), the
seam zone from the ring projection, recorded in the composite manifests. Tests: a synthetic seam
with a dark interior behind the head's edge fails A2 without the extend and passes with it; a
silhouette-only band is untouched by it; a ring that dips is followed. Then `check_asset.sh` at 25 %
and 100 % on SHOT_001 and SHOT_002 (v02): A2 within ±0.04 on every frame, criterion 3 passing, and
a 100 % crop of the neck with no line.

## Implemented (2026-09-25)

`slice/seam_extend.py` (numpy only), called by `slice/composite.py` (criterion 3, the default head)
and `slice/composite_order.py` (every order; the parameters are part of its idempotency key).
`tests/test_seam_extend.py` in CI: an open neck behind a filtered head edge fails A2 without the
extension and passes with it; the head's side against a wall is untouched bit for bit; a zone read
from a flat ring misses a ring that dips; the hidden back arc adds nothing; the ring projection is
`camera_model`'s pinhole. Two findings of the implementation itself, folded in before the numbers
below: the zone takes only the ring's visible side (the closed ring's back arc projects near the
head's back silhouette), and A2 is taken over the seam's mixed pixels (over the whole band inside
the zone the line was diluted to the threshold). A third came from the test suite: on the template's
placeholder — a rigid, unskinned body under a head that turns — the rings come apart by millimetres
and the full render shows the open neck through the gap (frame 1102: the seam's background reads
0.18 where the lit neck is 0.46); the extension painted over it and A2 failed at +0.17. The
contractor's asset keeps every ring point within 0.000 mm on all 240 frames of both shots, so the
extension now acts only on welded segments and reports open ones; the placeholder then passes as it
did before the amendment, and the numbers below are unchanged.

Precomp test on the delivered plates (the same renders as the trial; the "without" column is what
`composite.py` now reports beside every frame, never gated):

| Shot, scale | Frames | Criterion 3 band | A2 seam signed mean | Without `SEAM_EXTEND` |
|---|---|---|---|---|
| SHOT_001 v01, 25 % | 1001 / 1090 / 1100 | 0.971 / 0.963 / 0.962 | −0.005 / −0.025 / +0.000 | −0.175 / −0.189 / −0.153 |
| SHOT_001 v01, 100 % | 1001 / 1090 / 1100 | 0.974 / 0.969 / 0.967 | +0.002 / −0.002 / +0.005 | −0.177 / −0.192 / −0.162 |
| SHOT_002 v01, 25 % | 1121 / 1209 / 1210 | 0.906 / 0.916 / 0.917 | +0.005 / −0.005 / +0.001 | −0.131 / −0.098 / −0.097 |
| SHOT_002 v01, 100 % | 1121, 1144, 1164, 1185, 1209, 1210, 1228 | 0.909 – 0.919 | −0.002 … +0.001 | −0.104 … −0.130 |

Every frame of both shots passes criterion 3 and A2; without the extension every frame would fail
A2 by 2.4× to 4.8× its bound. SHOT_002's three-quarter frames (1121, 1144), which failed criterion 3
at 0.894–0.898, pass at 0.906–0.910. Visual at 100 %:
`~/Downloads/SHOT_002_v01_review/seam_fix_SHOT_002_f1121_100pct.png` — the line along the neck in the
old composite, none in the new one. Numbers: `slice/measurements/seam_extend_2026-09-25.json`.

Full `check_asset.sh` on fresh renders: **SHOT_001 v01 — `ASSET_CHECK_OK` at 25 % and at 100 %**
(still included, blur fidelity with two discriminating frames). **SHOT_002 v01** passes the composite
at both scales and then fails on frame 1209 — blur fidelity at 25 %, the round-trip against the
blurred matte at 100 % (identical to the diagnostic run before this amendment; the centre sample is
exact). That is the post-composite blur on fast close-up motion, a separate open item, not the seam.
