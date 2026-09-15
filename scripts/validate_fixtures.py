"""Validate every fixture under fixtures/ against the schema of the same name.

Exit 0: every fixture in fixtures/<entity>/ validates AND every fixture in
fixtures/_invalid/<entity>/ is rejected. Exit 1 otherwise. Exit 2 on loading errors.
"""
from __future__ import annotations

import json
import sys
from collections import namedtuple
from pathlib import Path
from typing import Iterator

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

Failure = namedtuple("Failure", "entity path expect_valid message")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMAS = ROOT / "schemas"
DEFAULT_FIXTURES = ROOT / "fixtures"


def _registry(schemas_dir: Path) -> tuple[Registry, dict[str, dict]]:
    """Load every schema's raw JSON plus the Registry that resolves their $refs.

    Shared by load_schemas() and by tests that need a validator built without
    the default FormatChecker but resolving against the same schema set.
    """
    raw = {p.stem: json.loads(p.read_text()) for p in sorted(schemas_dir.glob("*.json"))}
    resources = [(s["$id"], Resource.from_contents(s)) for s in raw.values() if "$id" in s]
    registry = Registry().with_resources(resources)
    return registry, raw


def load_schemas(schemas_dir: Path) -> dict[str, Draft202012Validator]:
    registry, raw = _registry(schemas_dir)
    checker = FormatChecker()
    return {
        name: Draft202012Validator(schema, registry=registry, format_checker=checker)
        for name, schema in raw.items()
    }


def _entity_for(path: Path, fixtures_dir: Path) -> str:
    rel = path.relative_to(fixtures_dir)
    parts = rel.parts
    if parts[0] == "_invalid":
        return parts[1]
    if parts[0] == "bakeoff_dry_run":
        return path.name.split(".")[0]
    return parts[0]


def iter_fixtures(fixtures_dir: Path) -> Iterator[tuple[str, Path, bool]]:
    for path in sorted(fixtures_dir.rglob("*.json")):
        rel = path.relative_to(fixtures_dir).parts
        expect_valid = rel[0] != "_invalid"
        yield _entity_for(path, fixtures_dir), path, expect_valid


def validate_instances(
    validators: dict[str, Draft202012Validator], fixtures_dir: Path
) -> tuple[list[Failure], int]:
    """Validate every fixture against already-loaded validators. Never raises for
    fixture-shaped problems (bad JSON, missing schema) — those become Failures — but a
    genuine bug in this loop (e.g. a broken validator object) is not caught here."""
    failures: list[Failure] = []
    total = 0
    for entity, path, expect_valid in iter_fixtures(fixtures_dir):
        total += 1
        if entity not in validators:
            failures.append(Failure(entity, path, expect_valid, f"no schema named {entity}.json"))
            continue
        try:
            instance = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            failures.append(Failure(entity, path, expect_valid, f"not JSON: {exc}"))
            continue
        errors = sorted(validators[entity].iter_errors(instance), key=lambda e: list(e.path))
        if expect_valid and errors:
            msg = "; ".join(f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors[:3])
            failures.append(Failure(entity, path, True, msg))
        elif not expect_valid and not errors:
            failures.append(Failure(entity, path, False, "expected rejection but validated"))
    return failures, total


def validate_all(schemas_dir: Path, fixtures_dir: Path) -> tuple[list[Failure], int]:
    """Convenience wrapper: load schemas (may raise) then validate every fixture."""
    validators = load_schemas(schemas_dir)
    return validate_instances(validators, fixtures_dir)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    schemas_dir = Path(argv[0]) if len(argv) > 0 else DEFAULT_SCHEMAS
    fixtures_dir = Path(argv[1]) if len(argv) > 1 else DEFAULT_FIXTURES
    if not schemas_dir.is_dir() or not fixtures_dir.is_dir():
        print("usage: validate_fixtures.py [schemas_dir] [fixtures_dir]", file=sys.stderr)
        return 2
    try:
        validators = load_schemas(schemas_dir)
    except Exception as exc:  # loading/registry errors are exit 2, not silent
        print(f"ERROR loading schemas: {exc}", file=sys.stderr)
        return 2
    # Not wrapped in try/except: a genuine bug in validation should raise, not be
    # swallowed as a loading error.
    failures, total = validate_instances(validators, fixtures_dir)
    for f in failures:
        kind = "SHOULD-PASS" if f.expect_valid else "SHOULD-FAIL"
        print(f"FAIL [{kind}] {f.entity} {f.path.relative_to(fixtures_dir)}: {f.message}")
    print(f"{total - len(failures)}/{total} fixtures behaved as expected")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
