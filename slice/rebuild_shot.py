"""Test-rebuild of one shot from the archived source (REBUILD.md step 8; brief deliverable H).
Plain Python orchestrating the pinned toolchain:

    .venv/bin/python slice/rebuild_shot.py --pkg <pkg> --shot SHOT_001 --out <fresh dir> \
        [--smoke SAMPLES SCALE] [--frames all|1001-1010] [--root-pose X Y Z YAW]

Runs every REBUILD.md step into --out: template → check_scene → export → check_exports →
check_alembic → render (video + still) → split → composite → round-trip → package hash. Each
step's exit code, wall-clock and last output line go into rebuild_report.json. Then compares the
fresh result with the archived package: export files must hash-identically (a non-deterministic
export is a defect); render bundle parts are compared by their pixel SHA-1 tokens and the
numbers of identical / differing parts are reported (Cycles on Metal is measured not bit-exact,
slice/README.md). Exit 2 on any failed step or export mismatch; a missing archived counterpart
is reported as NOT COMPARED, never as a pass."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
OCIO_REL = "ocio/studio-config-v4.0.0_aces-v2.0_ocio-v2.5.ocio"
RENDER_TIMEOUT_S = 7 * 24 * 3600  # a conformant full-range render of a real asset is hours; the step, not the tool, decides when it is done


class RebuildError(RuntimeError):
    pass


def run(step, cmd, report, env, timeout=3600, cwd=ROOT):
    t = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    except subprocess.TimeoutExpired:
        report["steps"].append({"step": step, "returncode": None, "seconds": round(time.time() - t, 1), "last_stdout": "", "last_stderr": f"timeout after {timeout} s"})
        raise RebuildError(f"step {step} timed out after {timeout} s")
    tail = (r.stdout.strip().splitlines() or [""])[-1][:300]
    err = (r.stderr.strip().splitlines() or [""])[-1][:300]
    report["steps"].append({"step": step, "returncode": r.returncode, "seconds": round(time.time() - t, 1), "last_stdout": tail, "last_stderr": err if r.returncode else ""})
    print(f"REBUILD_STEP {step} rc={r.returncode} {round(time.time() - t, 1)}s {tail}")
    if r.returncode != 0:
        raise RebuildError(f"step {step} failed (rc {r.returncode}): {err or tail}")
    return r


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def compare_exports(dir_a, dir_b):
    """The export-reproducibility rule, shared with slice/accept_delivery.py: every file in
    both directories by sha256 (missing on one side counts as differing) — except proxies.abc,
    whose bytes carry a write date and the source path (measured 2026-09-15) and is compared
    through proxies_geometry_sha256 in its meta file, and export_manifest.json, which is
    compared field by field without files.proxies.abc (and without the older ocio_env path).
    Returns the comparison dict; "differing" empty means the two exports are the same."""
    dir_a, dir_b = Path(dir_a), Path(dir_b)
    a = {f.name: sha256(f) for f in dir_a.iterdir() if f.is_file()}
    b = {f.name: sha256(f) for f in dir_b.iterdir() if f.is_file()}
    differing = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k) and k not in ("proxies.abc", "export_manifest.json"))
    ma, mb = (json.loads((d / "export_manifest.json").read_text()) for d in (dir_a, dir_b))
    for m in (ma, mb):
        m.get("files", {}).pop("proxies.abc", None)
        m.pop("ocio_env", None)
    if ma != mb:
        differing.append("export_manifest.json (beyond files.proxies.abc)")
    ga = json.loads((dir_a / "proxies.abc.meta.json").read_text()).get("proxies_geometry_sha256")
    gb = json.loads((dir_b / "proxies.abc.meta.json").read_text()).get("proxies_geometry_sha256")
    abc = "identical bytes" if a.get("proxies.abc") == b.get("proxies.abc") else ("geometry identical (bytes differ: write date / source path in the Alembic header)" if ga and ga == gb else "GEOMETRY DIFFERS")
    if abc == "GEOMETRY DIFFERS":
        differing.append("proxies.abc (geometry hash)")
    n_all = len(set(a) | set(b))
    return {"files_compared": n_all, "byte_identical": n_all - len(differing) - (0 if abc == "identical bytes" else 1),
            "geometry_identical_bytes_differ": [] if abc == "identical bytes" else ["proxies.abc"], "differing": differing, "proxies_abc": abc}


def compare(pkg, shot, out, report, no_archive):
    """Fresh vs archive. Exports by compare_exports; renders: bundle parts by pixel SHA-1.
    Nothing to compare is NOT COMPARED, never a pass."""
    cmp = {"exports": "NOT COMPARED — no archived exports", "renders": {}}
    arch_ex, fresh_ex = pkg / "shots" / shot / "exports", out / "shots" / shot / "exports"
    if (arch_ex / "export_manifest.json").exists():
        cmp["exports"] = compare_exports(arch_ex, fresh_ex)
    for bm_path in sorted((out / "shots" / shot / "renders").glob("*/bundle_manifest.*.json")):
        prof = bm_path.parent.name
        arch = pkg / "shots" / shot / "renders" / prof / bm_path.name
        if not arch.exists():
            cmp["renders"][prof] = "NOT COMPARED — no archived render for this profile"
            continue
        bma, bmf = json.loads(arch.read_text()), json.loads(bm_path.read_text())
        rma = json.loads((arch.parent / bma["source_render_manifest"]).read_text())["settings"]
        rmf = json.loads((bm_path.parent / bmf["source_render_manifest"]).read_text())["settings"]
        if rma != rmf:
            raise RebuildError(f"{prof}: render settings differ from the archive's — {rmf} vs {rma}; a comparison across settings is not a rebuild")
        fa, ff = bma["bundles"], bmf["bundles"]
        ident, diff = 0, []
        for b in ff:
            for fr_f in ff[b]["frames"]:
                fr_a = next((r for r in fa.get(b, {}).get("frames", []) if r["frame"] == fr_f["frame"]), None)
                if fr_a is None:
                    diff.append(f"{b}/{fr_f['frame']}: not in archive")
                    continue
                for pf in fr_f["parts"]:
                    pa = next((p for p in fr_a["parts"] if p["name"] == pf["name"]), None)
                    if pa and pa.get("pixel_sha1") == pf.get("pixel_sha1"):
                        ident += 1
                    else:
                        diff.append(f"{b}/{fr_f['frame']}/{pf['name']}")
        cmp["renders"][prof] = {"settings": rmf, "parts_identical": ident, "parts_differing": diff,
                                "note": "pixel SHA-1 per part under identical settings; Metal is not bit-exact (README), so differing parts are listed and counted — an image tolerance for them does not exist yet and no threshold is invented here"}
    report["comparison_with_archive"] = cmp
    exports_compared = isinstance(cmp["exports"], dict)
    renders_compared = bool(cmp["renders"]) and all(isinstance(v, dict) for v in cmp["renders"].values())
    cmp["status"] = {"exports": "COMPARED" if exports_compared else "NOT COMPARED", "renders": "COMPARED" if renders_compared else "NOT COMPARED"}
    if not (exports_compared or renders_compared) and not no_archive:
        raise RebuildError("nothing to compare: the archive has no exports and no renders for this shot — pass --no-archive to record a build without comparison (status NOT COMPARED)")
    if exports_compared and cmp["exports"]["differing"]:
        raise RebuildError(f"exports are not reproducible: {cmp['exports']['differing']}")
    return exports_compared and renders_compared


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--pkg", required=True)
    p.add_argument("--shot", default="SHOT_001")
    p.add_argument("--out", required=True)
    p.add_argument("--smoke", nargs=2, type=int, metavar=("SAMPLES", "SCALE"), default=None)
    p.add_argument("--frames", default="all")
    p.add_argument("--root-pose", nargs=4, type=float, default=None)
    p.add_argument("--no-archive", action="store_true", help="the archive has nothing to compare against; record the build as NOT COMPARED instead of failing")
    args = p.parse_args(argv)
    pkg, out = Path(args.pkg).resolve(), Path(args.out).resolve()
    if out.exists() and any(out.iterdir()):
        raise RebuildError(f"{out} is not empty — a rebuild starts from nothing")
    out.mkdir(parents=True, exist_ok=True)
    # CYCLES_METAL_DISABLE_BINARY_ARCHIVES: a first rebuild on this machine crashed (SIGSEGV) in
    # Metal's MTLBinaryArchive serialisation while Cycles compiled the probe's shaders
    # (2026-09-15, backtrace in slice/README.md); the archive is a cache, not a result.
    env = dict(os.environ, OCIO=str(pkg / OCIO_REL), CYCLES_METAL_DISABLE_BINARY_ARCHIVES="1")
    if not (pkg / OCIO_REL).exists():
        raise RebuildError(f"vendored OCIO config missing: {pkg / OCIO_REL}")
    report = {"schema_note": "test-rebuild of one shot; slice/rebuild_shot.py", "package": str(pkg), "shot": args.shot, "out": str(out),
              "smoke": args.smoke, "frames": args.frames, "root_pose": args.root_pose, "no_archive": args.no_archive,
              "env": {"OCIO": env["OCIO"], "CYCLES_METAL_DISABLE_BINARY_ARCHIVES": "1"}, "steps": [], "status": "RUNNING"}
    report_path = out / "rebuild_report.json"
    try:
        (out / "ocio").mkdir(exist_ok=True)
        (out / OCIO_REL).write_bytes((pkg / OCIO_REL).read_bytes())  # step 2 first: a partial rebuild is still a package
        blend = out / "template.blend"
        sh = out / "shots" / args.shot
        ex, rd = sh / "exports", sh / "renders"
        B = ["blender", "-b", "--python-exit-code", "2"]
        run("3 template", B + ["-P", str(ROOT / "slice/scene_template.py"), "--", "--out", str(blend), "--shot", args.shot] + (["--root-pose", *map(str, args.root_pose)] if args.root_pose else []), report, env)
        run("3 check_scene", ["blender", "-b", str(blend), "--python-exit-code", "2", "-P", str(ROOT / "slice/check_scene.py")], report, env)
        run("5 export", ["blender", "-b", str(blend), "--python-exit-code", "2", "-P", str(ROOT / "slice/export_shot.py"), "--", "--shot", args.shot, "--out", str(ex)], report, env)
        run("5 check_exports", [PY, str(ROOT / "slice/check_exports.py"), str(ex)], report, env)
        run("5 check_alembic", B + ["-P", str(ROOT / "slice/check_alembic.py"), "--", "--abc", str(ex / "proxies.abc"), "--meta", str(ex / "proxies.abc.meta.json")], report, env)
        smoke = ["--samples", str(args.smoke[0]), "--scale", str(args.smoke[1])] if args.smoke else []
        run("6 render video", ["blender", "-b", str(blend), "--python-exit-code", "2", "-P", str(ROOT / "slice/render_passes.py"), "--", "--shot", args.shot, "--profile", "video", "--frames", args.frames, "--probe", "--out", str(rd)] + smoke, report, env, timeout=RENDER_TIMEOUT_S)
        run("6 render still", ["blender", "-b", str(blend), "--python-exit-code", "2", "-P", str(ROOT / "slice/render_passes.py"), "--", "--shot", args.shot, "--profile", "still", "--frames", "still", "--probe", "--out", str(rd)] + smoke, report, env, timeout=RENDER_TIMEOUT_S)
        for prof in ("video", "still"):
            run(f"6 split {prof}", B + ["-P", str(ROOT / "slice/split_bundles.py"), "--", str(rd / prof), "--exports", str(ex)], report, env)
            run(f"6 composite {prof}", B + ["-P", str(ROOT / "slice/composite.py"), "--", str(rd / prof)], report, env)
            run(f"8 roundtrip {prof}", B + ["-P", str(ROOT / "slice/roundtrip.py"), "--", "--exports", str(ex), "--renders", str(rd / prof)], report, env)
        run("7 package hash", [PY, str(ROOT / "slice/package.py"), "hash", str(out)], report, env)
        compared = compare(pkg, args.shot, out, report, args.no_archive)
        c = report["comparison_with_archive"]
        if compared:
            n_diff = sum(len(v["parts_differing"]) for v in c["renders"].values())
            n_all = sum(v["parts_identical"] + len(v["parts_differing"]) for v in c["renders"].values())
            # The status says what was proven, not "PASS": exports are byte-reproducible; renders
            # were compared part by part and Metal's differences are counted, not judged.
            report["status"] = f"EXPORTS REPRODUCIBLE; RENDERS COMPARED ({n_diff} of {n_all} parts differ, no image tolerance defined)"
        elif "COMPARED" in c["status"].values():
            report["status"] = "PARTIALLY COMPARED: " + ", ".join(f"{k} {v}" for k, v in c["status"].items())
        else:
            report["status"] = "NOT COMPARED"
    except RebuildError as e:
        report["status"] = "FAIL"
        report["error"] = str(e)
        raise
    finally:
        report_path.write_text(json.dumps(report, indent=1) + "\n")
    print(f"REBUILD_OK {args.shot} {len(report['steps'])} steps status={report['status']} -> {report_path}")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except RebuildError as e:
        print(f"REBUILD_ERROR: {e}", file=sys.stderr)
        sys.exit(2)
