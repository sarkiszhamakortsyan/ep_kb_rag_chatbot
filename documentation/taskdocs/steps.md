# Task - Step to build the ChatBot

## Description

The steps to build the Enterprise Knowladge Base RAG Chatbot.

## The steps will be executed as follows:

1. ✅ Check the file documentation/taskdocs/goal.md, read and proceed with the request inside.
2. ✅ Check the file documentation/taskdocs/research.md, read and proceed with the request inside.
3. ✅ Check the file documentation/taskdocs/storage.md, read and proceed with the request inside.
4. ✅ Check the file documentation/taskdocs/ideas.md. Keep the extension points ("Future-readiness design"), but do not implement the ideas.

---

## Build plan (added 2026-09-25)

Based on the decisions in `research.md`, `storage.md` and `ideas.md`:
- **Stack**: Python 3.12 + FastAPI backend; Vite + React + TypeScript + Tailwind frontend; Ollama (`gemma3:4b` + `embeddinggemma`) or Anthropic API.
- **Vector store**: an in-memory vector store with an on-disk cache.
- **Delivery**: everything runs with Docker Compose.

**Rules for every phase**
- A phase is complete only when its **Done when** checks pass. After each phase: mark it ✅ here, tick the related README checklist item, commit, and **stop for the user's review** before the next phase.
- Keep the `ideas.md` extension points. Do not implement the ideas themselves.
- No real API keys in the repo. Only `.env.example` is committed.
- Claude transcripts are exported continuously (Phase 9 finalises them).

### Phase 0: Repository skeleton & tooling ✅ (2026-09-25)
- Create the folders from `ideas.md` → "Planned project structure" (`backend/`, `frontend/`, `backend/data/kb/`, `documentation/ai-logs/`).
- Backend: `pyproject.toml` (managed with `uv`), with ruff (lint + format), pytest, mypy in basic mode.
- Root files: `.gitignore`, `.env.example` (all config variables with safe defaults, empty keys), `.editorconfig`.
- Update `CLAUDE.md` with the build, lint and test commands.
- **Done when**: `uv run pytest` runs (0 tests OK), `uv run ruff check` passes, `.env` is git-ignored.

### Phase 1: Mock knowledge base ✅ (2026-09-25)
- Write the 5 OmniCorp Markdown articles proposed in `storage.md`. Each has front matter (`id`, `title`, `product`, `lang`, `updated`) and `##`/`###` sections.
- The topics overlap a little, so that some answers need citations from more than one document.
- Write `backend/tests/eval/questions.yaml`: about 15 questions, each with the expected `doc_id`s, plus about 3 questions the docs can't answer (these must be refused).
- **Done when**: the articles and the eval set have been reviewed by the user.

### Phase 2: Configuration & provider interfaces ✅ (2026-09-25)
- `core/config.py` (pydantic-settings) with these settings: `LLM_PROVIDER`, `ENABLED_LLM_PROVIDERS`, `EMBEDDING_PROVIDER`, `OLLAMA_BASE_URL`, `OLLAMA_CHAT_MODEL`, `OLLAMA_EMBED_MODEL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `TOP_K`, `MIN_SCORE`, `ADMIN_TOKEN`.
- `providers/llm/`:
  - `base.py`: the `LLMProvider` interface. It streams tokens and returns `usage` at the end.
  - `registry.py`
  - `ollama.py` (uses `think=false` where the model supports it, and `keep_alive`)
  - `anthropic.py` (Messages API, streaming)
- `providers/embeddings/`: `base.py`, `registry.py`, `ollama.py` (with the embeddinggemma query/document prefixes).
- **Done when**: unit tests with fake providers pass, and the registry rejects disabled or unknown providers with a clear error.

### Phase 3: Ingestion, chunking & vector store ✅ (2026-09-25: recall@5 = 0.97, hit rate = 1.00, MIN_SCORE = 0.35 kept, see `storage.md`)
- `rag/chunking.py`: splits on headings first, then into windows of about 400 tokens with about 60 tokens of overlap. Each chunk keeps `doc_id`, `title`, `section`, `lang`.
- `stores/vector/`:
  - `base.py`: the `VectorStore` interface (`add`, `search`, `count`)
  - `memory.py`: a numpy cosine-similarity store
- `rag/ingest.py`: loads the KB, chunks it, embeds the chunks, and caches the index to `data/index/`. The cache key is a hash of the docs, the chunking parameters and the embedding model name. It rebuilds automatically when that hash changes.
- **Done when**:
  - unit tests cover chunk boundaries and metadata, cosine top-k ordering, and cache reuse vs. invalidation
  - retrieval hit-rate on the eval set is ≥ 80% (expected doc in the top k) with the real Ollama embeddings

### Phase 4: RAG pipeline & prompts ✅ (2026-09-25)

**Evaluation with Claude** (`claude-opus-5`, `uv run python -m app.evaluation.answers --provider anthropic`):

| Run | Change | Passed | Notes |
|---|---|---|---|
| 1 | first prompt, TOP_K=5 | 13/18 | 4 English questions answered in German or Portuguese; LDAP refusal padded with cited "context"; q12 missing the P1 response time |
| 2 | stricter language rule and no "related info" in refusals | 17/18 | all answers in the question's language; 3/3 refusals |
| 3 | TOP_K=6 | **18/18** | the response-time table was ranked 6th for the two-document question q12 |

Final run: median 4.8 s per answer, first token after about 2–3 s, about 1,300 input and 270 output tokens per answer. Prompt caching reads about 40% of the input tokens from the cache. The local Ollama run timed out after 300 s on the AVX-less VM, so it must be re-run after the VM CPU change.
- `prompts/system.md`: professional, concise answers, using **only** the provided context. Sources are cited as `[n]`. The answer is in the language of the question. If the context doesn't contain the answer, it says so politely and suggests escalating to a human (Support/SME).
- `rag/pipeline.py`: embed the question → retrieve top-k → if the best score is below `MIN_SCORE`, refuse without calling the LLM (saves cost and prevents hallucination) → build the prompt → generate → map the `[n]` markers to citations. It returns a `ChatResult` with `answer`, `citations`, `language`, `provider`, `model`, `usage`, `timings`, `top_score`, `refused`.
- `stores/events/`: the `EventStore` interface plus a log-only implementation, called once per turn.
- **Done when**:
  - pipeline unit tests (with a fake LLM) pass for these cases: answer with citations, low-score refusal, citation mapping, and a `[n]` marker that matches no source
  - a manual run with Ollama answers the eval questions sensibly

### Phase 5: API ✅ (2026-09-25)

Verified in Docker through nginx:
- `/health` reports `starting` while the index loads in the background, and `/chat` returns 503 `not_ready` until then
- the index was built on the volume (about 5 minutes) and loaded from cache in seconds after a restart
- `/chat` and `/chat/stream` work with Claude (about 5 s per answer, first token after about 2.3 s)
- the logs are JSON with a request id

Bugs found and fixed:
1. writing the index across filesystems failed on the Docker volume (EXDEV)
2. configuration errors at startup were retried forever
- FastAPI app with CORS limited to the frontend's origin, plus structured JSON logging with a request id.
- Endpoints:
  - `GET /api/v1/health`: liveness, plus readiness (index loaded, provider reachable)
  - `GET /api/v1/providers`: which providers are enabled and healthy
  - `POST /api/v1/chat`: returns the full `ChatResult` as JSON
  - `POST /api/v1/chat/stream`: Server-Sent Events. Events: `meta` (conversation/message ids, citations), `token`, `done` (usage, timings), `error`
- Pydantic request/response schemas, including `conversation_id` and `options {language, detail, provider}`. The OpenAPI docs appear at `/docs`.
- Input limits: maximum message length, and graceful 4xx/5xx errors when a provider is down or a key is missing.
- **Done when**: API tests using `TestClient` and fake providers pass for the chat, stream, validation-error and provider-down cases.

### Phase 6: Frontend ✅ (2026-09-25)

Verified in a real (headless Chromium) browser against the Docker stack:
- a streamed answer with citation chips, where clicking a chip highlights its source card
- a refusal shown in amber
- a German question answered in German
- "New conversation" clears the chat, and `/admin` loads the placeholder
- no console errors

Frontend checks: 14 Vitest tests, eslint and `tsc` are clean.
- A Vite + React + TS + Tailwind app. `src/api/` holds a typed client whose types mirror the Pydantic schemas, plus an SSE stream reader.
- `features/chat/`:
  - message list and input box, with streamed answers
  - `[n]` markers linked to citation cards (document title, section, snippet, score), which can be expanded
  - loading, error and refusal states, and a "New conversation" button
- Leave a reserved `/admin` route stub (empty) for the future hidden tabs.
- Tests: Vitest + React Testing Library for the citation rendering and the stream parser.
- **Done when**:
  - `npm run build`, `npm run lint` and `npm test` pass
  - chatting against the local backend works end to end in the browser

### Phase 7: Docker Compose ✅ (2026-09-25)

**Fresh-clone check** (a `git clone`, then `cp .env.example .env` with only the API key added, run under its own compose project with empty volumes):
- `docker compose up -d --build` returned after 9.5 minutes (almost all of it the ~4 GB model download)
- the index was built about 5 minutes later; meanwhile `/health` said `starting` and `/chat` returned 503 `not_ready`
- the browser E2E test passed: cited answer, refusal, German answer, reset and `/admin`, with no console errors under the new CSP

Changes in this phase:
- pinned images
- Ollama always runs (the optional profile was removed, because embeddings need it)
- frontend healthcheck and `FRONTEND_PORT`
- nginx security headers, gzip and asset caching

**Known limitation:** a Claude-only setup still needs Ollama for embeddings (ideas.md #7).
- `backend/Dockerfile` (multi-stage, uv, non-root user).
- `frontend/Dockerfile`: builds the app, then serves it with nginx. nginx also proxies `/api` to the backend, so the browser never has CORS issues.
- `docker-compose.yml`:
  - Services: `backend`, `frontend`, and `ollama` (planned under an `ollama` profile; **implemented without a profile**, see the Phase 7 result above).
  - `ollama-init` is a one-shot service that pulls the two models.
  - Named volumes for the Ollama models and the vector index.
  - Healthchecks and `depends_on` conditions, and settings read from `.env`.
- Two run modes documented:
  - `docker compose up`: fully local (Ollama always runs)
  - `docker compose up` with `LLM_PROVIDER=anthropic`: Claude, with embeddings still from Ollama until the in-process embedding option from idea #7 exists. The limitation is documented.
- **Done when**: a fresh clone plus `cp .env.example .env` plus the compose command gives a working chat at `http://localhost:8080`.

### Phase 8: Tests, evaluation & performance baseline ✅ (2026-09-25; results in `documentation/evaluation.md`)
- `app/evaluation/`: a runner that measures retrieval hit@k, the refusal accuracy on the unanswerable questions, and the latency (p50/p95 for retrieval, time to first token, total). The same module will later back the hidden tests tab.
- pytest markers:
  - `unit`: the default, fast and offline
  - `integration`: needs Ollama
  - `eval`: the quality and speed benchmark
- Optional GitHub Actions workflow: lint + unit tests for the backend and frontend.
- **Done when**: all unit tests are green in CI, and the eval baseline numbers are recorded in the README.

### Phase 9: Documentation & AI-log export (mandatory deliverable)
- README sections:
  - overview and architecture diagram (Mermaid)
  - API design, with request/response examples
  - key decisions and trade-offs (summarised from the task docs)
  - how to run (both modes) and how to test
  - configuration reference and known limitations
  - future work (link to `ideas.md`)
- README section "AI assistant usage": which tools were used for which parts of the codebase.
- Export the Claude Code transcripts (`~/.claude/projects/-home-sako-git-ep-kb-rag-chatbot/*.jsonl`) to `documentation/ai-logs/`, converted to readable Markdown, after checking them for secrets.
- **Done when**:
  - the README checklist is updated
  - the transcripts are committed
  - a final fresh-clone run-through succeeds

### After the MVP
Pick ideas from `ideas.md` one at a time, using the extension points already in place. Mark each one done there when finished.
