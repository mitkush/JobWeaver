# Personal Claude Code provider

The optional provider connects the existing background Generate Draft action to an isolated
official Claude Code CLI. It is disabled by default. Only the configured internal User ID
with an explicit operator-recorded acceptance can use it. Other Users and synchronous Draft
Chat keep the existing routes. No public subscription-login UI or credential collection exists.

## What was measured

On 26 October 2026, the production VM (956 MB RAM) was tested with synthetic data only:

| Test | Container cap | Time | Result |
| --- | --- | --- | --- |
| Traced synthetic Draft, 23 fabricated Facts | 192 MiB | 93.1 s including cleanup | Timed out |
| Tiny untraced READY control | 256 MiB | 14.2 s | Success, subscription accepted |
| Traced synthetic Draft | 256 MiB | 28.6 s | Success |
| Traced malicious-JD variant | 256 MiB | 22.8 s | Success, no tool calls or sensitive-path accesses |

CLI version 2.1.308 resolved sonnet to claude-sonnet-5-5 in these tests. Peak charged cgroup
memory reached each cap, without OOM kills. The 192 MiB failure did not establish that Claude
could not run on the server; increasing the cap changed the result. Charge includes the
Python harness, tracer, CLI, file cache and tmpfs. Host and sandbox API connectivity worked.
The app health endpoint stayed healthy, and all probe containers were removed.

The trace checked attempted reads of synthetic canary/SSH/app/DB paths and shell execution;
no real production files were mounted. Tools and MCP were absent from CLI initialization.
These synthetic tests do not guarantee all resumes fit or establish a long-term capacity
benchmark. The deployment helper keeps the tested 256 MiB whole-container limit and no swap.
Monitor PostgreSQL/application latency and worker OOM/restarts after enabling. A 4 GB+ RAM
machine remains the vendor's documented requirement, despite this smaller bounded experiment.

## Private setup after merging and deploying the app

1. Use the official claude setup-token flow. Do not post the token in chat or issues.
   Create ~/.local/share/jobweaver-claude with mode 700 on the VM. Place the checksum-verified
   official linux-x64 2.1.308 binary at claude there (mode 555). The verified spike artifact
   can be copied locally on the VM; no installer or auto-updater needs to run in the app.
2. Create worker.env there, mode 600, from deployment/claude-worker.env.example. Supply the
   private subscription token and a newly generated random service key of at least 32 chars.
   The service key is separate from the subscription token. Never bake either into an image.
3. Review this disclosure before enabling: approved Facts and the job description will be
   processed through your consumer Claude account; its limits, extra-usage choices and
   privacy/training settings apply. Existing Fact checks reduce unsupported claims but cannot
   prove every sentence. Record your explicit acceptance time (timezone required), internal
   User UUID and notice version 1 in private backend/.env using deployment/claude-app.env.example.
   This is a private operator-maintained consent record, not automatic acceptance from a token
   or a global notice change. Keep the normal AI notice and region checks. Other Users do not
   need to reaccept a notice for a route they cannot use.
4. Run bash scripts/run-claude-worker.sh. It starts a separate unprivileged, capped container
   on jobweaver-net, without a published host port or production data mounts. It only exposes
   an internal authenticated completion endpoint. The helper refuses an existing worker or
   a wrong CLI hash. Check its health through docker exec or from the application network.
5. Set CLAUDE_CODE_ENABLED=true in the private app environment and recreate the app using
   the normal deployment. Verify the owner sees Trying Claude, then a completed Draft and
   a claude-code ai_usage row with the actual model. Explicitly request the first real Draft;
   setup and CI never generate a real application automatically.

Generation gives Claude a 60-second route; the CLI has 55 seconds plus cleanup and the HTTP
transport 59. Owner generation gets 210 seconds overall, allowing Claude plus the existing
45/30/30/30-second fallback routes. Other Users retain 150 seconds. Requirements extraction
stays a separate 90-second phase; Draft Chat stays at 20 seconds per route and 90 overall.
If Claude is busy, unauthenticated, invalid, unreachable or fails its deadline, current
providers remain fallbacks. A disconnected app request terminates the CLI process group.
The official CLI controls its output allowance; the gateway's output-token argument cannot
set that through this CLI interface. Time/file-size limits and output validation still apply.

The worker runs one invocation at a time. It passes a fixed executable/flag list, an explicit
minimal environment, no tools, no MCP, no session persistence and a temporary working/config
home. Subscription tokens reach only the worker/official CLI, not the web container. Its
stdout and stderr are temporary and never logged. Cached input counts are included in usage;
no CLI dollar estimate is presented as a subscription bill. The image's Python worker is
stdlib-only and lives inside app/gateway to retain ADR-0007's provider boundary.

## Revocation, replacement and rollback

Disable CLAUDE_CODE_ENABLED and recreate the app to revoke the route. Clearing the consent
version/date or changing the owner ID also disables it after app restart. Stop/remove only
jobweaver-claude to replace the worker code/binary or revoke its service; do not touch the web
or PostgreSQL containers. Restart it with the helper. Existing Draft startup recovery remains
in use; no lease table or new queue service is introduced. After a timeout/restart, consumed
subscription usage can be unknown. No claim of exactly-once billing is made.

The provider stays opt-in across app rollback; a missing worker fails into the existing
routes. Keep credentials outside deployment cleanup paths. Dispose of private test tokens
when no longer needed, and rotate any token exposed in chat or screenshots.

Official references:
- https://code.claude.com/docs/en/authentication
- https://code.claude.com/docs/en/cli-reference
- https://code.claude.com/docs/en/setup
- https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan
