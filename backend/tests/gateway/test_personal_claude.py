import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.errors import GatewayError
from app.gateway import cli_worker, personal
from app.gateway.claude_code import ClaudeCodeClient
from app.gateway.live import LiveAIGateway
from app.gateway.progress import draft_progress
from app.gateway.providers import Completion
from app.gateway.quota import UsageLedger
from app.models import AIUsage
from tests.gateway.test_draft_tasks import request
from tests.gateway.test_live_gateway import FakeClient


def enable(monkeypatch, owner):
    for key, value in {
        "CLAUDE_CODE_ENABLED": "true",
        "CLAUDE_CODE_OWNER_ID": str(owner),
        "CLAUDE_CODE_WORKER_KEY": "k" * 32,
        "CLAUDE_CODE_CONSENT_VERSION": "1",
        "CLAUDE_CODE_CONSENT_ACCEPTED_AT": datetime.now(UTC).isoformat(),
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


def raw():
    return json.loads(
        (Path(get_settings().gateway_recorded_dir) / "tailor_draft" / "success.json").read_text()
    )["output"]


@pytest.mark.parametrize(
    "change", ["disabled", "other_user", "old_notice", "no_date", "future_date"]
)
def test_owner_and_explicit_consent_required(monkeypatch, change):
    owner = uuid.uuid4()
    enable(monkeypatch, owner)
    assert personal.allowed(owner)
    values = {
        "disabled": ("CLAUDE_CODE_ENABLED", "false"),
        "old_notice": ("CLAUDE_CODE_CONSENT_VERSION", "old"),
        "no_date": ("CLAUDE_CODE_CONSENT_ACCEPTED_AT", None),
        "future_date": (
            "CLAUDE_CODE_CONSENT_ACCEPTED_AT",
            (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        ),
    }
    if change == "other_user":
        owner = uuid.uuid4()
    else:
        key, value = values[change]
        if value is None:
            monkeypatch.delenv(key)
        else:
            monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    assert not personal.allowed(owner)


async def test_owner_uses_claude_with_real_model_attribution_and_progress(alice, monkeypatch, db):
    user, _ = alice
    enable(monkeypatch, user.id)

    class Claude:
        async def complete_json(self, *args):
            return Completion(raw(), 100, 50, model="actual-claude-model")

    gemini = FakeClient("gemini", [raw()])
    gateway = LiveAIGateway(
        {"claude-code": Claude(), "gemini": gemini}, UsageLedger(get_sessionmaker())
    )
    providers = []

    async def update(provider):
        providers.append(provider)

    with draft_progress(update):
        result = await gateway.tailor_draft(request(user.id))
    assert result.provider == "claude-code" and result.model == "actual-claude-model"
    assert providers == ["claude-code"]
    assert gemini.calls == []
    usage = await db.scalar(select(AIUsage).where(AIUsage.provider == "claude-code"))
    assert usage.user_id == user.id and usage.model == "actual-claude-model"
    assert (usage.input_tokens, usage.output_tokens) == (100, 50)


async def test_claude_failure_falls_back_and_other_users_never_contact_it(alice, bob, monkeypatch):
    user, _ = alice
    enable(monkeypatch, user.id)
    claude = FakeClient("claude-code", [GatewayError("unavailable")])
    gemini = FakeClient("gemini", [raw(), raw()])
    gateway = LiveAIGateway(
        {"claude-code": claude, "gemini": gemini}, UsageLedger(get_sessionmaker())
    )
    assert (await gateway.tailor_draft(request(user.id))).provider == "gemini"
    # A distinct ID cannot reach this subscription; no caller-selectable route exists.
    assert (await gateway.tailor_draft(request(bob[0].id))).provider == "gemini"
    assert len(claude.calls) == 1


async def test_claude_is_never_used_for_synchronous_chat(alice, monkeypatch):
    from app.gateway.recorded import RecordedAIGateway
    from app.gateway.schemas import ReviseDraftRequest

    user, _ = alice
    enable(monkeypatch, user.id)
    body = request(user.id)
    original = await RecordedAIGateway(Path(get_settings().gateway_recorded_dir)).tailor_draft(body)
    claude = FakeClient("claude-code", [])
    gateway = LiveAIGateway(
        {"claude-code": claude, "gemini": FakeClient("gemini", [raw()])},
        UsageLedger(get_sessionmaker()),
    )
    await gateway.revise_draft(
        ReviseDraftRequest(**body.model_dump(), content=original.result.content, message="Shorten")
    )
    assert claude.calls == []


async def test_worker_transport_never_returns_raw_auth_errors():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(401, text="private-token-and-account")
        )
    ) as http:
        client = ClaudeCodeClient("http://worker", "secret", http)
        with pytest.raises(GatewayError) as exc:
            await client.complete_json("sonnet", "rules", "facts", 8192)
        assert "private-token" not in exc.value.message


def stream(*, tools=None, error=False, tool_call=False):
    return "\n".join(
        json.dumps(e)
        for e in [
            {
                "type": "system",
                "subtype": "init",
                "tools": tools or [],
                "model": "actual-claude-model",
            },
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "name": "Bash"}] if tool_call else []},
            },
            {
                "type": "result",
                "subtype": "success",
                "is_error": error,
                "result": "{}",
                "usage": {
                    "input_tokens": 2,
                    "cache_read_input_tokens": 40,
                    "cache_creation_input_tokens": 3,
                    "output_tokens": 10,
                },
            },
        ]
    )


def test_worker_counts_cached_input_and_rejects_tools_or_failed_runs():
    result = cli_worker.completion(stream())
    assert result["input_tokens"] == 45 and result["output_tokens"] == 10
    for text in [stream(tools=["Bash"]), stream(tool_call=True), stream(error=True), "garbage"]:
        with pytest.raises(cli_worker.WorkerFailure):
            cli_worker.completion(text)


def test_fixed_command_disables_tools_and_discovery():
    args = cli_worker.command("/work/rules")
    assert args[args.index("--tools") + 1] == ""
    assert args[args.index("--disallowedTools") + 1] == "*"
    assert "--restricted" in args and "--strict-mcp-config" in args
    assert args[args.index("--setting-sources") + 1] == ""
    assert not any("skip-permissions" in a for a in args)


def test_worker_uses_minimal_environment_and_removes_transcripts(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(cli_worker, "WORK_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "synthetic-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-reach-cli")
    monkeypatch.setenv("DATABASE_URL", "must-not-reach-cli")
    monkeypatch.setenv("CLAUDE_CODE_WORKER_KEY", "must-not-reach-cli")
    code = (
        "import os; assert not any(k in os.environ for k in "
        "['ANTHROPIC_API_KEY','DATABASE_URL','CLAUDE_CODE_WORKER_KEY']); print("
        + repr(stream())
        + ")"
    )
    monkeypatch.setattr(cli_worker, "command", lambda path: [sys.executable, "-c", code])
    result = cli_worker.generate("rules", "facts")
    assert result["model"] == "actual-claude-model"
    assert list(tmp_path.iterdir()) == []
    monkeypatch.setattr(
        cli_worker, "command", lambda path: [sys.executable, "-c", "raise SystemExit(1)"]
    )
    for _ in range(2):
        with pytest.raises(cli_worker.WorkerFailure, match="cli_failed"):
            cli_worker.generate("rules", "facts")
        assert list(tmp_path.iterdir()) == []


def test_worker_cancels_process_group_and_rejects_concurrent_work(tmp_path, monkeypatch):
    import sys
    import time

    monkeypatch.setattr(cli_worker, "WORK_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "synthetic-token")
    monkeypatch.setattr(cli_worker, "CLI_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(
        cli_worker, "command", lambda path: [sys.executable, "-c", "import time; time.sleep(20)"]
    )
    started = time.monotonic()
    with pytest.raises(cli_worker.WorkerFailure, match="timeout"):
        cli_worker.generate("rules", "facts")
    assert time.monotonic() - started < 3
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(cli_worker.WorkerFailure, match="cancelled"):
        cli_worker.generate("rules", "facts", disconnected=lambda: True)
    assert list(tmp_path.iterdir()) == []
    cli_worker._LOCK.acquire()
    try:
        with pytest.raises(cli_worker.WorkerFailure, match="busy"):
            cli_worker.generate("rules", "facts")
    finally:
        cli_worker._LOCK.release()


async def test_worker_http_requires_key_and_checks_input_before_dispatch(monkeypatch):
    import threading
    from http.server import ThreadingHTTPServer

    monkeypatch.setattr(cli_worker.Handler, "key", "synthetic-service-key")
    called = []

    def generate(system, user, disconnected):
        called.append((system, user))
        return {"text": "{}", "model": "model", "input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(cli_worker, "generate", generate)
    server = ThreadingHTTPServer(("127.0.0.1", 0), cli_worker.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{server.server_port}") as http:
            assert (
                await http.post("/complete", json={"system": "rules", "user": "facts"})
            ).status_code == 401
            headers = {"Authorization": "Bearer synthetic-service-key"}
            assert (
                await http.post("/complete", headers=headers, json={"system": [], "user": "facts"})
            ).status_code == 400
            assert (
                await http.post(
                    "/complete", headers=headers, content="x" * (cli_worker.MAX_REQUEST_BYTES + 1)
                )
            ).status_code == 413
            assert called == []
            response = await http.post(
                "/complete", headers=headers, json={"system": "rules", "user": "facts"}
            )
            assert response.status_code == 200
            assert called == [("rules", "facts")]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
