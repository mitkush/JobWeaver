# All AI calls go through a thin AI Gateway with free-provider fallback

One internal module owns every AI call and is the only code that imports a provider SDK. It exposes typed task methods (extract a Posting from free text, extract required skills, embed text, parse documents into Facts, tailor a resume, write a cover letter, write an email, apply a Draft Chat edit), routes each task to a model, and falls back in order **Gemini (Flash / Flash-Lite) -> Groq -> OpenRouter `:free`** when a provider errors, rate-limits or runs out of free quota. Ollama is available for local development only. A recorded-response mode serves committed fixtures so tests and CI make zero live AI calls, as in OneBrain.

**Considered and rejected:** LangChain-style frameworks (an abstraction with its own breaking changes for a handful of call shapes), calling SDKs from features directly (a provider change becomes a codebase-wide edit), a paid model (zero budget).

**Consequences:** every task needs success, malformed and refusal fixtures; output is validated against a schema and retried on the next provider when invalid; per-user AI usage is recorded for future pricing; free-tier terms (prompt use for training, regional limits) are an accepted risk for private use (ADR-0012).
