"""Print the FastAPI OpenAPI JSON to stdout.

Used by `make openapi` to regenerate `packages/api-spec/openapi.json`.

Any logs emitted during import (structlog renderer, OTEL init) are
redirected to stderr so only the JSON hits stdout — callers pipe the
output straight into a file.
"""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    os.environ.setdefault("PLATFORM_SECRET_KEY", "x" * 64)

    # Structlog's dev renderer + the otel.init_tracing.stubbed message
    # would otherwise write to stdout during import, corrupting the JSON
    # that gets piped into packages/api-spec/openapi.json. Swap stdout
    # for stderr for the duration of the import and the app factory call.
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        from aipacken.main import create_app

        app = create_app()
    finally:
        sys.stdout = real_stdout

    json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
