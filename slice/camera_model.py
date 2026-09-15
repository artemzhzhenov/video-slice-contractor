"""Pinhole camera model shared by the exporter and the round-trip test — pure Python, no Blender.

Pixel intrinsics from Blender's camera data, MEASURED on 5.2.1 with `world_to_camera_view`
(2026-09-15, review round 2; portrait and landscape, every fit):
- focal length in px: AUTO uses sensor_width against the LARGER frame dimension; HORIZONTAL uses
  sensor_width against the width; VERTICAL uses sensor_height against the height. Square pixels.
- the shift is a fraction of Blender's `viewfac`, which follows the fit: the width under
  HORIZONTAL, the height under VERTICAL, the larger dimension under AUTO. +shift_x moves the view
  right, so the optical axis lands left of centre; +shift_y moves the view up, so the axis lands
  lower in pixel rows (rows count down from the top, as EXR scanlines are stored).
  Measured principal points, lens 50 / 36×24 mm, shift (0.1, 0.05): HORIZONTAL 2160×3840 →
  (864, 2028); VERTICAL 3840×2160 → (1704, 1188); AUTO 2160×3840 → (696, 2112);
  HORIZONTAL 3840×2160 → (1536, 1272). tests/test_camera_model.py pins these.
The projection follows the exported camera convention: local -Z forward, +Y up, camera-to-world
matrices in socket space (conventions.exports.transform_conventions.camera)."""


def px_intrinsics(lens_mm, sensor_w_mm, sensor_h_mm, sensor_fit, shift, rx, ry):
    if sensor_fit == "AUTO":
        f = lens_mm / sensor_w_mm * max(rx, ry)
        viewfac = max(rx, ry)
    elif sensor_fit == "HORIZONTAL":
        f = lens_mm / sensor_w_mm * rx
        viewfac = rx
    elif sensor_fit == "VERTICAL":
        f = lens_mm / sensor_h_mm * ry
        viewfac = ry
    else:
        raise ValueError(f"unknown sensor_fit {sensor_fit!r}")
    return {"resolution_px": [rx, ry], "focal_length_px": [f, f],
            "principal_point_px": [rx / 2 - shift[0] * viewfac, ry / 2 + shift[1] * viewfac]}


def project(points_cam, focal_length_px, principal_point_px):
    """points_cam: iterable of (x, y, z) in the camera's local frame (-Z forward). Returns
    (u, v, depth) with u right, v DOWN, depth = -z > 0. Raises on a point at or behind the
    camera plane — a head behind the camera is a defect, never a clipped triangle."""
    fx, fy = focal_length_px
    cx, cy = principal_point_px
    out = []
    for x, y, z in points_cam:
        depth = -z
        if depth <= 0.0:
            raise ValueError(f"point {[x, y, z]} is at or behind the camera")
        out.append((cx + fx * x / depth, cy - fy * y / depth, depth))
    return out
