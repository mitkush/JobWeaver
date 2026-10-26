# Personal production AI worker plan

Status: proposed brief and implementation plan, 26 October 2026. Documentation only.
No CLI is installed, credential collected, provider enabled, or production setting changed.
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
  ADR-0008 rejected separate worker services; ADR-0018 explicitly proposes a narrow exception.
- The production VM has roughly 1 GB RAM shared with the application and PostgreSQL. CLI
  startup overhead, peak memory, CPU contention and PDF generation must be measured before
  enabling a persistent worker. A separate container alone does not provide extra RAM.

## User flow and job lifecycle

1. The User clicks Generate Draft. Existing ownership, reviewed Fact Bank, region and current
   AI notice checks apply before the request is accepted. Return promptly with a queued Draft.
2. Persist a generation attempt with User ID, Draft ID, expected version, status and expiry.
   Freeze the approved Facts and job context used for this attempt. Recheck authorization
   and consent immediately before dispatch, including after queue waits.
3. A worker claims the attempt with a bounded lease. Only one personal CLI invocation runs
   at a time. A busy or unavailable worker waits briefly or falls back; it never starts an
   unlimited queue of CLI processes. Keep database transactions short across remote work.
4. The gateway selects the personal route only for the server-configured internal User ID.
   It supplies the typed prompt to the official CLI over standard input, never through a shell.
5. Parse the CLI envelope and structured DraftResult, then run existing schema, Fact reference
   and tailoring checks. Invalid output follows the existing bounded repair/fallback policy.
6. Save only a result matching the current attempt and expected Draft version. Discard late
   replies from timed-out or superseded attempts. Retries must not overwrite manual edits
   or create duplicate versions. Keep each version's job context immutable.
7. The Draft page displays queued, generating, checking, ready or a useful retry state.
   Cancellation, account deletion and worker shutdown terminate the child process group.
   Restart recovery reclaims expired leases without accepting an older result twice. An
   interrupted request may have consumed subscription usage; retries are not cost-free.

Existing in-process Draft tasks are not a durable queue. Implementation must explicitly
choose a minimal database-backed attempt/lease design and migration rather than assuming
current queued state survives every deploy. Do not add Redis or a general broker by default.

## Gateway and isolated execution

- Put the provider adapter, CLI protocol and provider error mapping in app/gateway/. A worker
  orchestrates attempts but never calls Claude directly outside the gateway. Keep typed
  gateway methods, recorded fixtures and existing fallback semantics (ADR-0007).
- Prefer a separate unprivileged worker container/process with a bounded local interface.
  The web container never receives the subscription credential. Fix the executable and flags;
  no browser input can select commands, environment variables, paths or arbitrary models.
- Run the unmodified official CLI in a clean directory and isolated configuration home with
  no project instructions, hooks, plugins or MCP servers. Disable model tools including shell,
  editing and browsing using supported CLI options. Do not bypass permission checks.
- Do not mount the repository, Docker socket, application .env, SSH keys or database files.
  The worker may access only the minimal queue/result interface, its credential and transient
  working space. Enforce memory/CPU/process/output limits and network access appropriate
  to the selected provider and internal interface. Destroy temporary prompt files promptly.
- CLI headless mode can discover local instructions and hooks. Bare mode skips those, but
  currently does not read CLAUDE_CODE_OAUTH_TOKEN. Do not assume --bare works with subscription
  tokens: verify the chosen CLI version and use a clean supported configuration instead.

## Authentication, consent and personal access

The owner completes Anthropic's official claude setup-token browser flow. Store its output
as a private worker-only secret, outside Git, images, logs and the ordinary app configuration.
Only the official CLI consumes it; JobWeaver does not make requests with subscription tokens
to undocumented endpoints. Clear inherited API-key/provider variables that would override
subscription authentication; verify the effective account without logging credentials.

Configuration names are proposals: PERSONAL_CLAUDE_ENABLED defaults false and
PERSONAL_CLAUDE_USER_ID identifies exactly one existing User. Use the authenticated server
User ID, never a caller-supplied email or provider flag. No public endpoint can obtain or
change the credential. Other Users cannot queue work under the owner's subscription.

Update and version the AI notice before sending approved Facts to this new provider.
Existing Users must accept the changed notice as required by current consent rules. Explain
consumer-account data settings and ask the owner to review training/privacy choices. Retain
Fact Bank checks, but do not promise they prove every generated claim is accurate.

Document official authentication and expiry/renewal steps. An expired or revoked token
produces a redacted provider failure and fallback, not repeated login attempts. Multi-user
hosting requires a separate design and a fresh review of provider rules; an email allowlist
or an ADR alone does not establish permitted subscription use.

## Time budgets and smaller prompts

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

## Delivery stages and acceptance checks

1. Protocol spike in isolation: pin a supported CLI version, verify subscription authentication,
   tools disabled, structured output, exit/error formats, token metadata and child termination.
   Use synthetic data first. Confirm the official rules still cover the intended operation.
2. Implement the gateway adapter and durable attempt lifecycle behind the default-off flag.
   Fixtures and fake executable tests cover success, refusal, invalid JSON/schema, quota,
   expired login, startup failure, oversized output, timeout, cancellation and fallback.
3. Add ownership and consent tests: a second User cannot use the personal route; expired consent
   blocks dispatch; account deletion and superseded attempts cannot commit results. Test restart
   recovery, a busy worker, child cleanup, idempotent saves and unchanged older Draft versions.
4. Implement prompt budgeting and background Draft Chat separately within the implementation
   series. Preserve pinned Facts and manual edits; test full Draft output and fallback budgets.
   Add generated frontend API types if endpoints change. Update COSTS.md and notice wording.
5. Measure startup/steady/peak RAM and latency on a production-equivalent small VM while web,
   PostgreSQL and PDF generation remain responsive. Reject rollout if it risks OOM or health
   checks. Choose a larger/separate host or leave the feature disabled if it does not fit.
6. Deploy disabled, authenticate privately, then enable only for the owner. Run one explicitly
   requested real Draft, verify Fact references, provider attribution, PDF export and fallback.
   Routine CI never uses a real subscription or consumes AI quota. Publish measured results
   before broadening usage. Rollback disables the route and stops the worker without dropping
   attempts, history or Draft versions; validate worker compatibility with app rollbacks.

## Open decisions before implementation

- Exact model, CLI version and resource envelope after the protocol spike.
- Minimal attempt/lease schema, secure internal transport and restart recovery behaviour.
- Whether measured latency warrants different budgets and whether the current VM can fit.
- Precise supported flags for tool/config isolation with subscription authentication.
- Codex parity is deferred. Its documented headless login is technically available, but its
  own usage rules, output contract and isolation need separate verification and tests.

## Official references checked 26 October 2026

- [Claude Code authentication and setup-token](https://code.claude.com/docs/en/authentication)
- [Claude Code non-interactive execution](https://code.claude.com/docs/en/headless)
- [Subscription usage, including claude -p](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan)
- [Claude Code credential and hosted-product rules](https://code.claude.com/docs/en/legal-and-compliance)
- [Codex subscription and headless authentication](https://learn.chatgpt.com/docs/auth)
- [Codex non-interactive execution](https://learn.chatgpt.com/docs/non-interactive-mode)

Official docs support the mechanisms above; this plan is not a blanket legal determination
or a promise that future subscription policies, capacity or authentication stay unchanged.
