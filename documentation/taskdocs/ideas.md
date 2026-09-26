# Task - Ideas 

## Description

Ideas that can be implement in addition in the Chatbot

## List of ideas

Mark every idea after you finish.

- Create a hidden menu with statistics about the usage. ✅ (dev-features, phase 11)
- Check if its possible to have hidden menu with costs. Check for a method / AI suggestions how to optimize them.
- Method to write the response in professional language, clear and accurate. Provide more details only when requested.
- Option to Question / Answer in different languages.
- Add hidden tab with response history. ✅ (dev-features, phase 10; follow-up questions come in phase 18)
- Add hidden tab with unit, speed, and performance test.
- Option to enable / disable AI model use. For example, stop using Ollama and work only with Claude.
- Check if we can build the whole chatbot as an MCP server. (added 2026-09-26, from the README)
- Option to use it over a CLI. (added 2026-09-26, from the README)

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

---

## Implementation plan (2026-09-26)

The list above has nine ideas. The README list adds two (MCP server, CLI) that weren't here before, so they are now on the list too. This plan covers all of them, in the order I recommend. Each phase is small enough to review on its own and ends like the build phases: tests green, docs updated, a report, and your review before the next one.

### Where each idea stands today

| # | Idea | Already done | Missing |
|---|---|---|---|
| 1 | Statistics menu | Every turn produces a `ChatResult` with usage, timings, provider, top score and refusal. The `EventStore` hook is called once per turn (it only logs) | Storage, admin API, Stats tab |
| 2 | Costs menu + optimisation | Token usage per turn (Anthropic and Ollama), prompt caching of the system prompt | Price table, cost per turn, Costs tab, optimisation hints |
| 3 | Professional answers, detail on request | The system prompt enforces a professional, concise, cited style. `options` in the request exists | `options.detail` and a "More detail" button |
| 4 | Several languages | Answers come in the question's language (the German eval question passes), and the embeddings are multilingual | `options.language` and a language selector |
| 5 | Response history | `conversation_id` and `message_id` on every response | Storage, History tab. Multi-turn follow-ups are a separate step (phase 16) |
| 6 | Tests tab | The benchmarks are an importable module (`app/evaluation/`) with JSON summaries | Admin endpoint to run them, stored results, Tests tab |
| 7 | Enable/disable models | `ENABLED_LLM_PROVIDERS`, per-question model picker, `/api/v1/providers` | Runtime switch in the admin area; "Claude only" without Ollama needs a non-Ollama embedding provider |
| 8 | MCP server | The pipeline and retrieval are reusable services (`app/services.py`) | An MCP server exposing them as tools |
| 9 | CLI | The streaming API | A command-line client |

### Recommended order

The admin features (#1, #2, #5, #6) share one foundation: a database for chat events, admin authentication and the admin page shell. That foundation comes first and is built once. Quick, independent features come next, and the biggest infrastructure change (Claude only, without Ollama) comes last.

#### Phase 10: admin foundation + response history (#5). Size: M ✅ (2026-09-26, branch `dev-features`)
- **Storage:** SQLite (a file in a Docker volume, no new service) behind the existing `EventStore` interface: `SqliteEventStore` with a `turns` table. It holds the time, conversation and message ids, question, answer, citations (JSON), provider, model, language, refusal and reason, top score, token usage and timings. Schema migrations use plain versioned SQL files.
- **Privacy:** questions can contain customer data, so recording is configurable (`HISTORY_ENABLED`, default on) with a retention period (`HISTORY_RETENTION_DAYS`, default 90) and a purge on startup.
- **Admin API:** `/api/v1/admin/*`, protected by `ADMIN_TOKEN`. When the token isn't set, the admin API is switched off (404). Endpoints: `GET /admin/history` (paged, filter by date, provider, refused, text search) and `GET /admin/history/{message_id}`.
- **Admin UI:** `/admin` becomes a real page. It asks for the token once (kept in session storage) and has a tab bar (History now; Stats, Costs and Tests added by later phases). A keyboard shortcut in the chat (Ctrl+Shift+A) opens it. Hiding a page isn't security; the token is.
- **History tab:** a table of turns (time, question, model, time taken, refused), a detail view with the full answer and its sources, and CSV export.
- **Tests:** repository tests on a temporary SQLite file, admin auth tests (no token, wrong token, disabled), API tests, frontend tests for the tab.

#### Phase 11: statistics (#1). Size: S ✅ (2026-09-26)
- `GET /api/v1/admin/stats?from=&to=`: questions per day, refusal rate (split by reason), answer time p50/p95 per model, share per model, most cited documents and sections, and a list of recently refused questions. That last list shows which documentation is missing, the most useful number for a knowledge-base owner.
- **Stats tab:** a few KPI cards plus simple charts (one small chart library, or plain SVG).
- Computed with SQL from the `turns` table, so no new data is needed.

#### Phase 12: costs + optimisation hints (#2). Size: S–M
- **Price table in configuration:** $ per million input, output and cache-read tokens per model, with Anthropic list prices as defaults. Local models are $0, with an optional estimated compute cost per hour.
- **Cost:** each turn's cost is computed and stored. `GET /admin/costs` shows totals per day and model, cost per question, and the share saved by the prompt cache.
- **Optimisation hints:** rule-based, computed from the data. Examples: "X% of questions are refused before the LLM (free)", "a smaller Claude model would have cost $Y for the same questions", "the prompt cache saves Z%".
- **Optional "Ask Claude for suggestions" button:** sends only the aggregated numbers, never questions or answers, and shows its own cost before running.
- Further savings, each measured with the answer benchmark before adoption:
  - a semantic answer cache, which reuses the vector store on past questions
  - a lower `TOP_K`
  - routing simple questions to a cheaper model

#### Phase 13: tests tab (#6). Size: S
- `POST /api/v1/admin/eval` starts the retrieval benchmark and optionally the answer benchmark, for a chosen model, as a background job. Only one runs at a time, and a Claude run shows its estimated cost first.
- Results are stored in SQLite. `GET /admin/eval` lists the runs, and the tab shows pass rate, recall, p50/p95 and failed questions, compared with the previous run.
- The web UI calls the evaluation module and never runs `pytest` or shell commands.

#### Phase 14: detail level + language (#3, #4). Size: S
- `options.detail = "concise" | "detailed"` chooses the prompt template (`system.md` or a new `system_detailed.md`). Each answer gets a **More detail** button, which re-asks the same question in detailed mode.
- `options.language = "auto" | "en" | "de" | …` adds one line to the prompt ("Answer in German"). `auto` stays the default and keeps today's behaviour. The header gets a language selector.
- **Tests:** add a few eval questions per language and a detailed-mode check. The answer benchmark must stay at 18/18 on Claude and 17/18 on the local model.

#### Phase 15: CLI (#9). Size: S
- `omnicorp-kb` is a small Python command installed with the backend package. It talks to the HTTP API, so it works against the Docker stack.
- `omnicorp-kb ask "question" [--model anthropic|ollama] [--json]` streams the answer and then prints the sources. Plain `omnicorp-kb` opens an interactive session, where `/new` starts a new conversation and `/model` switches the model. Further commands: `omnicorp-kb health` and `omnicorp-kb providers`.
- Colours are turned off automatically when output goes to a file. Exit codes: 0 answered, 2 not covered, 1 error, so scripts can use it.
- **Tests:** the CLI against a mocked API.

#### Phase 16: MCP server (#8). Size: M
- **Answer to the question:** yes. The chatbot can be offered as an **MCP server**, so assistants such as Claude Desktop or Claude Code can use the knowledge base directly. Two tools:
  - `search_knowledge_base(query, k)` returns the matching sections with document, section and score. The calling assistant writes the answer itself.
  - `ask_knowledge_base(question, model?)` runs our full pipeline and returns the answer with citations. Answers stay under our rules: sources only, refusals, citations.
  - The KB articles are also offered as MCP **resources** (`kb://kb-003`) so a client can open the full source document.
- **Transport:** built with the official MCP Python SDK.
  - stdio: the client starts `omnicorp-kb mcp`.
  - streamable HTTP: mounted in the existing backend under `/mcp`, protected by a token, so one Docker stack serves the web UI, the API and MCP.
- **Tests:** the tools called through the SDK's in-memory client. The README gets setup snippets for Claude Desktop and Claude Code.

#### Phase 17: model switches and "Claude only" (#7). Size: M–L
- **Admin switches:** a Settings tab to switch providers on and off at runtime (stored in SQLite, applied without a restart), and to choose the default model.
- **"Claude only" also removes Ollama from the embeddings**, which Anthropic doesn't provide. Two options:
  1. **In-process embeddings** of the same `embeddinggemma` model inside the backend (`sentence-transformers` or an ONNX runtime). No Ollama container is needed and the index stays the same. The cost is a backend image about 1 GB larger and slower cold starts.
  2. **Voyage AI** (Anthropic's recommended embedding partner): a small image, but an extra paid API key and a full re-index.
- **Recommendation:** option 1, keeping Ollama as an optional Compose profile for local generation. The Phase 3 rule already covers the switch: the fingerprint includes the embedding model, so the index rebuilds itself.

#### Phase 18: follow-up questions (the rest of #5). Size: M
- Turns now live in SQLite (phase 10), so the pipeline can rewrite a follow-up ("and on Enterprise?") into a stand-alone question using the last turns before retrieval. That takes one short extra LLM call; on the local model it adds about 15–20 s.
- **Tests:** a small multi-turn eval set.

### Decisions needed before starting

1. **Order:** the recommended order starts with the admin foundation. An alternative is to do the quick wins first (phases 14 and 15, about half a day each).
2. **History privacy:** store full questions and answers (the recommendation, with a 90-day retention period), or only metrics without text.
3. **Charts:** a small chart library (for example Recharts, about 100 KB) or hand-made SVG charts (no dependency, simpler charts).
4. **"Claude only" embeddings:** in-process (recommended) or Voyage AI.

### Progress

The features are built on the **`dev-features`** branch. `main` and `dev` stay the official submission.

**Phase 10 ✅ (2026-09-26): admin foundation + response history.**
- **Backend:**
  - `SqliteHistory` (`app/stores/history/`) with versioned SQL migrations, retention purge, and filter and paging queries.
  - It's attached to the existing `EventStore` hook through `FanOutEventStore` (log + history).
  - `/api/v1/admin/{session,history,history/{id},history/export.csv}`, protected by `ADMIN_TOKEN` (`app/core/security.py`).
- **Frontend:** `/admin` with token sign-in (session storage), History tab with search, filters, paging, detail panel and CSV export, and Ctrl+Shift+A from the chat.
- **Tests:** backend 120 (18 new: store and admin API), frontend 21 (4 new).
- **Checked end to end:** in Docker, with screenshots in light and dark mode.

**Phase 11 ✅ (2026-09-26): statistics.**
- **Backend:** `compute_stats` (`app/stores/history/stats.py`) builds the numbers with SQL over `turns`, including SQLite `json_each` over the stored citations. The endpoint is `GET /api/v1/admin/stats?from&to` (default the last 30 days, at most 366 days, `invalid_range` otherwise).
- **Frontend:**
  - The Statistics tab is now the first admin tab. Each tab has its own address (`/admin/stats`, `/admin/history`), so back/forward and bookmarks work.
  - It shows the totals, a plain-SVG daily chart that measures its container so text keeps its size, a models table, the most cited documents and sections, and the documentation gaps, which open the answer details.
- **Tests:** backend 124 (4 new), frontend 21 (the admin test now covers both tabs).
- **Checked end to end:** with 11 mixed questions (Claude, local, early refusals), with screenshots on desktop, in dark mode and on mobile. A mobile overflow was found and fixed.

