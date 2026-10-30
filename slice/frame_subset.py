"""The frames a gate measures (`--frames` of slice/roundtrip.py and slice/check_skin_tone.py). Without a spec a gate
measures every frame of its bundle, as before. With one it measures the named frames only and its record says how many
of the bundle's frames those are — the master's full-range render gates its plates' picked frames and every 10th
(owner 2026-10-30, option (c)), never silently fewer. Plain Python."""


def select(available, spec):
    """(frames, coverage record): `spec` is None or a comma list of frames, every one of which `available` must hold."""
    have = sorted(set(available))
    if spec is None:
        return have, {"frames_gated": have, "frames_in_bundle": len(have), "coverage": "every frame of the bundle"}
    try:
        want = sorted({int(x) for x in spec.split(",") if x.strip()})
    except ValueError:
        raise ValueError(f"--frames {spec!r}: expected a comma list of frame numbers") from None
    if not want:
        raise ValueError(f"--frames {spec!r} names no frame")
    missing = [f for f in want if f not in have]
    if missing:
        raise ValueError(f"--frames names {missing}, which the bundle does not hold ({have[0]}-{have[-1]}, {len(have)} frames)")
    return want, {"frames_gated": want, "frames_in_bundle": len(have),
                  "coverage": f"{len(want)} of the bundle's {len(have)} frames, named by --frames"}
