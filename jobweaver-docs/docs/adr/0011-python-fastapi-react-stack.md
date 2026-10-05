# Python/FastAPI backend, React + TypeScript frontend

The backend is Python 3.12 + FastAPI with Pydantic v2; the frontend is React + TypeScript (Vite), with types generated from FastAPI's OpenAPI schema. This is the stack the founder already built OneBrain on, so its patterns (adapter registry, AI Gateway, recorded tests, CI) carry over directly. Python has the strongest ecosystem for this product's work: scraping clients, PDF parsing and generation, text similarity, embeddings and AI SDKs. React suits the interactive Draft screen (editor, live chat panel, diff and trace).

**Considered and rejected:** Ruby on Rails (the founder's strongest language and the fastest to ship, but a weaker AI and data ecosystem and less range for the portfolio), a full TypeScript stack (weaker for PDF and AI tooling).

**Consequences:** the UI uses Tailwind CSS with a consistent component library (shadcn/ui recommended) and supports light and dark mode; frontend types are regenerated on every API change, never written by hand.
