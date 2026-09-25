# Task - Ideas 

## Description

Ideas that can be implement in addition in the Chatbot

## List of ideas

Mark every idea after you finish.

- Create a hidden menu with statistics about the usage.
- Check if its possible to have hidden menu with costs. Check for a method / AI suggestions how to optimize them.
- Method to write the response in professional language, clear and accurate. Provide more details only when requested.
- Option to Question / Answer in different languages.
- Add hidden tab with response history.
- Add hidden tab with unit, speed, and performance test.
- Option to enable / disable AI model use. For example, stop using Ollama and work only with Claude.

---

## Future-readiness design (added 2026-09-25)

> **Status**: none of the ideas above are implemented yet, and none are marked done. This section records the **seams** that the first version (MVP) of the code, storage and project structure must include, so that each idea can be added later **without refactoring**. Each seam is marked **MVP** (build it now, cheaply) or **Later** (only reserve room for it).

### Cross-cutting design rules for the MVP

1. **Every chat turn produces a structured result, not just text.** The RAG pipeline returns a `ChatResult` containing `answer`, `citations`, `language`, `provider`, `model`, `usage` (input/output tokens), `timings` (retrieval_ms, time-to-first-token, total_ms), `top_score`, and `refused` (bool). The MVP only logs it. Stats, costs, history and performance tabs will later just *persist and read* it.
2. **The API is versioned and forward-compatible.** Routes live under `/api/v1/…`. `ChatRequest` = `{ message, conversation_id?, options?: { language?, detail?, provider? } }`. Optional fields can be added later without breaking clients. Responses always carry `conversation_id` and `message_id`.
3. **Two separate provider interfaces**: `LLMProvider` (chat) and `EmbeddingProvider` (vectors), each resolved through a **registry** from configuration. They are never imported directly by the pipeline.
4. **Two separate kinds of storage**:
   - the **vector index** (derived data, rebuildable, in-memory + npz cache; see `storage.md`)
   - an **operational database** (source of truth for events, history, costs), which is **added later** as SQLite behind a repository interface.
5. **The "hidden" UI is a real admin area, not just hidden.**
   - Backend: all admin endpoints under `/api/v1/admin/*`, guarded by an `ADMIN_TOKEN` env var (disabled when unset).
   - Frontend: an `/admin` route opened by a keyboard shortcut. Hiding a menu is not security, so the token is what protects the data.

### Idea → seam mapping

| # | Idea | What the MVP must already have | What gets added later |
|---|---|---|---|
| 1 | Hidden statistics menu | `ChatResult` metrics (rule 1). A single `record_event(result)` hook called after every turn, a no-op/log-only implementation in the MVP | SQLite `chat_events` table plus `/api/v1/admin/stats` (questions/day, refusal rate, avg latency, top cited docs, provider split) and a Stats tab |
| 2 | Hidden costs menu + optimisation | Providers **return token usage**: Anthropic `usage.input_tokens/output_tokens`, Ollama `prompt_eval_count/eval_count`. `usage` is included in `ChatResult` | A pricing table in config (`$ per MTok` per model; Ollama = $0 or an estimated compute cost), a Costs tab, and optimisations: Anthropic **prompt caching** of the system prompt, fewer/shorter chunks (top-k tuning), routing simple questions to Haiku, and a **semantic answer cache** (reuse the `VectorStore` interface on past questions) |
| 3 | Professional, concise answers; detail on request | Prompts live in **versioned template files** (`backend/app/prompts/*.md`), not inline strings. The system prompt already enforces a professional, concise, cited style | An `options.detail = "concise" \| "detailed"` field chooses the template variant, plus a "More details" button in the UI that re-asks with `detail=detailed` |
| 4 | Q&A in different languages | **Multilingual embedding model** (`embeddinggemma`, already chosen), so questions in other languages still retrieve English docs. `language` field in `ChatResult`. Chunk metadata includes `lang` | `options.language` (`auto` by default = reply in the question's language), a language selector in the UI, and optionally KB articles in other languages (filtered via `lang` metadata) |
| 5 | Hidden response-history tab | `conversation_id` + `message_id` in the API from day 1. The frontend keeps the conversation in state | SQLite `conversations` + `messages` tables (question, answer, citations JSON, provider, timings) via a `HistoryRepository`, a History tab, and multi-turn context (question rewriting using earlier turns) |
| 6 | Hidden tab with unit, speed and performance tests | The **evaluation set is data**: `backend/tests/eval/questions.yaml` (question → expected `doc_id`s / must-refuse). The benchmark logic lives in an importable module `app/evaluation/`, used by pytest **and** callable from code | `POST /api/v1/admin/eval` runs the retrieval-accuracy and latency benchmark in the background and stores the results, and a Tests tab shows pass rate, p50/p95 latency and tokens/sec. (The web UI never shells out to `pytest`. It only calls the evaluation module, which is safe and read-only) |
| 7 | Enable/disable AI models (e.g. Claude only, no Ollama) | Provider **registry** driven by env: `ENABLED_LLM_PROVIDERS=ollama,anthropic`, `LLM_PROVIDER` (default), `EMBEDDING_PROVIDER`. `GET /api/v1/providers` reports which are enabled and healthy. *(Implemented early: a per-request `options.provider` and a model selector in the UI.)* The index cache key already includes the embedding model name (`storage.md`) | A runtime toggle in the admin area (persisted in SQLite `settings`) and a per-request `options.provider`. **Important**: "Claude only" also means *no Ollama for embeddings*. Anthropic has no embeddings API, so we add an alternative `EmbeddingProvider`: **in-process** (`sentence-transformers`/`fastembed` running the same `embeddinggemma` model, no Ollama container) or **Voyage AI** (API, Anthropic's recommended partner). Ollama becomes an optional Docker Compose **profile** (`docker compose --profile ollama up`) |

### Planned project structure (supports all of the above)

```
backend/
  app/
    api/v1/            chat.py, providers.py, admin/ (stats, costs, history, eval: later)
    core/              config.py (pydantic-settings), security.py (ADMIN_TOKEN)
    rag/               ingest.py, chunking.py, retrieval.py, pipeline.py -> ChatResult
    prompts/           system.md, (later) system_detailed.md
    providers/
      llm/             base.py, registry.py, ollama.py, anthropic.py
      embeddings/      base.py, registry.py, ollama.py, (later) local.py, voyage.py
    stores/
      vector/          base.py, memory.py            (later: pgvector.py)
      events/          base.py, log_only.py          (later: sqlite.py + migrations)
    evaluation/        runner.py, metrics.py         (used by tests and, later, admin)
  tests/               unit/, integration/, eval/questions.yaml
  data/kb/             mock KB articles (*.md)
frontend/src/
  api/                 typed client + types mirroring the Pydantic schemas
  features/chat/       chat UI, citations
  features/admin/      (later) stats, costs, history, tests tabs
docker-compose.yml     backend, frontend, ollama (+ ollama-init), volumes: models, index, db (later)
```

**The rule for the MVP**: build the interfaces and the `ChatResult`/`usage`/`timings` plumbing now, because it's cheap. Do **not** build SQLite, the admin endpoints, or the admin UI until an idea is picked up.
