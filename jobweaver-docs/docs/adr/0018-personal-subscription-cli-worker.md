# Personal subscription CLI worker for Draft generation

Status: proposed, 26 October 2026. No runtime behaviour changes in this PR.

## Context

Free-provider Draft generation can fail when one provider times out, another cannot fit the
prompt, and remaining accounts are rate-limited. The owner wants the existing Generate Draft
button to use their personally authenticated Claude Code installation on the production
server. Other Users must not consume that subscription. MCP is not needed for this flow.

## Proposed decision

Add a default-off personal Claude Code provider inside the AI Gateway, restricted to a single
configured internal User ID. Execute the official unmodified CLI in an isolated production
worker with no model tools or production filesystem access. Authenticate through Anthropic's
official flow; only the CLI consumes its private credential. Retain current routes as fallback,
versioned consent, per-user attribution, recorded tests and existing Draft validation.

Use durable, bounded attempts with deadlines, leases and idempotent results. Measure resource
use before enabling the worker on the small VM. See the
[implementation plan](../../PERSONAL_AI_WORKER_PLAN.md) for lifecycle, rollout and open choices.
Draft Chat requires background processing before adopting longer generation deadlines.

This explicitly proposes two narrow amendments: ADR-0007's text-provider ordering may prepend
the personal CLI for its allowed User, while all AI access remains in the gateway; ADR-0008's
rejection of a separate worker is relaxed for this bounded, isolated personal worker only.
The owner supplies an existing subscription; no paid API billing is enabled automatically.
Existing global free-provider behaviour and the embedding policy remain unchanged.

## Consequences and alternatives

Subscription capacity, credential renewal and CLI compatibility become operational dependencies.
A separate process/container adds memory pressure, so rollout may require another host.
Fact checks do not prove factual accuracy; the User must still review the generated Draft.
No subscription connection UI, credential pooling or multi-user hosting is authorized here.

A paid API offers a simpler application integration but separate usage billing. An MCP-based
workflow uses the assistant as the entry point and would not preserve the requested button
flow. A Mac worker requires the Mac to remain online. Those alternatives remain available if
server resource tests or provider rules prevent the personal production worker.

Acceptance of this ADR does not certify compliance with every provider rule. Recheck the
linked official sources and effective authentication before implementation and rollout.
