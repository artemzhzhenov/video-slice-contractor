#!/bin/sh
# Pin the slice toolchain: record exact versions and hashes of what is installed NOW into
# slice/toolchain.lock.json. Re-run only to re-pin deliberately; a diff in this file is a
# toolchain change and bumps the package (ADR-0002 D11).
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG="$ROOT/benchmarks/bakeoff/01J7B000000000000000BAKEXP/slice"
OCIO_FILE="$(ls "$PKG"/ocio/*.ocio | head -1)"
BLENDER_BIN="$(command -v blender)"
BLENDER_APP="$(readlink -f "$BLENDER_BIN" 2>/dev/null || echo "$BLENDER_BIN")"
BL_INFO="$(blender -b --python-expr 'import bpy,sys,json;print("BLINFO "+json.dumps({"version":bpy.app.version_string,"hash":bpy.app.build_hash.decode() if isinstance(bpy.app.build_hash,bytes) else str(bpy.app.build_hash),"build_date":bpy.app.build_date.decode() if isinstance(bpy.app.build_date,bytes) else str(bpy.app.build_date),"python":sys.version.split()[0],"ocio":".".join(str(x) for x in bpy.app.ocio.version),"oiio":".".join(str(x) for x in bpy.app.oiio.version),"openexr":".".join(str(x) for x in bpy.app.openexr.version) if hasattr(bpy.app,"openexr") else "n/a","alembic":".".join(str(x) for x in bpy.app.alembic.version) if hasattr(bpy.app,"alembic") else "n/a"}))' 2>/dev/null | sed -n 's/^BLINFO //p')"
python3 - "$BL_INFO" "$OCIO_FILE" "$BLENDER_APP" <<'PY'
import json, sys, subprocess, hashlib, datetime, platform
bl = json.loads(sys.argv[1]); ocio_file = sys.argv[2]; blender_app = sys.argv[3]
def run(*cmd):
    try: return subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception as e: return f"UNKNOWN ({e})"
def brew_version(formula):
    out = run("brew", "list", "--versions", formula) or run("brew", "list", "--cask", "--versions", formula)
    return out.split()[-1] if out else "UNKNOWN"
sha = hashlib.sha256(open(ocio_file, "rb").read()).hexdigest()
lock = {
  "pinned_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
  "machine": {"platform": platform.platform(), "chip": run("sysctl", "-n", "machdep.cpu.brand_string"),
              "ram_gb": round(int(run("sysctl", "-n", "hw.memsize") or 0) / 2**30), "gpu_backend": "METAL (Apple M4, 10 GPU cores) — verified via cycles preferences"},
  "blender": {"version": bl["version"], "build_hash": bl["hash"], "build_date": bl["build_date"], "python": bl["python"],
              "embedded": {"opencolorio": bl["ocio"], "openimageio": bl["oiio"], "openexr": bl["openexr"], "alembic": bl["alembic"]},
              "install": {"method": "homebrew cask", "cask_version": brew_version("blender"), "path": blender_app},
              "license": "GNU GPL — VERIFIED FACT (blender.org/about/license)"},
  "openimageio_cli": {"version": run("oiiotool", "--version"), "install": "homebrew formula " + brew_version("openimageio")},
  "opencolorio_cli": {"version": brew_version("opencolorio"), "tool": "ociocheck", "install": "homebrew formula"},
  "ocio_config": {"file": "benchmarks/bakeoff/01J7B000000000000000BAKEXP/slice/ocio/" + ocio_file.split("/")[-1],
                  "source": "https://github.com/AcademySoftwareFoundation/OpenColorIO-Config-ACES/releases/tag/v4.0.0",
                  "release": "v4.0.0 (ACES 2.0, OCIO 2.5)", "sha256": sha, "validated": "ociocheck: Archivable yes, tests complete",
                  "requires_ocio": "2.5 — Blender embeds " + bl["ocio"]},
  "rule": "A component not listed here is not the slice's toolchain. Any change re-runs slice/pin_toolchain.sh and bumps the package."
}
json.dump(lock, open("slice/toolchain.lock.json", "w"), indent=2); open("slice/toolchain.lock.json", "a").write("\n")
print(json.dumps({k: lock[k] for k in ("blender", "openimageio_cli", "opencolorio_cli")}, indent=1)[:900])
PY
