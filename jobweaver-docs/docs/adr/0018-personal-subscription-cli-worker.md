# Personal subscription CLI worker for Draft generation

Status: accepted for the owner-only opt-in implementation, 26 October 2026.
The separate capped container was selected after the synthetic VM spike; see
[measured results and operation](../../PERSONAL_CLAUDE.md).

## Context

Free-provider Draft generation can fail when one provider times out, another cannot fit the
prompt, and remaining accounts are rate-limited. The owner wants the existing Generate Draft
button to use their personally authenticated Claude Code installation on the production
server. Other Users must not consume that subscription. MCP is not needed for this flow.

## Decision

Add a default-off personal Claude Code provider inside the AI Gateway, restricted to a single
configured internal User ID. Execute the official unmodified CLI in an isolated production
execution environment with no model tools or production filesystem access. Authenticate
through Anthropic's official flow; only the CLI consumes its private credential. Retain current routes as fallback,
owner-specific recorded consent, per-user attribution, recorded tests and existing Draft
validation.

Use the existing background Draft tasks and startup recovery with bounded deadlines and
single-run exclusion first. Measure resource use and injection resistance in an isolated VM
spike before building the provider; only add a queue/container if evidence justifies it. See the
[implementation plan](../../PERSONAL_AI_WORKER_PLAN.md) for lifecycle, rollout and open choices.
Draft Chat requires background processing before adopting longer generation deadlines.

This explicitly proposes two narrow amendments: ADR-0007's text-provider ordering may prepend
the personal CLI for its allowed User, while all AI access remains in the gateway; ADR-0008's
rejection of a separate worker may be relaxed only if the resource/isolation spike justifies
a separate capped service. It is not a prerequisite of the proposal.
The owner supplies an existing subscription; no paid API billing is enabled automatically.
Existing global free-provider behaviour and the embedding policy remain unchanged.

## Consequences and alternatives

Subscription capacity, credential renewal and CLI compatibility become operational dependencies.
CLI execution adds memory pressure, so the early spike may rule out the current host.
Fact checks do not prove factual accuracy; the User must still review the generated Draft.
No subscription connection UI, credential pooling or multi-user hosting is authorized here.

A paid API offers a simpler application integration but separate usage billing. An MCP-based
workflow uses the assistant as the entry point and would not preserve the requested button
flow. A Mac worker requires the Mac to remain online. Those alternatives remain available if
server resource tests or provider rules prevent the personal production worker.

Acceptance of this ADR does not certify compliance with every provider rule. Recheck the
linked official sources and effective authentication before implementation and rollout.

## Implementation boundary

The existing background Draft task calls the worker through a gateway-owned authenticated
HTTP adapter. No new lease table or durable queue is added. The operator records the owner
UUID, consent version and acceptance timestamp in private app configuration; the personal
route checks all three, the opt-in flag and service authentication before dispatch. This
record is independent of the global AI notice and does not prompt unrelated Users. A private
worker environment holds the subscription token. The web application holds only the separate
service key. Synchronous Draft Chat does not use the personal route.

The 192 MiB experiment timed out; a 256 MiB synthetic Draft and traced malicious-JD test
passed. The capped container protects the app/DB from unbounded CLI memory and credential
exposure, but does not create additional host memory. Long-term performance remains a
rollout observation. CLI shutdown, failed auth, quota and invalid output retain fallback.
