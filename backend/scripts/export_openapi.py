"""Writes the OpenAPI schema so the frontend can generate its types without a running server."""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("SCHEDULER_ENABLED", "false")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi.json")
target.write_text(json.dumps(app.openapi(), indent=2) + "\n")
print(f"wrote {target}")
