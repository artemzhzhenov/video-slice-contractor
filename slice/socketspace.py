"""Socket-space conversion (ADR-0002 D1/D7, proposal §3) — pure Python, no Blender, no numpy,
so the maths is unit-tested in CI and used verbatim inside Blender by the exporters.

Blender world: right-handed, +Z up, character faces -Y.
Socket space:  right-handed, +Y up, +Z forward (facing), +X = character's anatomical left.

    X_s = X_b ;  Y_s = Z_b ;  Z_s = -Y_b        R = Rx(-90°), det +1

Every exported transform is first expressed relative to SOCKET_SPACE_ROOT (T_rel = root⁻¹ · T),
then converted: T_s = C · T_rel · C⁻¹. Scale must be 1 within SCALE_TOL; anything else raises —
never normalised (CLAUDE.md §6). Quaternions are (x, y, z, w) with w ≥ 0."""
from __future__ import annotations

import math

SCALE_TOL = 1e-6
R_B2S = [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]]
C = [[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, -1.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
C_INV = [[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, -1.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
IDENTITY4 = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]


class SocketExportError(ValueError):
    """A transform that violates the contract. Raised, never clamped."""


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def mat_inv(m):
    """General 4×4 inverse by Gauss–Jordan; raises on a singular matrix."""
    n = 4
    a = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(m)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise SocketExportError("singular matrix")
        a[col], a[pivot] = a[pivot], a[col]
        p = a[col][col]
        a[col] = [v / p for v in a[col]]
        for r in range(n):
            if r != col and a[r][col] != 0.0:
                f = a[r][col]
                a[r] = [rv - f * cv for rv, cv in zip(a[r], a[col])]
    return [row[n:] for row in a]


def det3(m):
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def convert_transform(t_world_b, root_world_b=None):
    """Blender world 4×4 → socket-space 4×4 relative to the root, as a CHANGE OF BASIS of the
    local frame too (similarity C·T·C⁻¹). Use for the socket: its local frame is socket-oriented
    by definition (identity at rest, the head asset is authored Y-up, Z-forward)."""
    t_rel = mat_mul(mat_inv(root_world_b), t_world_b) if root_world_b is not None else t_world_b
    return mat_mul(mat_mul(C, t_rel), C_INV)


def convert_transform_keep_local(t_world_b, root_world_b=None):
    """Blender world 4×4 → socket-space 4×4 relative to the root, KEEPING the object's own local
    frame (left-multiply C·root⁻¹·T). Use for the camera (local −Z forward, +Y up stays what a
    consumer re-projects with) and for bones (Y along the bone stays Y along the bone). Using the
    similarity here re-labels the local axes and makes a camera look along socket +Y — the defect
    the first export shipped."""
    t_rel = mat_mul(mat_inv(root_world_b), t_world_b) if root_world_b is not None else t_world_b
    return mat_mul(C, t_rel)


def convert_point(p_b, root_world_b=None):
    x, y, z = p_b
    if root_world_b is not None:
        inv = mat_inv(root_world_b)
        x, y, z = (inv[i][0] * x + inv[i][1] * y + inv[i][2] * z + inv[i][3] for i in range(3))
    return [R_B2S[i][0] * x + R_B2S[i][1] * y + R_B2S[i][2] * z for i in range(3)]


def convert_direction(d_b, root_world_b=None):
    x, y, z = d_b
    if root_world_b is not None:
        inv = mat_inv(root_world_b)
        x, y, z = (inv[i][0] * x + inv[i][1] * y + inv[i][2] * z for i in range(3))
    return [R_B2S[i][0] * x + R_B2S[i][1] * y + R_B2S[i][2] * z for i in range(3)]


def decompose(t, scale_tol=SCALE_TOL, name="transform"):
    """4×4 → {position_m, quaternion (x,y,z,w; w ≥ 0), scale, matrix_4x4}. Raises when the scale
    deviates from 1 by more than scale_tol or the rotation is not proper (det ≠ +1)."""
    rot = [[t[i][j] for j in range(3)] for i in range(3)]
    scales = [math.sqrt(sum(rot[i][j] ** 2 for i in range(3))) for j in range(3)]
    for s in scales:
        if abs(s - 1.0) > scale_tol:
            raise SocketExportError(f"{name}: scale {scales} deviates from 1 by more than {scale_tol}")
    if det3(rot) < 0:
        raise SocketExportError(f"{name}: improper rotation (det < 0) — a mirrored transform")
    q = quaternion_from_matrix(rot)
    measured_scale = sum(scales) / 3.0
    return {"position_m": [t[0][3], t[1][3], t[2][3]], "quaternion": q, "scale": measured_scale, "matrix_4x4": [row[:] for row in t]}


def quaternion_from_matrix(m):
    """Rotation matrix → unit quaternion (x, y, z, w), sign canonicalised to w ≥ 0 (Shepperd)."""
    tr = m[0][0] + m[1][1] + m[2][2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        w = 0.25 * s; x = (m[2][1] - m[1][2]) / s; y = (m[0][2] - m[2][0]) / s; z = (m[1][0] - m[0][1]) / s
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2
        w = (m[2][1] - m[1][2]) / s; x = 0.25 * s; y = (m[0][1] + m[1][0]) / s; z = (m[0][2] + m[2][0]) / s
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2
        w = (m[0][2] - m[2][0]) / s; x = (m[0][1] + m[1][0]) / s; y = 0.25 * s; z = (m[1][2] + m[2][1]) / s
    else:
        s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2
        w = (m[1][0] - m[0][1]) / s; x = (m[0][2] + m[2][0]) / s; y = (m[1][2] + m[2][1]) / s; z = 0.25 * s
    n = math.sqrt(x * x + y * y + z * z + w * w)
    q = [x / n, y / n, z / n, w / n]
    if q[3] < 0:
        q = [-v for v in q]
    return q


def rotation_x(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[1, 0, 0, 0], [0, c, -s, 0], [0, s, c, 0], [0, 0, 0, 1]]


def rotation_z(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]


def translation(x, y, z):
    return [[1, 0, 0, x], [0, 1, 0, y], [0, 0, 1, z], [0, 0, 0, 1]]
