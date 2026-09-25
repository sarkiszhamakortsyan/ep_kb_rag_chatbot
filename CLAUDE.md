# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Implementation follows the phased build plan in `documentation/taskdocs/steps.md` (each phase ends with a user review). Phases 0–1 are done, and the Docker Compose stack runs (backend health endpoint + frontend placeholder). Keep this file's commands up to date as phases add them.

## Commands

Backend (Python 3.12, managed by `uv`, run from `backend/`):
- Install/sync deps: `uv sync`
- Tests: `uv run pytest` (runs only unit tests by default; `-m integration` needs Ollama, `-m eval` runs the benchmark)
- Single test: `uv run pytest tests/unit/test_smoke.py::test_package_imports`
- Lint / format: `uv run ruff check` and `uv run ruff format` (`--check` in CI)
- Type check: `uv run mypy`

Frontend (Node 22, run from `frontend/`): `npm ci`, `npm run dev` (proxies `/api` to `localhost:8000`), `npm run build`, `npm run lint`, `npm run typecheck`.

Full stack (repo root): `docker compose up -d --build`, then open http://localhost:8080. Ollama starts via `COMPOSE_PROFILES=ollama` in `.env`, and `ollama-init` pulls the models on first run. Ollama is published on `127.0.0.1:11434` for host-side dev and integration tests. Run the backend locally with `uv run uvicorn app.main:api --reload` (from `backend/`).

Configuration: copy `.env.example` to `.env` in the repo root. `.env` is git-ignored, so never commit real keys.

## Layout

- `backend/app/`: `api/v1` (routes), `core` (config, security), `rag` (ingest, chunking, retrieval, pipeline), `prompts` (template files), `providers/llm` + `providers/embeddings` (interfaces and registries), `stores/vector` + `stores/events`, `evaluation` (benchmark shared by tests and the future admin tab).
- `backend/data/kb/`: the mock KB articles (Markdown). `backend/data/index/` is the generated index cache (git-ignored).
- `backend/tests/`: `unit/`, `integration/`, `eval/questions.yaml`.
- `frontend/`: Vite + React + TS + Tailwind (Phase 6).
- `documentation/ai-logs/`: exported Claude transcripts (a mandatory deliverable).

## What is being built

A prototype **Enterprise Knowledge Base RAG chatbot** for "OmniCorp Solutions" Customer Success Managers. It answers natural-language questions **strictly from internal documentation** and returns **citations** to the source documents.

Required pieces (from `README.md`):
- **Backend API**: ingests 3–5 mock enterprise KB articles (which also need to be written), chunks them, stores embeddings in a local or in-memory vector store, and exposes a chat endpoint. The candidate languages are Python and Node.js; C#/.NET is also allowed.
- **Frontend**: a web chat UI (React, Next.js, or Vite + TypeScript, optionally with Tailwind) that shows answers and the specific document citations used.
- **LLM**: a local Ollama model, or bring-your-own-key via environment variables (Anthropic/OpenAI/Groq). Never commit real API keys.
- **`docker-compose.yml`** that starts the whole stack locally.
- Basic tests, plus a README section on architecture decisions, API design, trade-offs, and how to run and test the system.
- **Mandatory:** export the AI assistant conversation logs (Claude transcripts) into the repo, and add a README note on which tools were used for which parts.

The unchecked items in the README "Plan" list are planned features. They include a hidden statistics menu, multi-language Q&A, response history, polite handling or human handoff when the documentation has no answer, and unit, speed, and performance tests.

## Task-doc workflow

Work is driven by the markdown task files in `documentation/taskdocs/`, executed in the order given in `steps.md`:
1. `goal.md`: the overall goal.
2. `research.md`: choose the backend language (Python vs Node.js) and the frontend stack, pick the best Ollama model, and work out how to support Claude. **Findings get written back into this same file**, with the reasoning for and against each option.
3. `storage.md`: choose the vector store approach (local vs in-memory). **Findings get written back into this same file.**
4. `ideas.md`: future features (stats, costs, history, multi-language, test tab, provider toggle). **Do not implement them unless asked**, but every piece of code must keep the seams listed in its "Future-readiness design" section: `ChatResult` with usage/timings, `/api/v1` + an `options` object, separate `LLMProvider`/`EmbeddingProvider` registries, the `EventStore` hook, and prompts as template files. Mark an idea done in `ideas.md` only after it is implemented.

When you complete a task doc, append the research and decisions to that file instead of creating a new one. Update the README checklist as items are finished.
