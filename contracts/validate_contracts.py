#!/usr/bin/env python3
"""P0 contract validator. Nur lesend, nur Standardbibliothek + jsonschema.

Nutzung:
  python validate_contracts.py asset    <datei.json>
  python validate_contracts.py refset   <datei.json>
  python validate_contracts.py project  <datei.json>
  python validate_contracts.py selftest
      # prueft examples/ (valid_* muessen passen, invalid_* muessen scheitern)

Exit 0 = ok, 1 = Verstoss.
"""
import hashlib
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parent
SCHEMAS = {
    "asset": "asset-manifest.schema.json",
    "refset": "reference-set.schema.json",
    "project": "project-manifest.schema.json",
    "layout": "layout-spec.schema.json",
}
PERSON_VIEWS_MIN = {"front", "profile", "three_quarter"}


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def refset_hash(members):
    lines = [f"{m['asset_id']}:{m['sha256']}" for m in sorted(members, key=lambda m: m["asset_id"])]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def validate(kind, doc):
    schema = load(HERE / SCHEMAS[kind])
    errors = [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
              for e in Draft202012Validator(schema).iter_errors(doc)]
    if kind == "refset" and not errors:
        if doc["set_sha256"] != refset_hash(doc["members"]):
            errors.append("set_sha256 stimmt nicht mit den Members ueberein")
        if doc["lock_type"] == "PERSON_LOCK":
            views = {m.get("view") for m in doc["members"]}
            missing = PERSON_VIEWS_MIN - views
            if missing:
                errors.append(f"PERSON_LOCK-Set ohne Pflichtansichten: {sorted(missing)}")
    return errors


def selftest():
    ok = True
    for f in sorted((HERE / "examples").glob("*.json")):
        kind = f.name.split("_", 2)[1]  # valid_asset_xxx.json
        expect_valid = f.name.startswith("valid_")
        errs = validate(kind, load(f))
        good = (not errs) == expect_valid
        ok &= good
        suffix = "" if good or not errs else f"  -> {errs[0]}"
        print(f"{'PASS' if good else 'FAIL'}  {f.name}" + suffix)
    return ok


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "selftest":
        sys.exit(0 if selftest() else 1)
    if len(sys.argv) != 3 or sys.argv[1] not in SCHEMAS:
        print(__doc__)
        sys.exit(2)
    errs = validate(sys.argv[1], load(sys.argv[2]))
    for e in errs:
        print("VERSTOSS:", e)
    print("OK" if not errs else f"{len(errs)} Verstoss/Verstoesse")
    sys.exit(1 if errs else 0)
