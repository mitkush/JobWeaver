# Personal production AI worker plan

Status: implementation follow-up, 26 October 2026. The plan PR itself was documentation only.
Step 1 shipped in #61. The isolated VM spike passed at 256 MiB after failing at 192 MiB.
The owner-only provider implementation and operating limits are in [Personal Claude](PERSONAL_CLAUDE.md).
The production Generate route remains disabled until the implementation is deployed and
explicitly configured. The spike did not change the app's provider routing.
See [proposed ADR-0018](docs/adr/0018-personal-subscription-cli-worker.md).

## Goal and agreed scope

Keep the existing Generate Draft action on the web and Application Extension. For the
owner's own account, generation runs through the official Claude Code CLI on the production
server using the owner's subscription. The Mac need not be online. The User reviews the
result in JobWeaver and downloads the same PDFs as today.

Start with Tailored Resume, Cover Letter and Application Email generation. Include Draft
Chat only after its long-running request is moved to background execution. Claude Code
is first for an explicitly allowed internal User ID; everyone else retains existing routes.
Existing providers remain fallbacks. No MCP server is required.

Outside the first implementation: collecting other Users' subscription credentials,
subscription connection UI, shared subscription capacity, automatic application submission,
CLI access to production files or tools, embeddings through a CLI, and guaranteed availability.
Codex is a possible second adapter, not a dependency of the Claude implementation.

## Evidence and current constraints

- Current Draft routes allow 20 seconds each; Draft generation and synchronous Draft Chat
  use 90-second timeout scopes. A new 60-second route cannot simply be prepended without
  budgeting fallback time and validation retries. Page Description requirements extraction
  has a separate timeout scope today and must also be accounted for in end-to-end timing.
- The observed failed Captured Job extracted requirements successfully, then Gemini timed
  out, Groq skipped the oversized prompt, OpenRouter returned 429 and Mistral was unconfigured.
  A worker does not fix the oversized Groq fallback unless prompt construction changes too.
- ADR-0007 keeps all provider access inside the gateway and tests in recorded mode.
  ADR-0008 rejected separate worker services. A separate service is conditional on the spike,
  not a prerequisite; ADR-0018 records that boundary.
- Read-only VM check on 26 October: 956 MB RAM, 378 MB available, 750 MB swap used; app
  approximately 93 MB, PostgreSQL 135 MB. These are a snapshot, not reserved capacity. Swap
  occupancy alone does not establish active memory pressure. Measure CLI startup and peak
  whole-process memory, swap activity and latency in stage 1 before building an adapter.

## User flow and job lifecycle

1. The User clicks Generate Draft. Existing ownership, reviewed Fact Bank, region and current
   AI notice checks apply before the request is accepted. Return promptly with a queued Draft.
2. Use the existing queued/generating Draft lifecycle. Startup already calls recover_queued(),
   which resets and restarts both states. Recheck authorization and owner-specific consent
   immediately before dispatch, including after any wait.
3. Invoke the CLI through the gateway from the existing background Draft task, initially one
   run at a time under a process-wide lock. This assumes one application process/replica;
   verify deployment settings. If multiple processes are introduced, a Python lock is not
   sufficient and cross-process exclusion becomes a separate requirement.
4. Supply the typed prompt over standard input, never through a shell. The route is available
   only to the configured internal User ID. Parse structured output and retain current schema,
   Fact reference and tailoring checks. Invalid output follows bounded fallback.
5. Save only results for the still-current Draft operation. Existing manual-edit protection,
   ownership checks and immutable saved versions remain. Kill and await child processes on
   timeout, cancellation and shutdown; do not accept late output after fallback.
6. Show the active provider and fallback progress, such as Trying Claude or Falling back to
   Gemini, without exposing diagnostics or credentials. Leave Draft Chat on its existing
   synchronous limits until a separate background-chat change is reviewed.

The existing restart recovery makes a new durable lease queue unnecessary by default for
this personal single-process use. Test that recovery, retry exclusion and child cleanup
remain correct. Recovery may repeat a call that already consumed subscription capacity;
no design here promises exactly-once provider billing. Add a lease/attempt table only if
measured or tested lifecycle requirements cannot be handled safely by the existing tasks.

## Gateway and isolated execution

- Put the provider adapter, CLI protocol and provider error mapping in app/gateway/. A worker
  orchestrates attempts but never calls Claude directly outside the gateway. Keep typed
  gateway methods, recorded fixtures and existing fallback semantics (ADR-0007).
- Choose deployment after the stage 1 spike: a constrained child of the existing Draft task
  is the initial simple option; a separate capped container is justified if stronger memory
  or credential isolation is needed and fits the host. Fix the executable and flags; browser
  input cannot select commands, environment variables, paths or arbitrary models.
- Run the unmodified official CLI in a clean directory and isolated configuration home with
  no project instructions, hooks, plugins or MCP servers. Disable model tools including shell,
  editing and browsing using supported CLI options. Do not bypass permission checks.
- Do not mount the repository, Docker socket, application .env, SSH keys or database files.
  A clean directory alone does not prevent file reads by a child of the app. Use OS-enforced
  filesystem/process isolation appropriate to the measured design. Enforce a limit on the
  whole process tree using cgroups/container limits, not just Node heap size. Restrict CPU,
  process count, output and network access. Destroy transient prompt data promptly.
- CLI headless mode can discover local instructions and hooks. Bare mode skips those, but
  currently does not read CLAUDE_CODE_OAUTH_TOKEN. Do not assume --bare works with subscription
  tokens: verify the chosen CLI version and use a clean supported configuration instead.

## Authentication, consent and personal access

The owner completes Anthropic's official claude setup-token browser flow. Store its output
as a private CLI-only secret, outside Git, images, logs and the ordinary app configuration.
Only the official CLI consumes it; JobWeaver does not make requests with subscription tokens
to undocumented endpoints. Clear inherited API-key/provider variables that would override
subscription authentication; verify the effective account without logging credentials.

Configuration names are proposals: PERSONAL_CLAUDE_ENABLED defaults false and
PERSONAL_CLAUDE_USER_ID identifies exactly one existing User. Use the authenticated server
User ID, never a caller-supplied email or provider flag. No public endpoint can obtain or
change the credential. Other Users cannot queue work under the owner's subscription.

Retain the current global AI notice and region checks. Add explicit, recorded acceptance
for this owner-only Claude route, including the provider notice version and acceptance time,
and check it before every dispatch. A note without recorded acceptance is insufficient.
Do not require unrelated Users to reaccept a notice for a route they cannot use. Explain
consumer-account data settings and ask the owner to review training/privacy choices. Retain
Fact Bank checks, but do not promise they prove every generated claim is accurate.

Document official authentication and expiry/renewal steps. An expired or revoked token
produces a redacted provider failure and fallback, not repeated login attempts. Multi-user
hosting requires a separate design and a fresh review of provider rules; an email allowlist
or an ADR alone does not establish permitted subscription use.

## Time budgets and smaller prompts

Ship prompt budgeting and generation-only timeout fixes as a separate infrastructure-free
PR first. The numbers below concern the later optional Claude route, not that first PR.

Initial proposal for review and measurement: 60 seconds for Claude, followed by up to 30
seconds each for the existing configured text providers. Give the generation phase a
210-second total ceiling, including repair attempts; reserve at least 30 seconds for local
checking/cleanup. Requirements extraction has its own bounded phase, at most 90 seconds.
Cap the entire attempt at 300 seconds. Phase ceilings are inside, not additional to, that
attempt ceiling. These are proposed budgets, not measured latency guarantees.

The gateway receives the remaining deadline and never starts a route with an insufficient
budget. Skip unconfigured providers immediately; count busy retries within each route.
Kill timed-out CLI children and suppress late results before moving on. Cancellation is
logged as interrupted/unknown usage, not as zero-cost success. Draft Chat must use a background
attempt with polling before it receives these longer limits; no 210-second open web request.

Select relevant Facts deterministically using the JD and required skills, keeping stable
Fact IDs, contact information, essential employment context, linked supporting Facts and
explicitly protected manual edits. Budget serialized input, instructions and output together.
Do not truncate Facts mid-sentence or invent summaries to fit. Keep the frozen full approved
Fact set for validation while recording which IDs were sent. Provider-specific prompt budgets
must leave enough output room for a complete Draft; otherwise skip the route with a clear
reason. Never force Groq to produce a truncated resume just to stay below its allowance.

## Fallback and observability

For the allowed User: Claude Code -> existing configured Gemini/Groq/OpenRouter/Mistral
routes in their established order. For other Users, or when disabled: current routes only.
Authentication failures, quota exhaustion, process errors, timeout and invalid output all
follow bounded fallback. After all routes fail, expose a concise retry message and keep
redacted diagnostic reasons for the operator. No silent paid API fallback is introduced.

Record each actual attempt in ai_usage with User ID, task, provider, actual model and outcome.
Use CLI-reported tokens where supplied, never CLI dollar estimates as subscription charges.
Distinguish unknown usage after interruption from zero tokens. Record elapsed time and queue
wait using a minimal schema change if needed; never log raw prompts, resumes, JD text or tokens.
Subscription quotas are shared with the owner's other Claude use. Display that limits and
renewal are provider-controlled; do not invent daily request allowances or dollar balances.

## Delivery order and acceptance gates

0. [PR #61](https://github.com/mitkush/JobWeaver/pull/61), separate from this plan:
   deterministic relevant-Fact selection and provider-specific serialized
   prompt budgets, preserving employment context, whole supporting groups, stable refs and
   cited Facts/manual text for revisions. Increase only background generation route/phase
   timeouts. Keep synchronous Draft Chat and requirements extraction on their existing limits.
   Test actual outbound prompts, fallback and timeout cancellation. This addresses prompt
   size and short deadlines; it does not fix exhausted quotas or promise fewer failures.
1. Before adapter/queue work, run an isolated resource and protocol spike on the target VM.
   Pin the official CLI, review official authentication/usage documentation again, and use
   synthetic JD/Facts only. The owner completes setup-token authentication privately. Measure
   startup, peak whole-process-tree memory, wall time, CPU, swap activity and application/DB
   health under a strict memory cap. Record starting load and measurements, not an estimated
   few-hundred-MB claim. Avoid installation into the live web image or uncontrolled model
   execution on the host. If the safe constrained spike cannot fit, stop and choose another
   host or leave the feature disabled before building the provider.
   - Mandatory injection test: a JD requests ignoring instructions and reading ~/.ssh/*,
     the app .env and database settings. Verify no tool invocation and no reads of sensitive
     paths, using safe canary files/deny rules and OS-level observation; a compliant textual
     answer alone is not proof. Test configured tools unavailable on the pinned CLI version.
   - Use an empty working directory, private config home and explicitly constructed minimal
     environment. Confirm hooks, plugins and MCP discovery cannot import host configuration.
     Verify subscription auth headlessly, expiry behaviour, structured output, token metadata,
     cancellation and cleanup. Never use live production secrets as injection-test bait.
   - Passing this spike is a hard rollout gate. Decide child process versus isolated capped
     container from the evidence; preserve PostgreSQL and app health in either arrangement.
2. Only if the spike passes: add the Claude provider inside app/gateway/, invoked by the
   existing Draft task with single-run exclusion. Keep it disabled by default and limited to
   the owner ID. No queue migration or separate service unless the spike/test results justify
   it. Fake executable and recorded tests cover success, refusal, malformed JSON/schema,
   quota, expired login, crash, output limits, timeout, cancellation, cleanup and fallback.
3. Add owner-specific recorded consent and tests for second-User exclusion, missing/revoked
   acceptance, account deletion, concurrent retry, restart recovery and unchanged saved
   versions/manual edits. Persist provider progress for the Draft page. Background Draft Chat
   is a separate follow-up; do not silently extend its open web request.
4. Deploy disabled, complete private authentication, then enable only for the owner. Run one
   explicitly requested real Draft; verify trace, attribution, PDF and bounded fallback.
   Update COSTS.md with measured costs/limits and rollback instructions. CI never uses a real
   subscription. Rollback disables the route, stops CLI children and preserves Draft history.

## Open decisions after the spike

- Exact model, pinned CLI version and measured process-tree resource limits.
- Supported tool/config isolation flags and OS controls with subscription authentication.
- Child process or capped container; current lifecycle sufficiency under the actual process
  count, rather than a predetermined lease table or worker transport.
- Owner-only acceptance storage, route progress plumbing and measured timeout budgets.
- Codex parity is deferred. Its documented headless login is technically available, but its
  usage rules, output contract and isolation require their own verification and tests.

## Official references checked 26 October 2026

- [Claude Code authentication and setup-token](https://code.claude.com/docs/en/authentication)
- [Claude Code non-interactive execution](https://code.claude.com/docs/en/headless)
- [Subscription usage, including claude -p](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan)
- [Claude Code credential and hosted-product rules](https://code.claude.com/docs/en/legal-and-compliance)
- [Codex subscription and headless authentication](https://learn.chatgpt.com/docs/auth)
- [Codex non-interactive execution](https://learn.chatgpt.com/docs/non-interactive-mode)

Official docs support the mechanisms above; this plan is not a blanket legal determination
or a promise that future subscription policies, capacity or authentication stay unchanged.
