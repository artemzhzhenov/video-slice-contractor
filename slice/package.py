"""Content-addressed slice package (ADR-0002 D11; brief deliverable G). Plain Python:

    .venv/bin/python slice/package.py hash   <pkg> [--offline <dir>]   # writes package_manifest.json
    .venv/bin/python slice/package.py verify <pkg> [--offline <dir>]   # recomputes, exit 2 on any difference

`hash` walks the package, records sha256 and size of every file (excluding Blender backups,
the manifest itself and OS litter), derives per-shot entries from the export and bundle
manifests it finds, fills toolchain / OCIO / channel-vocabulary fields from the repository's
lock files and computes `package_hash` = sha256 over the sorted "sha256␠␠path" lines. It
refuses to write when the vendored OCIO config's hash differs from the lock. `verify` is what
"immutable" means in practice: missing, added or changed files are listed and fail. Values that
no measurement supports stay UNKNOWN with the reason.

Offline part (owner decision 2026-09-29: the slice package's heavy files live on the archive disk, the git record keeps
the manifest and the light files): `--offline <dir>` is a second root with the same relative layout — renders, the
shots' source .blend files, the per-frame exports. One file table, one `package_hash` over both; offline entries carry
`"offline": true`. `verify` without `--offline` checks the light part and re-derives everything from it with the
offline files' recorded hashes, and says so — PACKAGE_VERIFIED_LIGHT with the count not checked, never
PACKAGE_VERIFIED; with `--offline` every file is checked. `hash` refuses to run without `--offline` over a manifest
that records offline files (it would silently drop them)."""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_SUFFIX = (".blend1",)
EXCLUDE_NAMES = {"package_manifest.json", ".DS_Store"}
EXCLUDE_DIRS = {"__pycache__"}
MANIFEST_NOTE = "content-addressed package; `hash`/`verify` by slice/package.py"
CARRIED_FROM_PREVIOUS = ("master_contract_version", "template", "exports", "renders", "envelope_provisional")  # descriptive, hand-maintained


class PackageError(RuntimeError):
    pass


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def walk(pkg):
    files = {}
    for p in sorted(pkg.rglob("*")):
        if not p.is_file() or p.name in EXCLUDE_NAMES or p.suffix in EXCLUDE_SUFFIX or EXCLUDE_DIRS & set(p.relative_to(pkg).parts):
            continue
        files[p.relative_to(pkg).as_posix()] = {"sha256": sha256(p), "bytes": p.stat().st_size}
    return files


def package_hash(files):
    lines = "".join(f"{v['sha256']}  {k}\n" for k, v in sorted(files.items()))
    return hashlib.sha256(lines.encode()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text())


def shot_entries(pkg, files):
    shots = {}
    for shot_dir in sorted((pkg / "shots").iterdir()) if (pkg / "shots").is_dir() else []:
        if not shot_dir.is_dir():
            continue
        entry = {"exports": "NOT PRESENT", "renders": {}}
        em = shot_dir / "exports" / "export_manifest.json"
        if em.exists():
            m = load_json(em)
            rel = em.relative_to(pkg).as_posix()
            for name, h in m["files"].items():
                key = f"{rel.rsplit('/', 1)[0]}/{name}"
                if key not in files or files[key]["sha256"] != h:
                    raise PackageError(f"{shot_dir.name}: export_manifest hash for {name} does not match the file on disk — stale exports are not packaged")
            entry["exports"] = {"manifest": rel, "manifest_sha256": files[rel]["sha256"], "files": len(m["files"]), "frames": m["frames"],
                                "channel_vocabulary_version": m["channel_vocabulary_version"], "blender": m["blender"]}
        for bm_path in sorted(shot_dir.glob("renders/*/bundle_manifest.*.json")):
            bm = load_json(bm_path)
            rel = bm_path.relative_to(pkg).as_posix()
            per = {"manifest": rel, "manifest_sha256": files[rel]["sha256"], "smoke_test_only": bm["smoke_test_only"],
                   "frames": [f["frame"] for f in bm["bundles"]["COMPOSITE_BUNDLE"]["frames"]],
                   "bundle_files": {b: [f["sha256"] for f in info["frames"]] for b, info in bm["bundles"].items()},
                   "precomp_reproduction": "PASS" if bm["bundles"]["COMPOSITE_BUNDLE"].get("derived") else "NOT RUN",
                   "roundtrip": bm.get("roundtrip", {}).get("status", "NOT RUN")}
            for b, info in bm["bundles"].items():
                for f in info["frames"]:
                    key = f"{rel.rsplit('/', 1)[0]}/{b}/{f['file']}"
                    if key not in files or files[key]["sha256"] != f["sha256"]:
                        raise PackageError(f"{shot_dir.name}/{bm['profile']}: {b}/{f['file']} differs from its bundle_manifest hash")
            entry["renders"][bm["profile"]] = per
        shots[shot_dir.name] = entry
    return shots


def measurements(pkg, shots, existing):
    """Derived only: a value survives from the previous manifest solely when it is an UNKNOWN
    with its reason (nothing on disk supports it) — a derived number never carries over.
    `S_frame` is platform.md's: bytes of master passes a bundle's consumer reads per frame — not
    render time, which is `render_seconds_per_frame` (until 2026-09-29 this function wrote render
    seconds under `S_frame`)."""
    m = {k: v for k, v in existing.get("measurements", {}).items() if isinstance(v, str) and v.startswith("UNKNOWN")}
    bpf, render_seconds = {}, {}
    for shot, e in shots.items():
        for prof, r in e["renders"].items():
            bm = load_json(pkg / r["manifest"])
            bpf[f"{shot}/{prof}"] = {b: info["bytes_per_frame"] for b, info in bm["bundles"].items()}
            rm = load_json(pkg / r["manifest"].rsplit("/", 1)[0] / bm["source_render_manifest"])
            if not rm["smoke_test_only"]:
                # render_passes.py records seconds per render group ({"beauty": s, "data": s}); a frame costs their sum
                secs = [row["seconds"] for row in rm["frames"] if "seconds" in row]
                if any(not isinstance(v, dict) for v in secs):
                    raise PackageError(f"{shot}/{prof}: render manifest seconds are not per render group — {secs[:2]}")
                groups = sorted({g for v in secs for g in v})
                render_seconds[f"{shot}/{prof}"] = {"mean_seconds_per_frame": sum(sum(v.values()) for v in secs) / len(secs),
                                                   "mean_seconds_per_group": {g: sum(v.get(g, 0.0) for v in secs) / len(secs) for g in groups},
                                                   "frames": len(secs), "device": rm.get("device", "UNKNOWN")} if secs else "UNKNOWN"
    t_comp, s_frame = {}, {}
    for shot, e in shots.items():
        for prof, r in e["renders"].items():
            key = f"{shot}/{prof}"
            bm = load_json(pkg / r["manifest"])
            s_frame[key] = {"head technology (HEAD_RENDER_BUNDLE)": bm["bundles"]["HEAD_RENDER_BUNDLE"]["bytes_per_frame"]["mean"]}
            om_path = pkg / "shots" / shot / "order_qc" / prof / "order_composite_manifest.json"
            if not om_path.exists():
                continue
            om = load_json(om_path)
            if om["status"] != "PASS" or om["smoke_test_only"]:
                continue
            fr = om["frames"]
            blur = [f["post_composite_blur"]["seconds"] for f in bm["bundles"]["COMPOSITE_BUNDLE"].get("derived", {}).get("frames", []) if "post_composite_blur" in f]
            applied = om.get("post_composite_blur", {}).get("applied", False)
            t_comp[key] = {"mean_wall_s": sum(f["t_comp"]["wall_s"] for f in fr) / len(fr), "mean_cpu_s": sum(f["t_comp"]["cpu_s"] for f in fr) / len(fr),
                           "frames": len(fr), "order_id": om["order_id"], "includes_post_composite_blur": applied,
                           "qc_path_blur_seconds_per_frame": (sum(blur) / len(blur)) if blur else "NOT APPLICABLE (still)"}
            if applied:
                t_comp[key]["blur_seconds_per_frame"] = sum(f["metrics"]["post_composite_blur"]["seconds"] for f in fr) / len(fr)
            elif blur:
                t_comp[key]["excludes"] = "the post-composite blur: this order composite did not apply it (made before 2026-09-29, exit review step 5)"
            s_frame[key]["per-order compositor (COMPOSITE_BUNDLE composite + derived, read whole)"] = sum(f["master_bytes_read"] for f in fr) / len(fr)
    if t_comp:
        m["t_comp"] = t_comp
    wp = pkg / "warmup" / "warmup.json"
    if wp.exists():
        w = load_json(wp)
        m["worker_warmup_minutes"] = {"value": w["worker_warmup_minutes"], "machine": w["machine"], "rule": w["rule"], "not_measured": w["not_measured"], "source": "warmup/warmup.json"}
    if any(len(v) > 1 for v in s_frame.values()):
        m["S_frame"] = {**s_frame, "unit": "bytes of master passes read per frame, per consumer (docs/architecture/platform.md)"}
    if bpf:
        m["bytes_per_frame"] = bpf
    if render_seconds:
        m["render_seconds_per_frame"] = render_seconds
    elif any(e["renders"] for e in shots.values()):
        m["render_seconds_per_frame"] = "UNKNOWN — only smoke renders in the package (reduced samples / scale); render time is measured on a conformant render"
    return m


def merged_files(pkg, offline):
    files = walk(pkg)
    if offline is None:
        return files
    off = walk(offline)
    clash = sorted(set(files) & set(off))
    if clash:
        raise PackageError(f"{len(clash)} paths exist in both the package and its offline part, e.g. {clash[:3]}")
    for v in off.values():
        v["offline"] = True
    files.update(off)
    return dict(sorted(files.items()))


def build_manifest(pkg, offline=None):
    existing = load_json(pkg / "package_manifest.json") if (pkg / "package_manifest.json").exists() else {}
    recorded_offline = sum(1 for v in existing.get("files", {}).values() if v.get("offline"))
    if recorded_offline and offline is None:
        raise PackageError(f"the manifest records {recorded_offline} offline files — pass --offline <dir>; hashing without it would drop them")
    lock = load_json(ROOT / "slice" / "toolchain.lock.json")
    conv = load_json(ROOT / "slice" / "conventions.json")
    cmap = load_json(ROOT / "slice" / "channel_map.json")
    files = merged_files(pkg, offline)
    ocio_rel = "ocio/" + Path(lock["ocio_config"]["file"]).name
    if ocio_rel not in files:
        raise PackageError(f"vendored OCIO config {ocio_rel} missing from the package")
    if files[ocio_rel]["sha256"] != lock["ocio_config"]["sha256"]:
        raise PackageError(f"OCIO config hash {files[ocio_rel]['sha256']} differs from the lock {lock['ocio_config']['sha256']}")
    shots = shot_entries(pkg, files)
    # Hand-maintained descriptive keys are carried over explicitly; everything else is derived.
    man = {k: existing[k] for k in CARRIED_FROM_PREVIOUS if k in existing}
    man.update({
        "schema_note": MANIFEST_NOTE,
        "experiment_id": conv["experiment_id"], "master_id": conv["master_id"], "master_version": conv["master_version"],
        "master_contract_version": existing.get("master_contract_version", 1),
        "toolchain": {"lock": "slice/toolchain.lock.json", "lock_sha256": sha256(ROOT / "slice" / "toolchain.lock.json"),
                      "blender": lock["blender"]["version"], "blender_build_hash": lock["blender"]["build_hash"],
                      "openimageio_cli": lock["openimageio_cli"]["version"], "opencolorio_cli": lock["opencolorio_cli"]["version"]},
        "ocio_config": {"file": ocio_rel, "release": lock["ocio_config"]["release"], "sha256": files[ocio_rel]["sha256"], "scene_linear": conv["colour"]["working_space"]},
        "channel_vocabulary_version": cmap["channel_vocabulary_version"],
        "shots": shots,
        "content_addressing": {"algorithm": "sha256", "excluded": {"suffixes": list(EXCLUDE_SUFFIX), "names": sorted(EXCLUDE_NAMES), "dirs": sorted(EXCLUDE_DIRS)},
                               "file_count": len(files), "total_bytes": sum(v["bytes"] for v in files.values()),
                               "offline": {"root_at_hashing": str(offline) if offline else None, "file_count": sum(1 for v in files.values() if v.get("offline")),
                                           "total_bytes": sum(v["bytes"] for v in files.values() if v.get("offline"))},
                               "package_hash_rule": "sha256 over the sorted lines 'sha256␠␠relative/path\\n' of `files`"},
        "files": files,
        "package_hash": package_hash(files),
        "hashed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "carried_from_previous_manifest_unverified": [k for k in CARRIED_FROM_PREVIOUS if k in existing],
        "measurements": measurements(pkg, shots, existing),
    })
    return man


def verify(pkg, offline=None):
    """Recompute everything derivable and compare: the file table, the package hash, the
    per-shot entries (export / render manifests re-read from disk) and the measurements. A
    hand-edited `roundtrip: PASS` or a stale measurement fails here, not only a changed file.
    Without `offline` the offline entries are taken as recorded and counted as not checked."""
    mp = pkg / "package_manifest.json"
    if not mp.exists():
        raise PackageError("no package_manifest.json — nothing to verify against")
    man = load_json(mp)
    then = man.get("files", {})
    not_checked = {k: v for k, v in then.items() if v.get("offline")} if offline is None else {}
    now = merged_files(pkg, offline)
    now.update(not_checked)
    diff = {"missing": sorted(set(then) - set(now)), "added": sorted(set(now) - set(then)),
            "changed": sorted(k for k in set(then) & set(now) if then[k]["sha256"] != now[k]["sha256"])}
    diff["package_hash_recomputed"] = package_hash(now)
    diff["package_hash_recorded"] = man.get("package_hash")
    derived_diff = []
    if not (diff["missing"] or diff["added"] or diff["changed"]):
        shots = shot_entries(pkg, now)
        if shots != man.get("shots"):
            derived_diff.append("shots")
        if measurements(pkg, shots, {"measurements": man.get("measurements", {})}) != man.get("measurements"):
            derived_diff.append("measurements")
    diff["derived_entries_differ"] = derived_diff
    diff["offline_not_checked"] = len(not_checked)
    diff["ok"] = not (diff["missing"] or diff["added"] or diff["changed"] or derived_diff) and diff["package_hash_recomputed"] == diff["package_hash_recorded"]
    return diff


def main(argv):
    offline = None
    if len(argv) == 4 and argv[2] == "--offline":
        offline, argv = Path(argv[3]).resolve(), argv[:2]
    if len(argv) != 2 or argv[0] not in ("hash", "verify"):
        raise PackageError("usage: package.py hash|verify <package dir> [--offline <dir>]")
    pkg = Path(argv[1]).resolve()
    if not pkg.is_dir() or (offline is not None and not offline.is_dir()):
        raise PackageError(f"{pkg if not pkg.is_dir() else offline} is not a directory")
    if argv[0] == "hash":
        man = build_manifest(pkg, offline)
        (pkg / "package_manifest.json").write_text(json.dumps(man, indent=1, ensure_ascii=False) + "\n")
        off = man["content_addressing"]["offline"]
        print(f"PACKAGE_OK {man['content_addressing']['file_count']} files {man['content_addressing']['total_bytes']} bytes "
              f"({off['file_count']} offline, {off['total_bytes']} bytes) package_hash={man['package_hash']}")
    else:
        diff = verify(pkg, offline)
        print(json.dumps(diff, indent=1))
        if not diff["ok"]:
            raise PackageError("package differs from its manifest")
        if diff["offline_not_checked"]:
            print(f"PACKAGE_VERIFIED_LIGHT package_hash={diff['package_hash_recorded']} — {diff['offline_not_checked']} offline files NOT CHECKED (run verify with --offline <dir>)")
        else:
            print(f"PACKAGE_VERIFIED package_hash={diff['package_hash_recorded']}")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (PackageError, OSError, ValueError, KeyError) as e:
        print(f"PACKAGE_ERROR: {e}", file=sys.stderr)
        sys.exit(2)
