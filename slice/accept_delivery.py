"""Acceptance item 5 of contractor/burst-1/ACCEPTANCE.md, executed as one command: rebuild the
delivered scene from the contractor's build script on top of our template and prove the
delivered file is the product of that script. Plain Python orchestrating Blender:

    .venv/bin/python slice/accept_delivery.py --delivered <character_vNN.blend> \\
        --build <deliverables/scripts/build_character.py> \\
        --template-repo <path or URL of the public copy> --template-commit <sha from REPORT.md> \\
        --mpfb git:https://github.com/makehumancommunity/mpfb2@v2.0.17 --mpfb-version 2.0.17 \\
        --mpfb-commit 80919fa… --out <fresh dir> [--asset-check SAMPLES SCALE | --no-asset-check]

Steps (each recorded with exit code, wall-clock, last verdict line and a log file in
acceptance_report.json):
  0  environment; the judging tools (this repository's slice/*) fingerprinted by git commit,
     dirty flag and per-file sha256; MPFB2 from the source named in LICENSES.md (git ref or zip)
     built into an extension zip and installed into an ISOLATED Blender profile under --out
     (BLENDER_USER_EXTENSIONS / _CONFIG / _SCRIPTS / _DATAFILES — never the reviewer's own);
     the enabled module's manifest version must equal --mpfb-version and, for a git source,
     the checkout's HEAD must equal --mpfb-commit.
  1  template: slice/scene_template.py taken from the template repository at --template-commit
     (git archive; the checks below always use THIS repository's current tools).
  2  build: the build script's directory is COPIED into the run directory and run there
     (blender -b template.blend -P build_character.py -- --out rebuilt.blend), so a relative
     path to the delivered file resolves to nothing. It must exit 0 and print BUILD_OK
     (ACCEPTANCE item 5а). Before it runs, every .py in that directory is scanned for what a
     rebuild never needs — opening or appending another .blend, spawning processes, network,
     file copying, operators resolved at run time — and a hit FAILS the run with the line
     quoted (comments and docstrings are not scanned, only *.py files are; --allow-scan-hits
     records the hits and caps the verdict at PARTIAL). After it runs, the tool fingerprint is
     re-checked (byte-code caches under slice/, scripts/ and schemas/ are deleted before the
     fingerprint and must not have reappeared — Blender's embedded Python ignores
     PYTHONDONTWRITEBYTECODE, so a planted .pyc is caught by presence, not by hash), the delivered file's sha256
     must be what it was before the build and the rebuilt bytes must differ from the delivered
     bytes (a byte copy is not a build). The scan catches the obvious forms only; the controls
     are the fingerprints, the byte checks and a human reading of the copied scripts, whose
     sha256 are all recorded. NOT a sandbox: a script that assembles an operator name at run
     time, opens the delivery and saves it as the rebuilt file passes every check here — bytes
     differ, content equal by construction — and only the human reading catches it.
  3  check_scene on the delivered and the rebuilt file, zero failures (5а).
  4  check_asset.sh on the rebuilt file (5б) and on the delivered file (item 1 at the same smoke
     settings) unless --no-asset-check, which is recorded as NOT RUN and caps the verdict at
     PARTIAL — never a silent pass.
  5  exports of --shot from both files compared by the rule of slice/rebuild_shot.py (5в) —
     with the declared cross-platform tolerance (conventions.rebuild): a file that is not
     byte-identical is compared numerically, and proxies.abc by slice/compare_alembic.py.
  6  slice/blend_content_hash.py on both files: equal hash, or the canonical content dumps
     compared numerically within the same tolerance; beyond it the differing objects, materials
     or meshes are listed with their first differing fields (5г).

Verdict line and exit code: ACCEPTANCE_REBUILD_OK (0) — every step ran and passed, MPFB2
installed from a git source at the declared commit; ACCEPTANCE_REBUILD_PARTIAL (3) — every step
that ran passed but the asset check was skipped, or MPFB2 was not installed / its commit could
not be verified (zip source); ACCEPTANCE_REBUILD_FAIL (2) — a step failed, with the reason;
64 — usage error, nothing ran. Bytes of the two .blend files are never compared for equality
(ACCEPTANCE item 5); they are only required to differ."""
import argparse
import ast
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tokenize
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from slice.rebuild_shot import compare_exports, sha256  # noqa: E402
from slice.content_compare import compare as content_compare  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
OCIO = ROOT / "benchmarks/bakeoff/01J7B000000000000000BAKEXP/slice/ocio/studio-config-v4.0.0_aces-v2.0_ocio-v2.5.ocio"
CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
TOL = CONV["rebuild"]["cross_platform_tolerance"]["numeric_abs"]  # the contractor builds on another machine: float noise is not a difference
BUILD_TIMEOUT_S = 6 * 3600
ASSET_CHECK_TIMEOUT_S = 7 * 24 * 3600  # a conformant run of a real asset is hours; the step decides when it is done
EXIT_OK, EXIT_FAIL, EXIT_PARTIAL, EXIT_USAGE = 0, 2, 3, 64
# What a build from the template plus MPFB2 never needs. Applied to the code tokens of each
# LOGICAL line (comments and docstrings removed, names joined by one space, strings replaced by
# STR); only *.py files are scanned. A hit is quoted and fails the run unless --allow-scan-hits
# records it and caps the verdict at PARTIAL. Bare words a legitimate script uses (`socket` as a
# variable, getattr on bpy.context, importlib.import_module — the contract's own way to find the
# MPFB2 module under any extension repo, Q11) are not matched — the forms are the module/operator ones.
BUILD_SCRIPT_FORBIDDEN = re.compile(
    r"\b(open_mainfile|read_homefile|read_factory_settings|wm\.append|wm\.link|libraries\.load"
    r"|subprocess|os\.system|os\.popen|os\.exec\w*|shutil|urllib|requests|http\.client|ftplib|ctypes|importlib\.(reload|util|machinery|resources)|__import__|exec|eval)\b"
    r"|\bimport socket\b|\bsocket\.(socket|create_connection|connect)\b|\bfrom os import\b|\bgetattr\(bpy\.ops\.wm")
PYCACHE_TREES = ("slice", "scripts", "schemas")
BLENDER_PROFILE_VARS = ("BLENDER_USER_EXTENSIONS", "BLENDER_USER_CONFIG", "BLENDER_USER_SCRIPTS", "BLENDER_USER_DATAFILES")

MPFB_PROBE = r'''
import bpy, json, sys, tomllib
from pathlib import Path
out = {"enabled": []}
for key in bpy.context.preferences.addons.keys():
    if key.rsplit(".", 1)[-1] != "mpfb":
        continue
    mod = sys.modules.get(key) or __import__(key)
    manifest = Path(mod.__file__).parent / "blender_manifest.toml"
    version = tomllib.loads(manifest.read_text())["version"] if manifest.exists() else None
    out["enabled"].append({"module": key, "version": version, "path": str(Path(mod.__file__).parent)})
print("MPFB_PROBE " + json.dumps(out))
'''


class AcceptanceError(RuntimeError):
    pass


class UsageError(RuntimeError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


class Runner:
    def __init__(self, out, env, report):
        self.out, self.env, self.report = out, env, report

    def run(self, step, cmd, timeout=3600, cwd=ROOT, must_print=None):
        t = time.time()
        log = self.out / "logs" / (re.sub(r"[^A-Za-z0-9_.-]+", "_", step) + ".log")
        log.parent.mkdir(parents=True, exist_ok=True)
        cmd = [str(c) for c in cmd]
        header = f"$ {' '.join(cmd)}\n[cwd {cwd}]\n"
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=self.env, cwd=str(cwd))
        except subprocess.TimeoutExpired as e:
            so = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            se = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
            log.write_text(header + f"[TIMEOUT after {timeout} s — partial output]\n--- stdout\n{so}\n--- stderr\n{se}")
            self.report["steps"].append({"step": step, "returncode": None, "seconds": round(time.time() - t, 1), "last_stdout": "", "last_stderr": f"timeout after {timeout} s", "log": str(log)})
            raise AcceptanceError(f"step {step} timed out after {timeout} s — partial log {log}")
        log.write_text(header + f"--- stdout\n{r.stdout}\n--- stderr\n{r.stderr}")
        lines = r.stdout.strip().splitlines() or [""]
        verdicts = [ln for ln in lines if re.search(r"_OK|_ERROR|_FAIL|checks_failed|Traceback|MPFB_PROBE", ln)]
        tail = (verdicts or lines)[-1][:300]
        err = (r.stderr.strip().splitlines() or [""])[-1][:300]
        entry = {"step": step, "returncode": r.returncode, "seconds": round(time.time() - t, 1), "last_stdout": tail, "last_stderr": err if r.returncode else "", "log": str(log)}
        self.report["steps"].append(entry)
        print(f"ACCEPTANCE_STEP {step} rc={r.returncode} {entry['seconds']}s {tail}")
        if r.returncode != 0:
            raise AcceptanceError(f"step {step} failed (rc {r.returncode}): {err or tail} — log {log}")
        if must_print and must_print not in r.stdout:
            raise AcceptanceError(f"step {step} exited 0 without printing {must_print} — log {log}")
        return r


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise AcceptanceError(f"git {' '.join(args)} in {repo}: {r.stderr.strip()[-300:]}")
    return r.stdout.strip()


def is_url(s):
    return bool(re.match(r"^(https?://|git@|ssh://|git://)", s))


def refuse_userinfo(url, what):
    """No credential may reach a log or the report (CLAUDE.md §5, .claude/rules/privacy.md):
    a URL with userinfo — https://token@host, ssh://user@host or the scp form user@host:path —
    is refused before it is used. The plain scp form git@host:path is allowed."""
    if re.search(r"://[^/@]*@", url) or (re.match(r"^[^/:]*@[^/:]+:", url) and not url.startswith("git@")):
        raise UsageError(f"{what} carries userinfo (user or token before @) — refused; use a git credential helper")


def parse_mpfb_git(spec):
    """git:<url>@<ref>. The ref is the LAST @-segment and may not contain '/' or ':'."""
    url, sep, ref = spec.rpartition("@")
    if not sep or not url or not re.fullmatch(r"[A-Za-z0-9._-]+", ref):
        raise UsageError("--mpfb git:<url>@<ref> needs a URL and a ref (tag or commit; letters, digits, . _ -)")
    refuse_userinfo(url, "--mpfb URL")
    return url, ref


TOOL_GLOBS = ("slice/**/*", "schemas/**/*", "scripts/**/*", "benchmarks/bakeoff/01J7B000000000000000BAKEXP/slice/ocio/*.ocio")


def pycache_dirs():
    return sorted(d for t in PYCACHE_TREES for d in (ROOT / t).rglob("__pycache__") if d.is_dir())


def tool_fingerprint():
    """The judges: every file under slice/, schemas/ and scripts/ and the OCIO config, by sha256,
    plus this repository's commit and whether those paths are dirty. Byte-code caches are not
    hashed: they are DELETED before the fingerprint (Blender's embedded Python ignores
    PYTHONDONTWRITEBYTECODE, so a cache can reappear legitimately only if a judge runs — none
    does between the fingerprint and the recheck), and the recheck fails if any reappeared."""
    for d in pycache_dirs():
        shutil.rmtree(d)
    paths = sorted({p for g in TOOL_GLOBS for p in ROOT.glob(g) if p.is_file() and "measurements" not in p.parts and "__pycache__" not in p.parts})
    files = {str(p.relative_to(ROOT)): sha256(p) for p in paths}
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True)
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", *PYCACHE_TREES], capture_output=True, text=True)
    return {"repo_commit": head.stdout.strip() if head.returncode == 0 else "UNKNOWN (not a git checkout)", "pycache_dirs_present": [str(d.relative_to(ROOT)) for d in pycache_dirs()],
            "tools_dirty": bool(dirty.stdout.strip()) if dirty.returncode == 0 else "UNKNOWN", "files": files}


def step0_environment(rn, args):
    rep = rn.report
    if shutil.which("blender") is None:
        raise AcceptanceError("blender is not on PATH — install Blender 5.2.1 LTS (REBUILD.md step 1)")
    if not OCIO.exists():
        raise AcceptanceError(f"vendored OCIO config missing: {OCIO}")
    r = rn.run("0 blender --version", ["blender", "--version"])
    rep["environment"]["blender"] = r.stdout.strip().splitlines()[0]
    rn.run("0 python deps", [PY, "-c", "import jsonschema, numpy"])
    rep["environment"]["python"] = PY
    rep["tools"] = tool_fingerprint()
    rn.run("0 extension repo-list (isolated profile)", ["blender", "-b", "--command", "extension", "repo-list"])


def step0_mpfb(rn, args):
    rep = rn.report["mpfb"]
    if args.mpfb == "none":
        rep["status"] = "NOT INSTALLED (--mpfb none) — verdict capped at PARTIAL"
        rep["commit_check"] = "NOT VERIFIED (nothing installed)"
        return
    kind, _, spec = args.mpfb.partition(":")
    if kind == "git":
        url, ref = parse_mpfb_git(spec)
        src = rn.out / "mpfb2_src"
        rn.run("0 mpfb clone", ["git", "clone", "-q", "--no-checkout", url, str(src)], timeout=1800)
        rn.run("0 mpfb checkout", ["git", "-C", str(src), "checkout", "-q", ref], timeout=600)
        head = git(src, "rev-parse", "HEAD")
        rep.update({"source": url, "ref": ref, "commit": head})
        if args.mpfb_commit:
            if not head.startswith(args.mpfb_commit):
                raise AcceptanceError(f"MPFB2 ref {ref} resolves to {head[:12]}, LICENSES.md declares {args.mpfb_commit}")
            rep["commit_check"] = "matches LICENSES.md"
        else:
            rep["commit_check"] = "NOT VERIFIED (no --mpfb-commit given) — verdict capped at PARTIAL"
        manifest_dir = src / "src" / "mpfb"
        if not (manifest_dir / "blender_manifest.toml").exists():
            raise AcceptanceError(f"no blender_manifest.toml under {manifest_dir}; the extension layout changed")
        zip_path = rn.out / "mpfb_extension.zip"
        rn.run("0 mpfb build extension", ["blender", "-b", "--command", "extension", "build", "--source-dir", str(manifest_dir), "--output-filepath", str(zip_path)], timeout=1800)
    elif kind == "zip":
        zip_path = Path(spec).resolve()
        if not zip_path.exists():
            raise AcceptanceError(f"--mpfb zip: {zip_path} does not exist")
        rep.update({"source": str(zip_path), "commit_check": "NOT VERIFIED (a zip carries no commit) — verdict capped at PARTIAL"})
    else:
        raise UsageError("--mpfb must be none, git:<url>@<ref> or zip:<path>")
    rep["extension_zip_sha256"] = sha256(zip_path)
    rep["extension_zip_note"] = "the zip Blender builds is not byte-reproducible (archive timestamps; two builds of the same commit measured 2026-09-16 differ) — the identity of the installed code is the source commit, the zip hash only names this run's file"
    rn.run("0 mpfb install (isolated profile)", ["blender", "-b", "--command", "extension", "install-file", "-r", "user_default", "-e", str(zip_path)], timeout=1800)
    probe = rn.out / "mpfb_probe.py"
    probe.write_text(MPFB_PROBE)
    r = rn.run("0 mpfb probe", ["blender", "-b", "--python-exit-code", "2", "-P", str(probe)], must_print="MPFB_PROBE ")
    found = json.loads(r.stdout.split("MPFB_PROBE ", 1)[1].splitlines()[0])["enabled"]
    rep["enabled"] = found
    if len(found) != 1:
        raise AcceptanceError(f"expected exactly one enabled mpfb module in the isolated profile, found {found}")
    if found[0]["version"] != args.mpfb_version:
        raise AcceptanceError(f"MPFB2 manifest version {found[0]['version']} ≠ declared --mpfb-version {args.mpfb_version}")
    rep["status"] = f"INSTALLED {found[0]['module']} {found[0]['version']}"


def step1_template(rn, args):
    rep = rn.report["template"]
    repo = args.template_repo
    if is_url(repo):
        local = rn.out / "template_repo"
        rn.run("1 template repo clone", ["git", "clone", "-q", repo, str(local)], timeout=1800)
        repo = local
    repo = Path(repo).resolve()
    commit = git(repo, "rev-parse", "--verify", f"{args.template_commit}^{{commit}}")
    src = rn.out / "template_src"
    src.mkdir(parents=True, exist_ok=True)
    tar = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", commit, "slice"], capture_output=True)
    if tar.returncode != 0:
        raise AcceptanceError(f"git archive {commit[:12]} slice: {tar.stderr.decode(errors='replace')[-300:]}")
    subprocess.run(["tar", "-x", "-C", str(src)], input=tar.stdout, check=True)
    tmpl = src / "slice" / "scene_template.py"
    if not tmpl.exists():
        raise AcceptanceError(f"{commit[:12]} has no slice/scene_template.py")
    # Provenance: the commit is named by the contractor, so the script about to run must be one
    # this repository has committed at some point (the public copy is a whitelist export of it).
    if rn.report["tools"]["repo_commit"].startswith("UNKNOWN"):
        raise AcceptanceError("provenance of the template script cannot be checked outside a git checkout of this repository")
    blob = subprocess.run(["git", "-C", str(ROOT), "hash-object", "--", str(tmpl)], capture_output=True, text=True, check=True).stdout.strip()
    known = subprocess.run(["git", "-C", str(ROOT), "log", "--all", "--format=%H", f"--find-object={blob}", "--", "slice/scene_template.py"], capture_output=True, text=True, check=True)
    rep.update({"repo": str(args.template_repo), "commit": commit, "scene_template_sha256": sha256(tmpl), "scene_template_known_in_private_history": bool(known.stdout.strip())})
    if not known.stdout.strip():
        raise AcceptanceError(f"slice/scene_template.py at {commit[:12]} of {args.template_repo} matches no version in this repository's history — not our template script")
    blend = rn.out / "template.blend"
    rn.run("1 scene_template", ["blender", "-b", "--python-exit-code", "2", "-P", str(tmpl), "--", "--out", str(blend), "--shot", args.shot], timeout=1800, cwd=rn.out, must_print="TEMPLATE_OK")
    return blend


def scan_source(src, name):
    """Hits in one Python source: forbidden forms in the code tokens of each logical line, with
    comments and docstring tokens removed and string literals replaced by STR. An unparsable
    file is itself a hit. Only what this finds is found — see BUILD_SCRIPT_FORBIDDEN."""
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError) as e:
        return [f"{name}:{getattr(e, 'lineno', None) or 0}: not valid Python ({getattr(e, 'msg', e)})"]
    doc_starts = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                doc_starts.add((first.value.lineno, first.value.col_offset))
    hits, code, first_line, prev = [], "", None, None
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.NEWLINE, tokenize.ENDMARKER):
            if code and BUILD_SCRIPT_FORBIDDEN.search(code):
                hits.append(f"{name}:{first_line}: {code.strip()[:160]}")
            code, first_line, prev = "", None, None
            continue
        if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.INDENT, tokenize.DEDENT) or tok.start in doc_starts:
            continue
        if first_line is None:
            first_line = tok.start[0]
        if tok.type in (tokenize.STRING, tokenize.FSTRING_START):
            code += " STR "
            prev = tokenize.STRING
        elif tok.type in (tokenize.FSTRING_MIDDLE, tokenize.FSTRING_END):
            continue
        elif tok.type in (tokenize.NAME, tokenize.NUMBER):
            code += (" " if prev in (tokenize.NAME, tokenize.NUMBER) else "") + tok.string
            prev = tok.type
        elif tok.type == tokenize.OP:
            code += tok.string
            prev = tok.type
    return hits


def scan_build_scripts(script_dir):
    files = sorted(p for p in script_dir.rglob("*.py"))
    hits = []
    for p in files:
        hits += scan_source(p.read_text(errors="replace"), str(p.relative_to(script_dir)))
    return {"files": [str(p.relative_to(script_dir)) for p in files], "hits": hits,
            "rule": "code tokens of each logical line against BUILD_SCRIPT_FORBIDDEN; comments and docstrings removed, strings replaced by STR; only *.py files"}


def step2_build(rn, args, template, delivered):
    build = Path(args.build).resolve()
    sandbox = rn.out / "build_sandbox"
    shutil.copytree(build.parent, sandbox, ignore=shutil.ignore_patterns("__pycache__", "*.blend", "*.blend1"))
    script = sandbox / build.name
    rebuilt = rn.out / "rebuilt.blend"
    cmd = ["blender", "-b", str(template), "--python-exit-code", "2", "-P", str(script), "--", "--out", str(rebuilt)]
    scan = scan_build_scripts(sandbox)
    copied = {str(p.relative_to(sandbox)): sha256(p) for p in sorted(sandbox.rglob("*")) if p.is_file()}
    rn.report["build"] = {"script": str(build), "script_sha256": sha256(build), "script_dir_copied_to": str(sandbox), "copied_files_sha256": copied, "script_scan": scan, "command": " ".join(cmd), "cwd": str(sandbox)}
    if scan["hits"] and not args.allow_scan_hits:
        raise AcceptanceError("build script does what a rebuild never needs (opens another .blend, spawns a process, copies files, reaches the network or resolves operators at run time): " + "; ".join(scan["hits"][:5]) + " — read the script; --allow-scan-hits runs it anyway and caps the verdict at PARTIAL")
    scan["allowed_by_operator"] = bool(scan["hits"]) and args.allow_scan_hits
    rn.run("2 build_character", cmd, timeout=BUILD_TIMEOUT_S, cwd=sandbox, must_print="BUILD_OK")
    if not rebuilt.exists():
        raise AcceptanceError(f"build printed BUILD_OK but wrote no {rebuilt}")
    reappeared = [str(d.relative_to(ROOT)) for d in pycache_dirs()]
    after = tool_fingerprint()
    changed = sorted(k for k in set(after["files"]) | set(rn.report["tools"]["files"]) if after["files"].get(k) != rn.report["tools"]["files"].get(k))
    rn.report["tools"]["recheck_after_build"] = {"changed": changed, "pycache_reappeared": reappeared}
    if changed or reappeared:
        raise AcceptanceError(f"the judging tools changed while the build script ran: files {changed}, byte-code caches {reappeared} — the repository is compromised, restore it before anything else")
    if sha256(delivered) != rn.report["delivered_sha256"]:
        raise AcceptanceError("the delivered file changed while the build script ran — the script overwrote the delivery; nothing below can be trusted")
    rn.report["build"]["delivered_unchanged_after_build"] = True
    rn.report["build"]["rebuilt_sha256"] = sha256(rebuilt)
    if rn.report["build"]["rebuilt_sha256"] == rn.report["delivered_sha256"]:
        raise AcceptanceError("the rebuilt file is a byte copy of the delivered file — a Blender save never reproduces bytes, so the script copied the delivery instead of building")
    return rebuilt


def step3_check_scene(rn, files):
    rn.report["check_scene"] = {}
    for name, blend in files.items():
        out = rn.out / f"check_scene_{name}.json"
        rn.run(f"3 check_scene {name}", ["blender", "-b", str(blend), "--python-exit-code", "2", "-P", str(ROOT / "slice/check_scene.py"), "--", "--json", str(out)])
        failed = json.loads(out.read_text()).get("checks_failed", ["report unreadable"]) if out.exists() else ["no JSON written"]
        rn.report["check_scene"][name] = {"checks_failed": failed}
        if failed:
            raise AcceptanceError(f"check_scene on the {name} file: {failed}")


def step4_asset_check(rn, args, files):
    rep = rn.report["asset_check"]
    if args.no_asset_check:
        rep["status"] = "NOT RUN (--no-asset-check) — verdict capped at PARTIAL"
        return
    samples, scale = args.asset_check
    rep.update({"samples": samples, "scale_percent": scale, "shot": args.shot, "runs": {}})
    for name, blend in files.items():
        out = rn.out / "asset_check" / name
        r = rn.run(f"4 check_asset {name}", ["bash", str(ROOT / "slice/check_asset.sh"), str(blend), str(out), str(samples), str(scale), args.shot], timeout=ASSET_CHECK_TIMEOUT_S, must_print="ASSET_CHECK_OK")
        rep["runs"][name] = {"out": str(out), "verdict": r.stdout.strip().splitlines()[-1][:300]}
    rep["status"] = f"OK on {', '.join(files)} at {samples} spp / {scale} %, {args.shot}"


def step5_exports(rn, args, files):
    dirs = {}
    for name, blend in files.items():
        d = rn.out / "exports" / name
        rn.run(f"5 export {name}", ["blender", "-b", str(blend), "--python-exit-code", "2", "-P", str(ROOT / "slice/export_shot.py"), "--", "--shot", args.shot, "--out", str(d)], timeout=1800, must_print="EXPORT_OK")
        rn.run(f"5 check_exports {name}", [PY, str(ROOT / "slice/check_exports.py"), str(d)])
        dirs[name] = d
    cmp = compare_exports(dirs["delivered"], dirs["rebuilt"], tolerance=TOL)
    rn.report["exports"] = {"rule": "slice/rebuild_shot.compare_exports with conventions.rebuild.cross_platform_tolerance", "shot": args.shot, **cmp}
    if cmp["differing"]:
        raise AcceptanceError(f"exports of the delivered and the rebuilt file differ beyond the tolerance {TOL:g}: {cmp['differing']}")
    if cmp["abc_needs_numeric_comparison"]:
        r = rn.run("5 compare proxies.abc numerically", ["blender", "-b", "--python-exit-code", "2", "-P", str(ROOT / "slice/compare_alembic.py"), "--", "--a", str(dirs["delivered"] / "proxies.abc"), "--b", str(dirs["rebuilt"] / "proxies.abc"), "--meta", str(dirs["delivered"] / "proxies.abc.meta.json"), "--tol", str(TOL)], timeout=3600, must_print="ALEMBIC_COMPARE_OK")
        rn.report["exports"]["proxies_abc"] = next(ln for ln in r.stdout.splitlines() if ln.startswith("ALEMBIC_COMPARE_OK"))
    rn.report["exports"]["status"] = "EQUAL (byte-identical)" if not cmp["within_tolerance"] and not cmp["abc_needs_numeric_comparison"] else f"EQUAL WITHIN TOLERANCE {TOL:g} (max deviation {max(list(cmp['within_tolerance'].values()) or [0.0]):.3e} in the JSON/OBJ files; proxies.abc: {rn.report['exports']['proxies_abc']})"


def step6_content_hash(rn, files):
    reps, dumps = {}, {}
    for name, blend in files.items():
        js, dp = rn.out / f"content_hash_{name}.json", rn.out / f"content_dump_{name}.json"
        rn.run(f"6 content hash {name}", ["blender", "-b", str(blend), "--python-exit-code", "2", "-P", str(ROOT / "slice/blend_content_hash.py"), "--", "--json", str(js), "--dump", str(dp)], timeout=1800, must_print="BLEND_CONTENT_HASH ")
        reps[name], dumps[name] = json.loads(js.read_text()), dp
    a, b = reps["delivered"], reps["rebuilt"]
    diff = {kind: sorted(k for k in set(a[kind]) | set(b[kind]) if a[kind].get(k) != b[kind].get(k)) for kind in ("objects", "materials", "mesh_data")}
    rn.report["content_hash"] = {"delivered": a["content_hash"], "rebuilt": b["content_hash"], "equal": a["content_hash"] == b["content_hash"], "differing": diff}
    if a["content_hash"] == b["content_hash"]:
        rn.report["content_hash"]["status"] = "EQUAL (hash)"
        return
    # Hashes differ: on another machine float noise flips the 1e-6 rounding of the hash, so the
    # canonical content is compared numerically within the declared tolerance, section by section.
    da, db = json.loads(dumps["delivered"].read_text()), json.loads(dumps["rebuilt"].read_text())
    within, failing = {}, {}
    for kind in ("objects", "materials", "mesh_data"):
        for k in diff[kind]:
            res = content_compare(da[kind].get(k), db[kind].get(k), TOL)
            if res["equal"]:
                within[f"{kind}/{k}"] = res["max_dev"]
            else:
                failing[f"{kind}/{k}"] = res["differences"][:5]
    scene_res = content_compare(da["scene"], db["scene"], TOL)
    if not scene_res["equal"]:
        failing["scene"] = scene_res["differences"][:5]
    rn.report["content_hash"].update({"within_tolerance": within, "failing": failing, "tolerance": TOL})
    if failing:
        raise AcceptanceError(f"content differs beyond the tolerance {TOL:g}: " + "; ".join(f"{k}: {v[0]}" for k, v in failing.items()))
    rn.report["content_hash"]["status"] = f"EQUAL WITHIN TOLERANCE {TOL:g} (max deviation {max(within.values()) if within else 0.0:.3e}; {len(within)} entries needed it)"


def parse_args(argv):
    p = Parser(description=__doc__.split("\n\n")[0])
    p.add_argument("--delivered", required=True, help="the contractor's character_vNN.blend")
    p.add_argument("--build", required=True, help="the contractor's build script; its directory is copied into the run directory and run from there")
    p.add_argument("--template-repo", required=True, help="path or URL of the repository the template commit lives in (the public copy)")
    p.add_argument("--template-commit", required=True, help="commit named in REPORT.md the template was built from")
    p.add_argument("--mpfb", default="none", help="none | git:<url>@<ref> | zip:<path> — MPFB2 as declared in LICENSES.md; only git with --mpfb-commit can reach OK")
    p.add_argument("--mpfb-version", default=None, help="manifest version declared in LICENSES.md (required unless --mpfb none)")
    p.add_argument("--mpfb-commit", default=None, help="commit declared in LICENSES.md; verified against the git checkout (git source only)")
    p.add_argument("--shot", default="SHOT_001")
    p.add_argument("--out", required=True, help="fresh directory; the isolated Blender profile and every intermediate live here")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--asset-check", nargs=2, type=int, metavar=("SAMPLES", "SCALE"), default=[64, 25], help="check_asset.sh settings (default 64 25)")
    g.add_argument("--no-asset-check", action="store_true", help="skip check_asset.sh; recorded, verdict at most PARTIAL")
    p.add_argument("--allow-scan-hits", action="store_true", help="run the build script although the scan hit; hits recorded, verdict at most PARTIAL")
    args = p.parse_args(argv)
    if args.mpfb != "none" and not args.mpfb_version:
        raise UsageError("--mpfb-version is required unless --mpfb none")
    if args.mpfb_commit and not args.mpfb.startswith("git:"):
        raise UsageError("--mpfb-commit can only be verified against a git source (--mpfb git:<url>@<ref>)")
    if args.mpfb.startswith("git:"):
        parse_mpfb_git(args.mpfb[4:])
    elif args.mpfb != "none" and not args.mpfb.startswith("zip:"):
        raise UsageError("--mpfb must be none, git:<url>@<ref> or zip:<path>")
    if is_url(args.template_repo):
        refuse_userinfo(args.template_repo, "--template-repo URL")
    out = Path(args.out).resolve()
    if out.exists() and any(out.iterdir()):
        raise UsageError(f"{out} is not empty — an acceptance run starts from nothing")
    delivered = Path(args.delivered).resolve()
    if not delivered.exists():
        raise UsageError(f"delivered file {delivered} does not exist")
    if not Path(args.build).exists():
        raise UsageError(f"build script {args.build} does not exist")
    build_dir = Path(args.build).resolve().parent
    if out.is_relative_to(build_dir) or build_dir.is_relative_to(out):
        raise UsageError(f"--out {out} must not lie inside the build script's directory {build_dir} (nor contain it): that directory is copied into the run")
    return args, out, delivered


def main(argv):
    args, out, delivered = parse_args(argv)
    out.mkdir(parents=True, exist_ok=True)
    profile = out / "blender_profile"
    env = dict(os.environ, OCIO=str(OCIO), CYCLES_METAL_DISABLE_BINARY_ARCHIVES="1", PYTHONDONTWRITEBYTECODE="1")
    env.pop("CHECK_ASSET_QUICK", None)  # acceptance always runs the full check_asset.sh, whatever the caller's shell has set
    for var in BLENDER_PROFILE_VARS:
        d = profile / var.removeprefix("BLENDER_USER_").lower()
        d.mkdir(parents=True)
        env[var] = str(d)
    report = {"schema_note": "contractor acceptance item 5 (rebuild); slice/accept_delivery.py", "delivered": str(delivered), "delivered_sha256": sha256(delivered),
              "shot": args.shot, "out": str(out), "args": vars(args),
              "environment": {"isolated_blender_profile": str(profile), "profile_vars": {v: env[v] for v in BLENDER_PROFILE_VARS}, "OCIO": str(OCIO), "CYCLES_METAL_DISABLE_BINARY_ARCHIVES": "1"},
              "tools": {}, "mpfb": {}, "template": {}, "build": {}, "check_scene": {}, "asset_check": {}, "exports": {}, "content_hash": {},
              "steps": [], "status": "RUNNING"}
    report_path = out / "acceptance_report.json"
    rn = Runner(out, env, report)
    code = EXIT_FAIL
    try:
        step0_environment(rn, args)
        step0_mpfb(rn, args)
        template = step1_template(rn, args)
        rebuilt = step2_build(rn, args, template, delivered)
        files = {"delivered": delivered, "rebuilt": rebuilt}
        step3_check_scene(rn, files)
        step4_asset_check(rn, args, files)
        step5_exports(rn, args, files)
        step6_content_hash(rn, files)
        partial = []
        if args.no_asset_check:
            partial.append("check_asset.sh NOT RUN")
        if "NOT VERIFIED" in report["mpfb"]["commit_check"]:
            partial.append(f"MPFB2 {report['mpfb']['status'].split(' — ')[0]}, commit {report['mpfb']['commit_check'].split(' — ')[0]}")
        if report["build"]["script_scan"]["allowed_by_operator"]:
            partial.append(f"build script scan hits allowed by the operator: {len(report['build']['script_scan']['hits'])}")
        report["partial_reasons"] = partial
        if partial:
            report["status"] = f"PARTIAL — rebuilt, check_scene clean, exports {report['exports']['status']}, content {report['content_hash']['status']}; " + "; ".join(partial)
            code = EXIT_PARTIAL
        else:
            report["status"] = f"OK — rebuilt from the build script with MPFB2 at the declared commit; check_scene and check_asset passed on both files; exports {report['exports']['status']}; content {report['content_hash']['status']}"
            code = EXIT_OK
    except UsageError:
        report["status"] = "NOT RUN (usage error)"
        raise
    except AcceptanceError as e:
        report["status"], report["error"] = "FAIL", str(e)
        print(f"ACCEPTANCE_REBUILD_FAIL: {e}")
        print(f"ACCEPTANCE_REBUILD_FAIL: {e}", file=sys.stderr)
    except Exception:  # noqa: BLE001 — a crash is a FAIL with its traceback, never a report left at RUNNING
        report["status"], report["error"] = "FAIL (unhandled exception)", traceback.format_exc()
        print(f"ACCEPTANCE_REBUILD_FAIL: unhandled exception, traceback in {report_path}")
        print(f"ACCEPTANCE_REBUILD_FAIL: unhandled exception, traceback in {report_path}", file=sys.stderr)
    finally:
        report_path.write_text(json.dumps(report, indent=1) + "\n")
    h = report["content_hash"].get("delivered", "")[:16]
    if code == EXIT_PARTIAL:
        print(f"ACCEPTANCE_REBUILD_PARTIAL {delivered.name} hash={h} — {'; '.join(report['partial_reasons'])} -> {report_path}")
    elif code == EXIT_OK:
        print(f"ACCEPTANCE_REBUILD_OK {delivered.name} hash={h} steps={len(report['steps'])} -> {report_path}")
    return code


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except UsageError as e:
        print(f"usage error: {e}", file=sys.stderr)
        sys.exit(EXIT_USAGE)
