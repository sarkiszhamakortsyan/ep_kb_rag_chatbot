# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

All phases (0–9) of the build plan in `documentation/taskdocs/steps.md` are done. The README documents the architecture, API, trade-offs, testing and AI usage; `documentation/evaluation.md` has the test and benchmark results (Claude 18/18, local `ministral-3:3b` 17/18, plus a comparison of six local models). Key entry points: the API app factory `backend/app/main.py` (`create_app`) and `app/api/` (schemas, error mapping, SSE, background index loading in `state.py`); the pipeline in `app/rag/pipeline.py`, with prompts in `app/prompts/*.md` and wiring in `app/services.py`; shared test fakes in `backend/tests/fakes.py`. CI: `.github/workflows/ci.yml`. New features come from `documentation/taskdocs/ideas.md`, one at a time, on the **`dev-features`** branch (`main`/`dev` stay the official submission). Their phase plan and progress are at the end of `ideas.md`. Phase 10 added the admin area (`app/api/v1/admin/`, token check in `app/core/security.py`, SQLite history in `app/stores/history/`, frontend `features/admin/`); phase 11 the Statistics tab (`app/stores/history/stats.py`, `/admin/stats`). Keep this file's commands up to date.

## Commands

Backend (Python 3.12, managed by `uv`, run from `backend/`):
- Install/sync deps: `uv sync`
- Tests: `uv run pytest` (runs only the offline unit/API tests by default; `-m perf` speed tests, `-m integration` and `-m eval` need Ollama); coverage: `uv run pytest --cov`
- Single test: `uv run pytest tests/unit/test_smoke.py::test_package_imports`
- Lint / format: `uv run ruff check` and `uv run ruff format` (`--check` in CI)
- Type check: `uv run mypy`
- Build/refresh the vector index: `uv run python -m app.rag.ingest [--force]` (cached in `data/index/`, rebuilt automatically when docs, chunking or the embedding model change)
- Answer benchmark (full pipeline, real LLM, costs tokens with Claude): `uv run python -m app.evaluation.answers [--provider anthropic|ollama] [--ids q01,q16] [--show] [--json out.json]`
- Retrieval benchmark: `uv run python -m app.evaluation.retrieval [--k 6] [--json out.json]`, or `uv run pytest -m eval -s` (needs Ollama)

Frontend (Node 22, run from `frontend/`): `npm ci`, `npm run dev` (proxies `/api` to `localhost:8000`), `npm run build`, `npm run lint`, `npm run typecheck`, `npm test` (Vitest; single file: `npx vitest run src/api/sse.test.ts`).

Full stack (repo root): `docker compose up -d --build`, then open http://localhost:8080. Ollama always starts (it serves the embeddings), and `ollama-init` pulls the models on first run (~4 GB, about 10 minutes); the backend then builds the index in the background (about 16 s on the dev VM's host CPU, cached in the `backend-index` volume). Ollama is published on `127.0.0.1:11434` for host-side dev and integration tests. Run the backend locally with `uv run uvicorn app.main:api --reload` (from `backend/`).

Configuration: copy `.env.example` to `.env` in the repo root. `.env` is git-ignored, so never commit real keys.

## Layout

- `backend/app/`: `api/v1` (routes), `core` (config, security), `rag` (ingest, chunking, retrieval, pipeline), `prompts` (template files), `providers/llm` + `providers/embeddings` (interfaces and registries), `stores/vector` + `stores/events`, `evaluation` (benchmark shared by tests and the future admin tab).
- `backend/data/kb/`: the mock KB articles (Markdown). `backend/data/index/` is the generated index cache (git-ignored).
- `backend/tests/`: `unit/`, `integration/`, `perf/`, `eval/` (`questions.yaml` + benchmark test).
- `frontend/src/`: `api/` (typed client, SSE parser, types mirroring the Pydantic schemas), `features/chat/` (`useChat` state/streaming hook, answer bubble with citation chips, source cards), `features/admin/` (placeholder for the future hidden tabs), `test/` (setup and fixtures).
- `documentation/ai-logs/`: Claude Code sessions as Markdown (a mandatory deliverable). They are regenerated automatically after every assistant turn by the Stop/SessionEnd hooks in `.claude/settings.json`, which run `scripts/export_ai_logs.py --hook` (redacts secrets). Manual full export: `python3 scripts/export_ai_logs.py --all`. Commit the updated logs together with each phase.

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
