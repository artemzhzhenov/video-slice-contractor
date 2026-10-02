# ADR-0002 amendment — the gaze as a target point: every head converges its own eyes

## Status

**APPROVED — 2026-10-01 by the owner («утверждаю», on the 2026-09-30 proposal); implemented the same day; merged into
ADR-0002 D8, channel vocabulary v2 (`master_contract_version` unchanged at 5: no pass or plate changes).** Raised on
2026-09-22 (the motion-blur amendment, "Also raised, not decided here") and recorded in PROJECT_STATE as the
gaze-vergence question to settle before the bake-off, because the bake-off drives every candidate with the performance
track. It changes §D8 (the performance track) and the channel vocabulary (CLAUDE.md §9: changing an approved ADR). The
evidence: `slice/measurements/gaze_vergence.py`, results in `slice/measurements/gaze_vergence_2026-09-30/`; the
implementation's own measurement `gaze_aimed.py` (same directory). Implementation: §Implemented.

## What was found

§D8 carries one `gaze_yaw` / `gaze_pitch` pair for both eyes. Three defects follow, measured on the accepted shots
(SHOT_001 v02, SHOT_002 v02, SHOT_003 v06; the default head's eyes 54.6 mm apart):

1. **The pair has no defined angle.** `slice/channel_map.json` v1 says only "−1 to character's right, +1 to character's
   left"; the degrees live in the default head's rig (`build_character.py`: 1 = 30° yaw, 1 = 20° pitch). A head
   technology reading the track cannot know what 0.5 means.
2. **Both eyes turn by the same pair, so they are parallel and cannot converge.** On SHOT_001 1023–1027 the girl looks at
   the ball at 0.26 m (the state map names it: `gaze_target` PROP_A): both eyes on it need 10.8° of vergence; the rig,
   aimed between the eyes since Q27, leaves each eye 5.1–5.7° off it.
3. **The pair is right only for the default head's eye positions.** The same numbers on a head whose eyes sit 15 %
   closer or wider apart miss the ball by up to 4.8° or 6.6° per eye. The same acting would land differently on every
   child — the opposite of invariant 6 (the master owns the performance).

`master-spec.md` already lists a `gaze_target` among the performance fields; §D8 never carried it.

Also measured, and why the slice cannot simply infer the target: the shots record a direction and no distance. The first
surface on the gaze ray is not the target — on SHOT_003 1300–1302 it is the girl's own hand over her face, 8 cm from the
eyes (a surface rule would cross the eyes by 38°), and elsewhere a floor or a wall 1.8–6.0 m away that nobody chose.
Looks toward the lens are not separable either: on SHOT_001 the angle between the gaze and the camera runs continuously
from 0.1° to 10°, with no gap to draw a line through.

## Proposal

**G1. The gaze is a point (§D8).** Per frame the track carries `gaze.target_m` = [x, y, z], the point the character
looks at, in the socket's local frame (the frame of `default_head_rest.obj` and the envelope, §D1), in metres, with
`gaze.source` (below). Every head turns each of its own eyes so that eye's line of sight passes through the point;
vergence and parallax follow from the head's own eye positions. A far look is a far point: at 10 m two eyes are parallel
within 0.16° each. Between frames a head interpolates each eye's rotation, not the point: a saccade from a toy at 26 cm
to the horizon turns the eyes evenly instead of snapping at the end. A head whose eyes cannot turn that far clamps and
reports it per frame (`gaze_clamped`), never silently. A head without 3D eyes (a 2D rig) maps the point through its own
eye positions in the socket frame; the rule is where the eyes look, not how they are drawn.

**G2. `gaze_yaw` / `gaze_pitch` stop driving (channel vocabulary v2).** They stay in the track as readouts: the default
head's gaze direction toward the point, in defined degrees (1 = 30° yaw, 1 = 20° pitch), for QC and state detection
(`check_states`). No head reads them. The track schema gains `gaze`; the vocabulary becomes version 2.

**G3. The master authors the point.** A master's rig carries an animated look-at target, or names one per window in
`editorial.gaze_target`: an object, or `CAMERA` for a look into the lens, which is how a master asks for eye contact.
The export writes the point per frame. The default head aims each eye at it (one aim per eye), so the reference render
follows the rule. The export check asserts that each rendered eye's line of sight passes through the point within a
stated tolerance (`PROVISIONAL`, set by measurement at implementation).

**G4. The slice, without contractor work.** The slice's shots were authored with the pair and record no distance. The
export derives the point by one rule, recorded per frame in `gaze.source`:
- **`NAMED_TARGET`:** the ray from the midpoint between the default head's eyes along their shared direction, where it
  meets the object the state map names for that frame.
- **`FAR`:** otherwise, the point on that ray at 10 m.

The default head's eyes aim at the exported point at render time: our render step, with the delivered animation
untouched. Measured consequences:
- SHOT_001 1023–1027 (`NAMED_TARGET`, PROP_A at 0.258–0.262 m) converge on the ball.
- All other frames of the three shots (`FAR`, 355 frames) stay within 0.16° per eye of what was rendered and accepted.
- None of the package's rendered frames (1001, 1050, 1094, 1101; 1121, 1210, 1215, 1217; 1241, 1286, 1290, 1338) is a
  `NAMED_TARGET` frame, so no render is redone.

## Cost

- **Render:** none. The package's renders stand. The performance tracks change, so the package is re-hashed.
- **Per order:** none. A head reads three numbers instead of two.
- **Track size:** four values per frame.
- **Contractor:** none now. Q50 (the gaze darts in SHOT_002's ¾ hold) is authored with the pair as before; its frames
  carry no named target, so the export derives `FAR` points. The public copy gets the new vocabulary and exporter with
  the next question; the contractor's work does not change.
- **The first real master (Phase 8):** the rig carries a look-at target from the start. This is a requirement for the
  master's TD.

## Alternatives

- **The pair plus a distance channel.** Gives vergence, but the angles are measured from the default head's eyes. At
  26 cm a head whose eyes sit 1 cm elsewhere misses by ~2° (parallax), so the numbers stay head-specific.
- **Angles per eye (four channels).** Exact for the default head and wrong for every other head: the performance
  becomes the default head's property.
- **Keep the pair and aim between the eyes (the slice's workaround).** Each eye 5.1–5.7° off at 26 cm on the default
  head, and up to 6.6° on other spacings. A kids' cartoon looks at toys, hands and faces at arm's length all the time.
- **A point in world or camera space.** Equivalent through the socket transform the track already carries. The socket
  frame is the one a head already works in.

## Does not solve

- **Where the character looks is the master's acting.** A wrong target is an acting defect, not the head's.
- **The slice's `FAR` frames stay parallel**, because the animator recorded no distance. True eye contact at the slice's
  lens distance (1.2 m) needs 1.1° more per eye (1.3° against the 0.16° at 10 m); a master that wants it names `CAMERA`.
- **Lids following the eyes, and eye dynamics beyond the point**, are the head's and the acting's.

## Validation after approval

- **Vocabulary and schema:** `slice/channel_map.json` v2 (the gaze readouts with their degrees, the point's definition);
  `schemas/performance_track.json` gains `gaze`, required from vocabulary v2. Fixtures: a valid track, and invalid ones
  with no point or an unknown source.
- **Export:** `slice/export_shot.py` writes the point by G3 / G4 and the readouts. `slice/check_exports.py` asserts that
  the point is finite, the source is known, and the readouts agree with the point on the default head.
- **Render:** `slice/render_passes.py` aims each eye of the default head at the point. A synthetic test: with a target
  at 0.26 m both eyes' lines of sight pass through it; the parallel pair (the negative control) does not.
- **On the slice:** SHOT_001 re-measured (1023–1027 converge; `FAR` frames unchanged within 0.16°); the three shots
  re-exported, the package re-hashed and verified.
- **Records:** the exit review's S3 row updated (vocabulary v2); ADR-0002 §D8 and `master-spec.md` cite this amendment.

## Implemented (2026-10-01)

- **Vocabulary v2** — `slice/channel_map.json`: `gaze` (the point's frame, the rule every head follows, the four sources,
  `far_m` 10, the slice's migration rule, the readout degrees 30° / 20° and a PROVISIONAL readout tolerance of 0.1°);
  `gaze_yaw` / `gaze_pitch` marked READOUT. `schemas/performance_track.json`: `frames[].gaze = {target_m, source}`,
  required from vocabulary 2 (fixtures: the valid track at v2; invalid — a v2 frame without `gaze`, an unknown source).
  The default head's eye objects are named in `conventions.json → scene_naming.eyes` (pupil axis local −Y; a rig's own
  look-at object `GAZE_TARGET`), and the placeholder template now carries two driven eyes.
- **Export** — `slice/export_shot.py` derives the point per frame (G3 / G4: the rig's look-at, the camera, the named
  object where the default head's gaze ray meets it, else 10 m along the ray) and asserts the rig's eyes obey the
  vocabulary's degrees (measured 0.000° on the three shots); `export_manifest.json → gaze` records the eyes' socket
  positions and the sources. `slice/check_exports.py` checks the point's distance and the readouts against the point
  without Blender.
- **Render** — `slice/render_passes.py --exports <dir>` aims each eye at the exported point (a Damped Track to an aim
  empty keyed per frame, linear between frames, so the shutter's sub-frames follow); `settings.gaze_aim` records
  `TARGET_POINT` with the track's hash, `RIG_LOOK_AT` for a rig that aims itself, `NONE` without the flag (how the
  plates rendered before v2 are rebuilt — `rebuild_from_package.py` passes the exports only when the archived plates were
  aimed). `check_asset.sh` and the skin-tone gate's truth renders pass the exports. The synthetic test
  (`tests/test_slice_exports.py`): with a target 26 cm in front of the template's eyes each aimed eye's line of sight
  passes through it within 0.05°, the parallel pair misses it by more than 3°; the manifest records the aim.
- **The slice** — the three accepted shots re-exported at v2 into their conformant runs: SHOT_001 115 FAR + 5
  NAMED_TARGET (1023–1027, PROP_A at 0.296–0.300 m from the eyes' midpoint), SHOT_002 and SHOT_003 120 FAR each. The aim
  measured on the delivered files (`gaze_aimed.py`): every eye's miss of its point 0.000°; the eyes turn by at most
  **0.156°** on every FAR frame and by **5.68°** on SHOT_001's ball frames — as proposed. The plates were not re-rendered
  (`gaze_aim` NONE recorded; no packaged frame is a named-target frame); the exports re-copied into the HEAD_RENDER
  bundles (`split_bundles.py --refresh-plus-files`), the package re-made and verified with its offline part
  (`package_hash` 5a825a0e, 585 files; `package_add_shot.py` gained `--skin-tone` so the contract-v5 gate records stay
  in the package on a replace).
- **Records** — ADR-0002 header and D8; `master-spec.md`; the exit review's S3 (v2); `slice/README.md`.
- **Not done, by design** — the contractor's copy (the new vocabulary and exporter go out with the next question; Q50
  is authored with the pair as before, its frames FAR); eye contact on the slice (a master names `CAMERA`); the first
  real master's rig carries a look-at from the start (a requirement for its TD).
