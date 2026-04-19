"""Print the FastAPI OpenAPI JSON to stdout.

Used by `make openapi` to regenerate `packages/api-spec/openapi.json`.
"""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    os.environ.setdefault("PLATFORM_SECRET_KEY", "x" * 64)
    from aipacken.main import create_app

    app = create_app()
    json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
