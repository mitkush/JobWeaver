"""One isolated JobSpy search. The API process never imports pandas or blocking clients."""

import contextlib
import io
import json
import sys
from collections.abc import Callable
from time import monotonic
from typing import Any


def collect(
    payload: dict[str, Any], emit: Callable[[dict[str, Any]], None] | None = None
) -> dict[str, Any]:
    from jobspy import scrape_jobs

    deadline = monotonic() + payload.get("time_budget", 895)
    limit = payload.get("max_results", 50)
    jobs: list[dict[str, Any]] = []
    error = False
    complete = False
    # Collect one public LinkedIn page at a time and checkpoint it immediately. If a
    # later page stalls, the parent can kill us without losing completed pages.
    for offset in range(0, limit, 25):
        if monotonic() >= deadline:
            error = True
            break
        wanted = min(25, limit - offset)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                frame = scrape_jobs(
                    site_name=["linkedin"],
                    search_term=payload["keywords"],
                    location=payload["location"],
                    hours_old=payload["hours_old"],
                    results_wanted=wanted,
                    offset=offset,
                    fetch_description=True,
                    description_format="plain",
                    proxies=payload.get("proxies") or None,
                    verbose=0,
                )
            rows = json.loads(frame.to_json(orient="records", date_format="iso"))
        except Exception:
            error = True
            break
        jobs.extend(rows)
        # LinkedIn uses fail() for search errors but only logs most warnings. Keep the
        # rows returned alongside an error; do not rely on attrs['warnings'].
        error = bool(frame.attrs.get("errors"))
        if emit:
            emit({"jobs": rows, "error": error, "complete": False})
        if error:
            break
        if len(rows) < wanted:
            complete = True
            break
    return {"jobs": jobs, "error": error, "complete": complete}


def main() -> None:
    def emit(frame: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(frame) + "\n")
        sys.stdout.flush()

    try:
        result = collect(json.load(sys.stdin), emit)
    except Exception:
        # Library errors can include proxy credentials. Only this safe protocol goes
        # back to the parent; library stderr is discarded there as well.
        result = {"error": True, "complete": False}
    # Rows were already checkpointed. The last frame only reports completion.
    emit({"jobs": [], "error": result["error"], "complete": result["complete"]})


if __name__ == "__main__":
    main()
