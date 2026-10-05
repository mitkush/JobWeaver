# Accepted risks for private use, to revisit before any public launch

JobWeaver is used privately by the founder and a few friends. On that basis the founder accepts three risks that would block a public product: (1) fetching LinkedIn and Naukri through Bright Data and Apify breaches those sites' terms of service, which is a civil (contract) risk, not a criminal one; (2) free AI tiers may use prompts, which contain resume content, to improve the provider's products (confirmed for Gemini's free tier on 5 Oct 2026); (3) every free tier can change or disappear without notice.

Gemini's terms also require paid services for apps made available to users in the EEA, Switzerland or the UK. This is a rule, not a risk to accept: in V1, while on the free tier, JobWeaver Users must be outside those regions; a friend there can join only after the move to a paid Gemini tier.

Risk (2) also affects the founder's friends, so the founder cannot accept it for them: every User accepts a one-line AI data notice in onboarding before any document is sent to an AI provider.

**Consequences:** these are recorded, not re-debated, during V1; the fallback design (ADR-0003, ADR-0007) limits the impact of (3); a **pre-launch review** of (1) and (2), plus Google verification for Gmail (ADR-0006), is a required gate before JobWeaver is offered publicly or for money.
