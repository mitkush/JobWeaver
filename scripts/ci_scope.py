"""Select PR checks conservatively. Main always runs everything."""
import json
import os
import subprocess


def scope(paths: list[str], *, full: bool = False) -> dict[str, bool]:
    result = dict.fromkeys(("backend", "frontend", "extension", "docker"), full)
    for path in paths:
        if path.startswith("backend/"):
            # Backend schemas also supply generated frontend types.
            result.update(backend=True, frontend=True, docker=True)
        elif path.startswith("frontend/"):
            result.update(frontend=True, docker=True)
        elif path.startswith("extension/"):
            result["extension"] = True
        elif path.startswith("jobweaver-docs/") or path in {"README.md", "CLAUDE.md", "prd-prompt.md"}:
            continue
        else:
            # Workflows, build context, scripts and unknown paths fail open to full checks.
            result = dict.fromkeys(result, True)
    return result


if __name__ == "__main__":
    event = json.loads(open(os.environ["GITHUB_EVENT_PATH"]).read())
    full = os.environ["GITHUB_EVENT_NAME"] != "pull_request"
    paths = []
    if not full:
        pr = event["pull_request"]
        paths = subprocess.check_output(
            ["git", "diff", "--name-only", "-z", f"{pr['base']['sha']}...{pr['head']['sha']}"],
        ).decode().split("\0")
        paths = [path for path in paths if path]
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        for key, value in scope(paths, full=full).items():
            output.write(f"{key}={str(value).lower()}\n")
