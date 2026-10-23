"""One isolated JobSpy search. The API process never imports pandas or blocking clients."""

import contextlib
import io
import json
import sys
from typing import Any


def collect(payload: dict[str, Any]) -> dict[str, Any]:
    from jobspy import scrape_jobs

    # JobSpy reports search errors in DataFrame.attrs instead of raising. A blocked
    # search must not look like a successful empty search and advance a watermark.
    with contextlib.redirect_stdout(io.StringIO()):
        frame = scrape_jobs(
            site_name=["linkedin"],
            search_term=payload["keywords"],
            location=payload["location"],
            hours_old=payload["hours_old"],
            results_wanted=1000,
            fetch_description=True,
            description_format="plain",
            proxies=payload.get("proxies") or None,
            verbose=0,
        )
    if frame.attrs.get("errors") or frame.attrs.get("warnings"):
        return {"error": "LinkedIn search was blocked or incomplete"}
    return {"jobs": json.loads(frame.to_json(orient="records", date_format="iso"))}


def main() -> None:
    try:
        result = collect(json.load(sys.stdin))
    except Exception:
        # Library errors can include proxy credentials. Only this safe protocol goes
        # back to the parent; library stderr is discarded there as well.
        result = {"error": "JobSpy could not complete the LinkedIn search"}
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
