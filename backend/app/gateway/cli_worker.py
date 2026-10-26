"""Standalone, stdlib-only gateway worker. Run in its own capped, secret-only container."""

import hmac
import json
import os
import resource
import select
import signal
import socket
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CLI = "/opt/claude"
WORK_DIR = "/work"
MAX_REQUEST_BYTES = 128_000
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
CLI_TIMEOUT_SECONDS = 55
_LOCK = threading.Lock()


class WorkerFailure(Exception):
    pass


def command(system_file: str) -> list[str]:
    return [
        CLI,
        "--restricted",
        "-p",
        "--tools",
        "",
        "--disallowedTools",
        "*",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--setting-sources",
        "",
        "--no-session-persistence",
        "--output-format",
        "stream-json",
        "--verbose",
        "--max-turns",
        "1",
        "--model",
        "sonnet",
        "--effort",
        "low",
        "--system-prompt-file",
        system_file,
    ]


def completion(stream: str) -> dict:
    events = []
    for line in stream.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), {})
    if init.get("tools") != []:
        raise WorkerFailure("tools_not_disabled")
    for event in events:
        if event.get("type") == "assistant":
            blocks = event.get("message", {}).get("content", [])
            if any(isinstance(b, dict) and b.get("type") == "tool_use" for b in blocks):
                raise WorkerFailure("unexpected_tool_call")
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    if result.get("is_error", True) or result.get("subtype") != "success":
        raise WorkerFailure("cli_failed")
    text, model = result.get("result"), init.get("model")
    if not isinstance(text, str) or not text or not isinstance(model, str) or not model:
        raise WorkerFailure("invalid_output")
    usage = result.get("usage", {})
    counts = [
        usage.get(k, 0)
        for k in [
            "input_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
            "output_tokens",
        ]
    ]
    if any(type(n) is not int or n < 0 for n in counts):
        raise WorkerFailure("invalid_usage")
    return {
        "text": text,
        "model": model,
        "input_tokens": sum(counts[:3]),
        "output_tokens": counts[3],
    }


def child_limits() -> None:
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT_BYTES, MAX_OUTPUT_BYTES))


def terminate(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=2)
    except ProcessLookupError:
        process.wait(timeout=2)


def generate(system: str, user: str, disconnected=lambda: False) -> dict:
    if not _LOCK.acquire(blocking=False):
        raise WorkerFailure("busy")
    try:
        with tempfile.TemporaryDirectory(prefix="draft-", dir=WORK_DIR) as directory:
            root = Path(directory)
            home = root / "home"
            home.mkdir()
            rules = root / "system.txt"
            rules.write_text(system)
            # Explicit allowlist: no app secrets, API keys, hooks or worker key reach the CLI.
            env = {
                "HOME": str(home),
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "LANG": "C.UTF-8",
                "DISABLE_AUTOUPDATER": "1",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                "CLAUDE_CODE_OAUTH_TOKEN": os.environ["CLAUDE_CODE_OAUTH_TOKEN"],
            }
            with (root / "stdout").open("w") as out, (root / "stderr").open("w") as err:
                process = subprocess.Popen(
                    command(str(rules)),
                    cwd=root,
                    env=env,
                    stdin=subprocess.PIPE,
                    stdout=out,
                    stderr=err,
                    text=True,
                    start_new_session=True,
                )
                deadline = time.monotonic() + CLI_TIMEOUT_SECONDS
                data = user
                try:
                    while True:
                        if disconnected():
                            raise WorkerFailure("cancelled")
                        if time.monotonic() >= deadline:
                            raise WorkerFailure("timeout")
                        try:
                            process.communicate(data, timeout=0.25)
                            break
                        except subprocess.TimeoutExpired:
                            data = None
                    if process.returncode:
                        raise WorkerFailure("cli_failed")
                finally:
                    terminate(process)
            return completion((root / "stdout").read_text())
    except OSError as exc:
        raise WorkerFailure("process_failed") from exc
    finally:
        _LOCK.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "JobWeaverWorker"
    key = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *args):
        pass  # No request bodies, headers, CLI output or credentials in access logs.

    def reply(self, code, body):
        encoded = json.dumps(body).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        self.reply(200 if self.path == "/health" else 404, {"status": "ok"})

    def disconnected(self):
        if select.select([self.connection], [], [], 0)[0]:
            return self.connection.recv(1, socket.MSG_PEEK) == b""
        return False

    def do_POST(self):
        if self.path != "/complete":
            self.reply(404, {"error": "not_found"})
            return
        if not hmac.compare_digest(
            self.headers.get("Authorization", "").encode(), f"Bearer {self.key}".encode()
        ):
            self.reply(401, {"error": "unauthorized"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_REQUEST_BYTES:
                self.reply(413, {"error": "request_too_large"})
                return
            body = json.loads(self.rfile.read(size))
            system, user = body["system"], body["user"]
            if not isinstance(system, str) or not isinstance(user, str) or not system or not user:
                raise ValueError
        except (ValueError, TypeError, KeyError):
            self.reply(400, {"error": "invalid_request"})
            return
        try:
            self.reply(200, generate(system, user, self.disconnected))
        except WorkerFailure as exc:
            self.reply(503, {"error": str(exc)})


def main():
    child_limits()
    Handler.key = os.environ.get("CLAUDE_CODE_WORKER_KEY", "")
    if len(Handler.key) < 32 or not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        raise SystemExit("Private worker authentication is missing")
    server = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
