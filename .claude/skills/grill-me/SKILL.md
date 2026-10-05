---
name: grill-me
description: Interview the user relentlessly about a plan or design until every branch of the decision tree is resolved. Use when the user says "grill me", wants to stress-test a plan, or wants to resolve the open questions in prd-prompt.md before the PRD is generated.
---

# Grill me

Interview me relentlessly about every aspect of the plan until we reach a shared understanding.

## Target
- Default target: `prd-prompt.md` (the PRD brief). If I name another plan or file, grill that instead.
- Read the target first. Start with its **Open questions**, then any *(recommendation)* or *(verify)* items, then anything vague, contradictory or missing (personas, flows, edge cases, failure modes, data model, limits, metrics).

## How to grill
- Walk down each branch of the design tree. Resolve dependencies between decisions in order: settle the decision that others depend on first.
- Ask **one question at a time**. For each question, give your recommended answer and the strongest reason against it, so I can just say "yes" or push back.
- If a question can be answered by exploring the repo (or by facts already in `prd-prompt.md` / `CLAUDE.md`), answer it yourself instead of asking me.
- Follow `CLAUDE.md` working style: no filler, accuracy over agreement, don't cave without a new argument, never present a guess as fact.
- Don't re-open decisions listed under **Accepted risks** unless I ask.

## Recording
- After each resolved decision, update `prd-prompt.md`: move it out of **Open questions** into the relevant section, and add any new open questions that came up.
- Anything I leave unresolved stays under **Open questions**, never as an assumption.

## Finish
Stop when no open branches remain or I say stop. Then summarise what was decided, what is still open, and whether the brief is ready for PRD generation (step 3 in `CLAUDE.md`).
