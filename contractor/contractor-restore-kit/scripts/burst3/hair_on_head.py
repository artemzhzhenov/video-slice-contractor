"""hair_on_head.py — the hair of a head: bob + strands (+ the cheek strand of the default head), or a child's hair
class (short_straight / long_straight, bangs or not; curly_voluminous) — built from the HEAD alone (Q55, Q61).

Inputs: the head shell's vertices and faces (HERO_HEAD — the master head's topology, as every child and the owner's
FaceBuilder variant have), the eye centres, the centre of the SOCKET_BOUNDARY ring, the collar height (long hair stays
above it), the brow band on the skin (derived from the head), the hair parameters (a subject json's "hair" + "seed", or
none = the default head's v04.1 hair) and the HERO_HAIR material. No MakeHuman human or helper is needed: the hairdo is
fitted to the head shell (its skull extents above the eyes, the hairline, the brow band) — never to a scalp helper.

    In a build:   hair = build_hair(co, hused, head_faces, eye_c, ring_c, collar_z, brow_band, subj, mats, fail)
                  (build_character.py, step 11 — v04.1 and the children bit for bit as before the move)
    On a file:    blender -b head.blend --python-exit-code 2 -P hair_on_head.py -- --out out.blend [--subject s.json]
                  [--collar-z Z]  — takes HERO_HEAD, HERO_EYE_L/R, the SOCKET_BOUNDARY group, the rig's shoulder_l (= MakeHuman's
                  clavicle.L; collar height — or --collar-z) from the file, replaces HERO_HAIR (in C_HAIR, child of SOCKET_HEAD placed
                  like HERO_HEAD, shadow-caster-only like the build), saves a copy.
Deterministic: the curls draw from random.Random(seed)."""
import argparse
import json
import math
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

BROW_ABOVE_EYE_M = 0.017
BROW_TOP_M = 0.032
BROW_X_MIN_M = 0.012
BROW_X_MAX_M = 0.056
HAIR_THICKNESS_M = 0.018
STRAND_WIDTH_M = 0.011
STRAND_THICK_M = 0.006
STRAND_LIFT_M = 0.001
STRAND_DROP_LATITUDE_DEG = 105.0
STRAND_COUNT_SIDES_BACK = 44
STRAND_COUNT_BANGS = 14
HAIR_BOB_BELOW_EYES_M = 0.035
HAIR_BANG_ABOVE_EYES_M = 0.062
CHEEK_STRANDS = [(-44.0, None, 1.0), (-36.0, None, 0.75)]   # v04.1: the root starts behind the temple,
CHEEK_RINGS = 14
CHEEK_WIDTH_M = 0.0075
CHEEK_THICK_M = 0.0035
CHEEK_START_ABOVE_EYE_M = 0.024          # starts just below the brow, at the temple
CHEEK_END_BELOW_EYE_M = 0.042            # ends on the cheek, ~9 mm above the mouth corner level
CHEEK_SWEEP_DEG = 86.0                   # how far forward around the head the strand sweeps
CHEEK_EYE_CLEAR_M = 0.024                # ≥ 5 mm from the eyeball surface (radius ≈ 15.5 mm + strand)
CHEEK_BROW_CLEAR_M = 0.009               # centre line to the brow band; the strand's own half-width adds the rest
CHEEK_ROOT_FRACTION = 0.22               # first fifth of the strand: the root, inside the side hair
CHEEK_ROOT_DEPTH_M = 0.0                 # v04.1: no sinking — the root lies on the skin like the rest of
CHEEK_SINK = 0.55                        # the strand's own half-thickness only partly lifts it off the skin
CHEEK_LIFT_M = 0.0004                    # gap from the skin at the strand's surface
HAIR_SIDE_FRONT_LIMIT_DEG = -4.0     # side strands start behind the temple: nothing hangs beside the eyes
HAIR_CENTRE_BACK_M = 0.004
HAIR_HAIRLINE_ABOVE_EYES_M = 0.058
HAIR_NAPE_ABOVE_RING_M = 0.07
SHORT_SIDE_END_ABOVE_EYES_M = -0.012     # short_straight: sides end at the ear lobes
SHORT_NAPE_ABOVE_RING_M = 0.095
LONG_SIDE_ABOVE_COLLAR_M = 0.046         # long_straight: side strands end ~1 cm above the dress's side neckline
LONG_NAPE_ABOVE_COLLAR_M = 0.052 
BANGS_ON_FOREHEAD_ABOVE_EYES_M = 0.036   # bangs end just above the brows (brow top ≈ eyes + 32 mm)
CURL_VOLUME_M = (0.030, 0.034, 0.040)      # cloud beyond the skull-fitted helmet: sides, front/back, top
CURL_CLOUD_BACK_M = 0.008
CURL_CLOUD_UP_M = 0.010
CURL_HAIRLINE_ABOVE_EYES_M = 0.054
CURL_BANG_ABOVE_EYES_M = BANGS_ON_FOREHEAD_ABOVE_EYES_M + 0.004   # curly bangs (Q69): on the forehead, 4 mm higher than straight ones — a curl is thicker
CURL_TEMPLE_ABOVE_EYES_M = 0.032
CURL_NAPE_ABOVE_RING_M = 0.070
CURL_EYE_CLEAR_M = 0.040
CURL_SAMPLES = 1500
CURL_LENGTH_M = (0.012, 0.020)
CURL_HELIX_R_M = (0.0035, 0.0055)
CURL_TUBE_R_M = (0.0013, 0.0019)
CURL_TURNS = (2.0, 3.0)
CURL_RINGS_PER_TURN = 8
CURL_SIDES = 5
CURL_ROOT_DEPTH_M = 0.006
DRESS_COLLAR_ABOVE_CLAVICLE_M = 0.045
STRAND_RINGS, STRAND_SIDES = 9, 8
CURL_CLOUD_U, CURL_CLOUD_V = 72, 44


def _fail(msg):
    print("HAIR_ON_HEAD_ERROR " + msg)
    raise SystemExit(2)


def brow_band_of(co, hused, eye_c):
    """Head-shell vertices of the brow band (same rule as build_character.py's brows)."""
    z_eye = (eye_c["L"].z + eye_c["R"].z) / 2
    head_c = sum((co[i] for i in hused), Vector()) / len(hused)
    return [i for i in hused if z_eye + BROW_ABOVE_EYE_M < co[i].z < z_eye + BROW_TOP_M and co[i].y < head_c.y - 0.01
            and BROW_X_MIN_M < abs(co[i].x) < BROW_X_MAX_M]


def build_hair(co, hused, head_faces, eye_c, ring_c, collar_z, brow_band, subj, mats, fail=_fail):
    """HERO_HAIR (new object, not linked): co — vertex positions (head shell indices in hused, faces in head_faces index
    the same array), eye_c {"L", "R"}, ring_c, collar_z — Vectors / float in the head's build frame."""
    # ---- 11. hair: solid bob — an ellipsoid helmet fitted to the skull, cut at the hairline ----
    z_eye = (eye_c["L"].z + eye_c["R"].z) / 2
    head_c = sum((co[i] for i in hused), Vector()) / len(hused)
    skull = [co[i] for i in hused if co[i].z > z_eye]
    lo = Vector((min(p.x for p in skull), min(p.y for p in skull), z_eye))
    hi = Vector((max(p.x for p in skull), max(p.y for p in skull), max(p.z for p in skull)))
    centre = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2 + HAIR_CENTRE_BACK_M, (lo.z + hi.z) / 2))
    radii = Vector(((hi.x - lo.x) / 2 + HAIR_THICKNESS_M, (hi.y - lo.y) / 2 + HAIR_THICKNESS_M, (hi.z - lo.z) / 2 + HAIR_THICKNESS_M * 1.4))
    def hairline(pt):
        if pt.y < centre.y - 0.02:                        # front: above the forehead hairline
            return pt.z > z_eye + HAIR_HAIRLINE_ABOVE_EYES_M
        return pt.z > ring_c.z + HAIR_NAPE_ABOVE_RING_M    # sides and back: bob down to the nape
    # Two ellipsoid layers (outer, inner) on a u×v grid, cut by the hairline, joined by rim quads.
    # Built explicitly (no bmesh solidify: its output order depends on pointer hashing and is not
    # reproducible between runs — found on the content hash, 2026-09-16).
    U, V = 48, 32
    def ell(u, v, rad):
        th, ph = 2 * math.pi * u / U, math.pi * v / V
        return Vector((centre.x + rad.x * math.sin(ph) * math.cos(th), centre.y + rad.y * math.sin(ph) * math.sin(th), centre.z + rad.z * math.cos(ph)))
    inner = radii - Vector((HAIR_THICKNESS_M, HAIR_THICKNESS_M, HAIR_THICKNESS_M))
    keep = {(u, v) for u in range(U) for v in range(1, V) if hairline(ell(u, v, radii))}
    hverts, hidx = [], {}
    def vid(u, v, layer):
        key = (u % U, v, layer)
        if key not in hidx:
            hidx[key] = len(hverts)
            hverts.append(ell(key[0], v, radii if layer == 0 else inner))
        return hidx[key]
    hfaces = []
    top = [len(hverts)]; hverts.append(ell(0, 0, radii)); top.append(len(hverts)); hverts.append(ell(0, 0, inner))
    for u in range(U):                                    # top caps (triangle fans)
        hfaces.append([top[0], vid(u + 1, 1, 0), vid(u, 1, 0)])
        hfaces.append([top[1], vid(u, 1, 1), vid(u + 1, 1, 1)])
    edge_use = {}
    def quad(a, b, c, d):
        hfaces.append([a, b, c, d])
    for u in range(U):
        for v in range(1, V - 1):
            cell = [(u, v), ((u + 1) % U, v), ((u + 1) % U, v + 1), (u, v + 1)]
            if all(c in keep for c in cell):
                quad(vid(u, v, 0), vid(u + 1, v, 0), vid(u + 1, v + 1, 0), vid(u, v + 1, 0))
                quad(vid(u, v + 1, 1), vid(u + 1, v + 1, 1), vid(u + 1, v, 1), vid(u, v, 1))
                for a, b in ((cell[0], cell[1]), (cell[1], cell[2]), (cell[2], cell[3]), (cell[3], cell[0])):
                    edge_use[(a, b)] = edge_use.get((a, b), 0) + 1
    for (a, b), n in sorted(edge_use.items()):            # rim: boundary edges of the outer layer
        if (b, a) in edge_use:
            continue
        quad(vid(a[0], a[1], 0), vid(a[0], a[1], 1), vid(b[0], b[1], 1), vid(b[0], b[1], 0))
    # rim quads must not exist where the neighbour cell across the edge is kept: edge_use is
    # counted per directed edge, so an interior edge appears in both directions and is skipped.
    # ---- 11b. strands (Q20): tapered tubes lying on the helmet, explicit geometry, rigid ---------
    # Every strand runs down a meridian of the helmet ellipsoid from a start latitude to an end
    # height, hugging the surface (offset = its own thickness). Elliptic cross-section, wide along
    # the surface, thin outward, tapering to the tip. Azimuth 0 = +X (character's left), −90° = front.
    def ell_pt(th, ph, rad):
        return Vector((centre.x + rad.x * math.sin(ph) * math.cos(th), centre.y + rad.y * math.sin(ph) * math.sin(th), centre.z + rad.z * math.cos(ph)))
    def ell_normal(th, ph):
        p = ell_pt(th, ph, radii) - centre
        n = Vector((p.x / radii.x ** 2, p.y / radii.y ** 2, p.z / radii.z ** 2))
        return n.normalized()
    def strand(th0, ph0, z_end, width, thick, drift=0.0, rings=STRAND_RINGS, sides=STRAND_SIDES):
        # Down the meridian to STRAND_DROP_LATITUDE_DEG, then straight down (the ellipsoid bottom is
        # above the jaw line, so a bob that hangs past the rim must leave the surface).
        pts, phs, norms = [], [], []
        ph = ph0
        ph_max = math.radians(STRAND_DROP_LATITUDE_DEG)
        while len(pts) < 200:
            th = th0 + drift * (min(ph, ph_max) - ph0)
            if ph <= ph_max:
                p = ell_pt(th, ph, radii)
                n = ell_normal(th, ph)
            else:
                p = ell_pt(th, ph_max, radii) + Vector((0.0, 0.0, -(ph - ph_max) * radii.z))
                n = ell_normal(th, ph_max)
                n = Vector((n.x, n.y, 0.0)).normalized()
            if p.z < z_end:
                break
            pts.append(p)
            phs.append(ph)
            norms.append(n)
            ph += math.radians(2.0)
        if len(pts) < 3:
            return
        step = max(1, (len(pts) - 1) / (rings - 1))
        sel = [pts[min(len(pts) - 1, round(k * step))] for k in range(rings)]
        seln = [norms[min(len(pts) - 1, round(k * step))] for k in range(rings)]
        base = len(hverts)
        for k, (p, n) in enumerate(zip(sel, seln)):
            t = (sel[min(k + 1, rings - 1)] - sel[max(k - 1, 0)]).normalized()
            b = t.cross(n).normalized()
            n = b.cross(t).normalized()
            taper = 1.0 - 0.75 * (k / (rings - 1)) ** 2
            w, h = width * taper, thick * (1.0 - 0.5 * (k / (rings - 1)))
            c = p + n * (h + STRAND_LIFT_M)
            for j in range(sides):
                a = 2 * math.pi * j / sides
                hverts.append(c + b * (w * math.cos(a)) + n * (h * math.sin(a)))
        for k in range(rings - 1):
            for j in range(sides):
                j1 = (j + 1) % sides
                hfaces.append([base + k * sides + j, base + k * sides + j1, base + (k + 1) * sides + j1, base + (k + 1) * sides + j])
        for end, order in ((0, -1), (rings - 1, 1)):     # caps
            cap = len(hverts)
            hverts.append(sum((hverts[base + end * sides + j] for j in range(sides)), Vector()) / sides)
            for j in range(sides):
                j1 = (j + 1) % sides
                hfaces.append([cap, base + end * sides + j1, base + end * sides + j][::order])
    z_bob = z_eye - HAIR_BOB_BELOW_EYES_M          # side strands end at the jaw line
    z_nape = ring_c.z + HAIR_NAPE_ABOVE_RING_M     # back strands end above the seam
    z_bang = z_eye + HAIR_BANG_ABOVE_EYES_M        # bangs end above the brows
    n_side = STRAND_COUNT_SIDES_BACK
    n_bang_override = None
    hair_cls = subj["hair"]["class"] if subj is not None else None
    if hair_cls == "short_straight":               # burst 3: ear-length straight bob, higher at the nape
        z_bob = z_eye + SHORT_SIDE_END_ABOVE_EYES_M
        z_nape = ring_c.z + SHORT_NAPE_ABOVE_RING_M
    if hair_cls == "long_straight":                # burst 3: to the collar — rigid hair must stay clear of the
        z_bob = collar_z + LONG_SIDE_ABOVE_COLLAR_M   # shoulders and the dress through every head turn
        z_nape = collar_z + LONG_NAPE_ABOVE_COLLAR_M
    if subj is not None and hair_cls in ("short_straight", "long_straight"):
        if subj["hair"].get("bangs"):              # bangs ON the forehead in neutral, ending just above the brows
            z_bang = z_eye + BANGS_ON_FOREHEAD_ABOVE_EYES_M
        # no bangs: the default short fringe at the hairline stays (it hides the helmet's front edge, which
        # otherwise reads as a hat brim); the forehead is open by ~25 mm between the brows and the fringe
    for k in range(n_side):                        # sides and back: from the left temple round the back to the right temple
        th = math.radians(HAIR_SIDE_FRONT_LIMIT_DEG) + math.radians(180.0 - 2 * HAIR_SIDE_FRONT_LIMIT_DEG) * k / (n_side - 1)   # temple … back … temple (front is −90°)
        wob = math.sin(37.0 * k) * 0.35 + math.cos(11.0 * k) * 0.25            # deterministic variety
        back = abs(math.sin(th))   # 1 at the back, 0 at the sides
        z_end = z_nape + (z_bob - z_nape) * (1.0 - back) ** 1.2
        strand(th, math.radians(28.0 + 6.0 * wob), z_end, STRAND_WIDTH_M * (1.0 + 0.25 * wob), STRAND_THICK_M, drift=0.12 * wob)
    n_bang = STRAND_COUNT_BANGS if n_bang_override is None else n_bang_override
    for k in range(n_bang):                        # bangs across the forehead
        th = math.radians(-135.0) + math.radians(90.0) * k / (n_bang - 1)
        wob = math.sin(23.0 * k) * 0.4
        strand(th, math.radians(20.0 + 5.0 * wob), z_bang + 0.006 * wob, STRAND_WIDTH_M * 1.1, STRAND_THICK_M, drift=0.15 * wob)
    # v04 (Q31): the cheek strand — two strands that leave the temple on the side the SHOT_002 camera
    # sees (the character's right, −X) and LIE ON the cheek. The generic `strand` walker follows the
    # helmet ellipsoid and then drops vertically, which never reaches the cheek (measured on v03: the
    # nearest hair vertex was 30 mm away). So this one is laid on the head shell itself: its centre
    # line is sampled on the skin by ray-casting from inside the head outward, and each ring is
    # lifted by its own half-thickness plus CHEEK_LIFT_M, which keeps it on the skin (≤ 3 mm) without
    # intersecting it. Rigid like the rest of the hair, no keys, child of SOCKET_HEAD.
    skin_tree = BVHTree.FromPolygons([c[:] for c in co], [list(f) for f in head_faces], all_triangles=False)
    eye_r = eye_c["R"]
    head_mid = Vector((0.0, head_c.y, 0.0))
    def on_skin(axis_point, direction):
        """First hit on the OUTER skin of the side `direction` points to: the ray starts 30 cm out
        along that direction and travels back toward the axis. Casting from the axis outward hits the
        inside of the eye socket first, and starting on the opposite side lands on the other cheek —
        both found while building this strand."""
        hit = skin_tree.ray_cast(axis_point + direction * 0.3, -direction, 0.6)
        return hit[0], hit[1]
    for si, (start_deg, _unused, width_k) in enumerate(CHEEK_STRANDS if subj is None else []):   # the cheek strand is the default head's
        end_z_off = eye_r.z - CHEEK_END_BELOW_EYE_M - (0.004 if si else 0.0)
        pts, nrms = [], []
        brow_pts = [co[i] for i in brow_band]
        for k in range(CHEEK_RINGS):
            u = k / (CHEEK_RINGS - 1)
            # the strand drops below the eye line early (u**0.55) and only then sweeps forward
            # (u**1.4), so it crosses the cheek, never the eye or the brow
            z = (eye_r.z + CHEEK_START_ABOVE_EYE_M) + (end_z_off - (eye_r.z + CHEEK_START_ABOVE_EYE_M)) * (u ** 0.55)
            yaw = math.radians(start_deg + CHEEK_SWEEP_DEG * (u ** 1.4))
            d = Vector((-math.cos(yaw), -math.sin(yaw), 0.0)).normalized()
            loc = nrm = None
            for _ in range(8):                 # lower the ring until it clears the eye and the brows
                loc, nrm = on_skin(Vector((0.0, head_c.y, z)), d)   # d points from the axis outward
                if loc is None:
                    z -= 0.002
                    continue
                clear_eye = (loc - eye_r).length
                clear_brow = min((loc - b).length for b in brow_pts)
                if clear_eye >= CHEEK_EYE_CLEAR_M and clear_brow >= CHEEK_BROW_CLEAR_M:
                    break
                z -= 0.002
            if loc is None:
                continue
            # the first rings are the root: sunk into the side hair mass so the strand grows out of
            # the hairdo instead of starting on bare skin (Q32)
            if u < CHEEK_ROOT_FRACTION:
                w_root = 1.0 - u / CHEEK_ROOT_FRACTION
                loc = loc + nrm * (CHEEK_ROOT_DEPTH_M * w_root)
            pts.append(loc); nrms.append(nrm)
        if len(pts) < 4:
            fail("cheek strand: the skin ray-casts missed")
        base = len(hverts)
        for k, (p, n) in enumerate(zip(pts, nrms)):
            u_k = k / (len(pts) - 1)
            t = (pts[min(k + 1, len(pts) - 1)] - pts[max(k - 1, 0)]).normalized()
            b = t.cross(n).normalized(); n2 = b.cross(t).normalized()
            taper = 1.0 - 0.93 * (k / (len(pts) - 1)) ** 1.5   # v04.1: the tip tapers away instead of a flat cut
            w = CHEEK_WIDTH_M * width_k * taper; h = CHEEK_THICK_M * taper
            lift = CHEEK_LIFT_M if u_k > CHEEK_ROOT_FRACTION else CHEEK_LIFT_M * 0.3
            c = p + n2 * (h * CHEEK_SINK + lift)
            for j in range(STRAND_SIDES):
                a = 2 * math.pi * j / STRAND_SIDES
                hverts.append(c + b * (w * math.cos(a)) + n2 * (h * math.sin(a)))
        rings = len(pts)
        for k in range(rings - 1):
            for j in range(STRAND_SIDES):
                j1 = (j + 1) % STRAND_SIDES
                hfaces.append([base + k * STRAND_SIDES + j, base + k * STRAND_SIDES + j1,
                               base + (k + 1) * STRAND_SIDES + j1, base + (k + 1) * STRAND_SIDES + j])
        for end, order in ((0, -1), (rings - 1, 1)):
            cap = len(hverts)
            hverts.append(sum((hverts[base + end * STRAND_SIDES + j] for j in range(STRAND_SIDES)), Vector()) / STRAND_SIDES)
            for j in range(STRAND_SIDES):
                j1 = (j + 1) % STRAND_SIDES
                hfaces.append([cap, base + end * STRAND_SIDES + j1, base + end * STRAND_SIDES + j][::order])
        print(f"cheek strand {si}: {rings} rings on the skin, from z {pts[0].z:.3f} to z {pts[-1].z:.3f}")


    # ---- 11c. burst 3: curly voluminous hair (only with --subject and hair class curly_voluminous) ----
    # Replaces the bob and its strands. A lumpy "cloud" shell well outside the skull-fitted helmet gives the
    # volume and the silhouette; hundreds of short helical curls rooted in it give the curly read. Mesh only,
    # rigid on the socket (C_HAIR contract). Deterministic: every random draw comes from random.Random(seed).
    # The class is volume-first by the owner's decision (2026-10-02): it may exceed the default head's
    # envelope; the build prints how far, the report states it.
    if subj is not None and subj["hair"]["class"] == "curly_voluminous":
        import random
        rng = random.Random(int(subj["seed"]))
        c0 = centre + Vector((0.0, CURL_CLOUD_BACK_M, CURL_CLOUD_UP_M))
        R = Vector((radii.x + CURL_VOLUME_M[0], radii.y + CURL_VOLUME_M[1], radii.z + CURL_VOLUME_M[2]))
        eyes = (eye_c["L"], eye_c["R"])
        def cloud_dir(th, ph):
            return Vector((math.sin(ph) * math.sin(th), -math.sin(ph) * math.cos(th), math.cos(ph)))
        def bump(th, ph):
            return (0.050 * math.sin(5 * th + 1.3) * math.sin(4 * ph + 0.7) + 0.035 * math.sin(9 * th + 2.1) * math.sin(7 * ph + 0.3)
                    + 0.020 * math.sin(14 * th + 0.4) * math.sin(11 * ph + 1.9))
        def cloud_pt(th, ph):
            d = cloud_dir(th, ph)
            return c0 + Vector((d.x * R.x, d.y * R.y, d.z * R.z)) * (1.0 + bump(th, ph))
        def covered(p):
            if any((p - e).length < CURL_EYE_CLEAR_M for e in eyes):
                return False
            if p.y < c0.y - 0.020:                                   # front: above the forehead hairline,
                # or, with bangs (Q69: subject_09), down onto the forehead to just above the brows like the straight bangs
                lim = CURL_BANG_ABOVE_EYES_M if subj["hair"].get("bangs") else CURL_HAIRLINE_ABOVE_EYES_M
                return p.z > z_eye + lim
            if p.y < c0.y + 0.015:                                   # temples: above the brow line
                return p.z > z_eye + CURL_TEMPLE_ABOVE_EYES_M
            return p.z > ring_c.z + CURL_NAPE_ABOVE_RING_M           # sides and back: down to the nape
        hverts, hfaces = [], []
        U, V = CURL_CLOUD_U, CURL_CLOUD_V
        grid = {}
        for vi in range(V + 1):
            ph = math.pi * vi / V
            for ui in range(U):
                th = 2 * math.pi * ui / U
                p = cloud_pt(th, ph)
                grid[(ui, vi)] = (len(hverts), covered(p))
                hverts.append(p)
        for vi in range(V):
            for ui in range(U):
                q = [(ui, vi), ((ui + 1) % U, vi), ((ui + 1) % U, vi + 1), (ui, vi + 1)]
                if all(grid[k][1] for k in q):
                    hfaces.append([grid[k][0] for k in q][::-1])
        cloud_faces = len(hfaces)
        golden = math.pi * (3.0 - math.sqrt(5.0))
        curls = 0
        for k in range(CURL_SAMPLES):
            zc = 1.0 - 2.0 * (k + 0.5) / CURL_SAMPLES
            ph = math.acos(zc)
            th = (golden * k) % (2 * math.pi)
            base = cloud_pt(th, ph)
            if not covered(base):
                continue
            n = (base - c0).normalized()
            a_ = n.cross(Vector((0.0, 0.0, 1.0)) if abs(n.z) < 0.9 else Vector((1.0, 0.0, 0.0))).normalized()
            b_ = n.cross(a_).normalized()
            L = rng.uniform(*CURL_LENGTH_M)
            rh = rng.uniform(*CURL_HELIX_R_M)
            rt = rng.uniform(*CURL_TUBE_R_M)
            turns = rng.uniform(*CURL_TURNS)
            phase = rng.uniform(0.0, 2 * math.pi)
            tilt = (a_ * rng.uniform(-0.35, 0.35) + b_ * rng.uniform(-0.35, 0.35))
            axis = (n + tilt).normalized()
            start = base - n * CURL_ROOT_DEPTH_M
            rings = max(8, int(turns * CURL_RINGS_PER_TURN))
            pts = []
            for r_ in range(rings + 1):
                t = r_ / rings
                ang = phase + 2 * math.pi * turns * t
                pts.append(start + axis * (L * t) + (a_ * math.cos(ang) + b_ * math.sin(ang)) * rh)
            base_i = len(hverts)
            for r_, p in enumerate(pts):
                tan = (pts[min(r_ + 1, rings)] - pts[max(r_ - 1, 0)]).normalized()
                u_ = tan.cross(n if abs(tan.dot(n)) < 0.95 else a_).normalized()
                w_ = tan.cross(u_).normalized()
                for s_ in range(CURL_SIDES):
                    al = 2 * math.pi * s_ / CURL_SIDES
                    hverts.append(p + (u_ * math.cos(al) + w_ * math.sin(al)) * rt)
            for r_ in range(rings):
                for s_ in range(CURL_SIDES):
                    s1 = (s_ + 1) % CURL_SIDES
                    hfaces.append([base_i + r_ * CURL_SIDES + s_, base_i + r_ * CURL_SIDES + s1,
                                   base_i + (r_ + 1) * CURL_SIDES + s1, base_i + (r_ + 1) * CURL_SIDES + s_])
            for end, order in ((0, -1), (rings, 1)):
                cap = len(hverts)
                hverts.append(pts[end])
                for s_ in range(CURL_SIDES):
                    s1 = (s_ + 1) % CURL_SIDES
                    hfaces.append([cap, base_i + end * CURL_SIDES + s_, base_i + end * CURL_SIDES + s1][::order])
            curls += 1
        print(f"curly hair: cloud {cloud_faces} faces, {curls} curls, {len(hverts)} vertices")

    if subj is not None:                           # the child's hair colour, every hair class
        bsdf = mats["HERO_HAIR"].node_tree.nodes.get("Principled BSDF") if mats["HERO_HAIR"].use_nodes else None
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (*subj["hair"]["color_linear"], 1.0)
        mats["HERO_HAIR"].diffuse_color = (*subj["hair"]["color_linear"], 1.0)
    me_h = bpy.data.meshes.new("HERO_HAIR")
    me_h.from_pydata([v[:] for v in hverts], [], hfaces)
    me_h.validate()
    me_h.update()
    hair = bpy.data.objects.new("HERO_HAIR", me_h)
    me_h.materials.append(mats["HERO_HAIR"])
    for p_ in me_h.polygons:
        p_.use_smooth = True
    mats["HERO_HAIR"].blend_method = "OPAQUE"

    return hair


def head_inputs_from_scene(collar_z=None):
    """The inputs from a character file, in HERO_HEAD's own (build) frame."""
    head = bpy.data.objects["HERO_HEAD"]; me = head.data; inv = head.matrix_world.inverted()
    co = [v.co.copy() for v in me.vertices]
    hused = list(range(len(co)))
    head_faces = [tuple(p.vertices) for p in me.polygons]
    eye_c = {S: (inv @ bpy.data.objects["HERO_EYE_" + S].matrix_world).translation.copy() for S in ("L", "R")}
    g = head.vertex_groups["SOCKET_BOUNDARY"].index
    ring = [co[v.index] for v in me.vertices if any(x.group == g for x in v.groups)]
    ring_c = sum(ring, Vector()) / len(ring)
    if collar_z is None:
        names = ("shoulder_l", "clavicle.L")      # the build renames MakeHuman's clavicle.L to shoulder_l
        rig = next((o for o in bpy.data.objects if o.type == "ARMATURE" and any(n in o.data.bones for n in names)), None)
        if rig is None:
            _fail("no armature with shoulder_l / clavicle.L — pass --collar-z")
        bone = next(rig.data.bones[n] for n in names if n in rig.data.bones)
        collar_z = (inv @ rig.matrix_world @ bone.head_local).z + DRESS_COLLAR_ABOVE_CLAVICLE_M
    return co, hused, head_faces, eye_c, ring_c, collar_z


def main(argv):
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("--subject")
    ap.add_argument("--collar-z", type=float); a = ap.parse_args(argv)
    subj = json.load(open(a.subject)) if a.subject else None
    co, hused, head_faces, eye_c, ring_c, collar_z = head_inputs_from_scene(a.collar_z)
    old = bpy.data.objects.get("HERO_HAIR")
    if old is not None:
        me_old = old.data; bpy.data.objects.remove(old); bpy.data.meshes.remove(me_old)
    mat = bpy.data.materials.get("HERO_HAIR") or bpy.data.materials.new("HERO_HAIR")
    hair = build_hair(co, hused, head_faces, eye_c, ring_c, collar_z, brow_band_of(co, hused, eye_c), subj, {"HERO_HAIR": mat})
    coll = bpy.data.collections.get("C_HAIR") or bpy.data.collections.new("C_HAIR")
    if coll.name not in bpy.context.scene.collection.children and not any(coll in c.children_recursive for c in [bpy.context.scene.collection]):
        bpy.context.scene.collection.children.link(coll)
    coll.objects.link(hair)
    head = bpy.data.objects["HERO_HEAD"]
    hair.parent = head.parent; hair.parent_type = head.parent_type; hair.parent_bone = head.parent_bone
    hair.matrix_parent_inverse = head.matrix_parent_inverse.copy(); hair.matrix_basis = head.matrix_basis.copy()
    for k in ("visible_camera", "visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter"):
        setattr(hair, k, getattr(head, k)) if False else None
    hair.visible_camera = True; hair.visible_shadow = True; hair.visible_diffuse = False; hair.visible_glossy = False
    hair.visible_transmission = False; hair.visible_volume_scatter = False
    bpy.ops.wm.save_as_mainfile(filepath=a.out, copy=True)
    print(f"HAIR_ON_HEAD_OK {a.out} class={(subj or {}).get('hair', {}).get('class', 'default_v04_1')} "
          f"vertices={len(hair.data.vertices)} faces={len(hair.data.polygons)} collar_z={collar_z:.4f}")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
