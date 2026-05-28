"""
export_openapi.py — Dump the FastAPI OpenAPI spec to backend/openapi.json.

Run this whenever a backend schema or route changes. The frontend's
`npm run gen:types` consumes the resulting JSON to regenerate
`src/lib/api-types.gen.ts`, making the API contract a build-time check.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.main import app  # noqa: E402


def main() -> None:
    spec = app.openapi()
    out = Path(__file__).resolve().parent.parent / "backend" / "openapi.json"
    out.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}  ({len(spec.get('paths', {}))} paths, "
          f"{len(spec.get('components', {}).get('schemas', {}))} schemas)")


if __name__ == "__main__":
    main()
