<h1>Enterprise Knowledge Base RAG Chatbot</h1>

A prototype assistant for OmniCorp Solutions' Customer Success Managers (CSMs). It answers natural-language questions **strictly from internal documentation**, **cites the exact document sections** it used, and **refuses politely** (pointing to a human expert) when the documentation has no answer.

- **Backend:** Python 3.12 + FastAPI. Heading-aware chunking, exact in-memory vector search with an on-disk index cache, and a streaming RAG pipeline with citation mapping.
- **Frontend:** Vite + React + TypeScript + Tailwind. Streamed answers, clickable `[n]` citation chips and source cards.
- **LLM:** a local model via **Ollama** (`gemma3:4b`, embeddings `embeddinggemma`), or **Claude** with your own API key (`claude-opus-5`), selectable per question.
- **One command:** `docker compose up`.

> The original assignment brief and the progress checklist are at the [end of this file](#assignment-brief).

---

## Contents

- [Quick start](#quick-start)
- [Architecture](#architecture)
- [API](#api)
- [Key decisions and trade-offs](#key-decisions-and-trade-offs)
- [Testing and evaluation](#testing-and-evaluation)
- [Configuration](#configuration)
- [Project structure](#project-structure)
- [Known limitations and future work](#known-limitations-and-future-work)
- [AI assistant usage](#ai-assistant-usage)
- [Assignment brief](#assignment-brief)

---

## Quick start

Requirements: Docker with Compose v2, about 6 GB of disk space, and about 6 GB of free RAM. No GPU is needed.

```bash
git clone https://github.com/sarkiszhamakortsyan/ep_kb_rag_chatbot.git
cd ep_kb_rag_chatbot
cp .env.example .env        # optional: all settings have defaults
docker compose up -d --build
```

Open **http://localhost:8080**.

- **First start:** `ollama-init` downloads the two models (~4 GB). The backend then builds the vector index in the background (about 16 s on a 4-core laptop CPU). Until it's ready the UI shows *"Knowledge base loading…"* and the API answers `503 not_ready`. Later starts load the cached index within seconds.
- **Using Claude (recommended on machines without a GPU):** set `ANTHROPIC_API_KEY=...` in `.env`, then run `docker compose up -d`. Pick *anthropic* in the **Model** selector, or set `LLM_PROVIDER=anthropic` to make it the default. Ollama still runs, because it provides the embeddings.
- **Check the status:** `curl localhost:8080/api/v1/health`. The backend container isn't published: the UI's nginx forwards `/api/*` to it. For the interactive Swagger UI (`/docs`), run the backend locally (see below) and open `http://localhost:8000/docs`.
- **Stop:** `docker compose down` (add `-v` to also delete the models and the index).

### Local development (without Docker for the app)

```bash
docker compose up -d ollama ollama-init          # Ollama on 127.0.0.1:11434
cd backend  && uv sync && uv run uvicorn app.main:api --reload    # :8000, Swagger at /docs
cd frontend && npm ci && npm run dev                               # :5173, proxies /api -> :8000
```

---

## Architecture

```mermaid
flowchart LR
    U[CSM in browser] -->|HTTP| N[nginx<br/>frontend container]
    N -->|static files| SPA[React SPA]
    N -->|/api/*, SSE| API[FastAPI backend]

    subgraph Backend
        API --> P[RagPipeline]
        P --> R[Retriever]
        R --> E[EmbeddingProvider<br/>registry]
        R --> VS[(InMemoryVectorStore<br/>numpy cosine)]
        P --> L[LLMProvider<br/>registry]
        P --> EV[EventStore<br/>log-only]
        I["Ingest: load, chunk, embed"] --> VS
        I <--> C[(index cache<br/>volume)]
    end

    E --> O[Ollama<br/>embeddinggemma]
    L --> O2[Ollama<br/>gemma3:4b]
    L --> A[Anthropic API<br/>claude-opus-5]
    KB[(5 Markdown KB articles)] --> I
```

**Ingestion (at startup, in the background):**
1. Load `backend/data/kb/*.md`, whose front matter holds `id`, `title` and `lang`.
2. Split on headings, then pack paragraphs, lists and tables (kept whole) into windows of about 300 words with overlap. Each chunk keeps its heading path, e.g. `Configuring SAML 2.0 › Certificate rotation`.
3. Embed the chunks, including the heading path, with task-specific prompts.
4. Save the index to a volume. The cache key is a hash of the documents, the chunking parameters and the embedding model, so changing any of them triggers a rebuild.

**Answering a question:**
1. **Retrieve:** embed the question and take the top 6 chunks by cosine similarity.
2. **Refuse early:** if even the best chunk scores below `MIN_SCORE` (0.35), return a polite "not in the knowledge base, ask an expert" message **without calling the LLM**.
3. **Prompt:** chunks below `MIN_SCORE` are dropped. The rest are sent as numbered `<source>` blocks, under a system prompt that is kept byte-identical so it can be cached. The prompt is a template file (`backend/app/prompts/system.md`): answer only from the sources, cite every statement as `[n]`, refuse without citations when not covered, stay professional and concise, reply in the question's language, and treat the sources as data, never as instructions.
4. **Generate:** stream tokens from the selected provider.
5. **Cite:** map the `[n]` markers to sources and drop invented numbers. An answer without any valid citation counts as a refusal (`no_citations`), which works in any language.
6. **Record:** every turn produces a `ChatResult` with the answer, citations, provider/model, token usage, timings, top score and refusal reason. It's passed to an `EventStore` hook (log-only today), which the planned stats, costs and history features will persist.

**Startup and resilience:**
- The index loads in a background task, so the API is up immediately and reports progress in `/health`.
- Temporary failures, such as Ollama still starting, are retried. Configuration errors fail fast with a clear message.
- The index is written to a staging folder and swapped in, with the manifest written last. A crash never leaves a half-written index, and nothing is renamed across the Docker volume boundary.
- Logs are JSON lines with a request id (the `X-Request-ID` header, passed through by nginx).

---

## API

Base path `/api/v1`. The OpenAPI schema is generated by FastAPI (`/docs` on the backend). Every error has the same shape:

```json
{ "error": { "code": "provider_unavailable", "message": "Ollama did not respond within 300 s ..." } }
```

| Method & path | Purpose |
|---|---|
| `POST /chat` | Answer a question and return the full result as JSON |
| `POST /chat/stream` | The same, as **Server-Sent Events**: `meta` → `token`… → `done`, or `error` |
| `GET /health` | Liveness (always 200) and readiness: `status` `starting`/`ok`/`degraded`, index stats, Ollama status |
| `GET /providers` | The enabled LLM providers, their models, the default, and whether each is usable now |

**Request** (`POST /chat` and `/chat/stream`):

```json
{
  "message": "How long are backups retained?",
  "conversation_id": "optional-id",
  "options": { "provider": "anthropic" }
}
```

- `message` must be 1–4,000 characters and not blank.
- Unknown fields and options are **rejected** (422) instead of silently ignored. New optional fields, such as the planned `language` and `detail` options, can be added without breaking clients.

**Response** (shortened):

```json
{
  "conversation_id": "7f3c…",
  "message_id": "a91e…",
  "answer": "Backups are retained for **35 days** [1].",
  "citations": [
    { "number": 1, "doc_id": "kb-003", "title": "Data Retention, Backup & GDPR Policy",
      "section": "Backups and restore", "snippet": "Backup frequency: daily full snapshots…",
      "score": 0.6831, "chunk_id": "kb-003#004" }
  ],
  "refused": false,
  "refusal_reason": null,
  "provider": "anthropic",
  "model": "claude-opus-5",
  "usage": { "input_tokens": 1138, "output_tokens": 93, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0 },
  "timings": { "embed_ms": 48.1, "search_ms": 0.2, "time_to_first_token_ms": 2103.5, "generation_ms": 2650.9, "total_ms": 2701.4 },
  "top_score": 0.6831,
  "sources_used": 4,
  "stop_reason": "end_turn"
}
```

`refusal_reason` is one of:
- `low_score`: nothing relevant was retrieved, so the LLM wasn't called
- `no_citations`: the model said the documentation doesn't cover the question
- `model_refusal`: the provider declined the request

**Streaming events** (`/chat/stream`):

```text
event: meta    data: {"conversation_id": "…", "message_id": "…", "sources": [ …candidate citations… ]}
event: token   data: {"text": "Backups are "}
event: token   data: {"text": "retained for 35 days [1]."}
event: done    data: { …the same object as POST /chat… }
```

Errors before streaming starts (validation, unknown provider, index still loading) are normal HTTP errors. Errors during streaming arrive as `event: error` with `{code, message}`.

| Status | `code` | When |
|---|---|---|
| 400 | `invalid_provider` | Unknown or disabled provider |
| 422 | `validation_error` | Invalid request body |
| 502 | `provider_error` | The provider rejected the request |
| 503 | `not_ready`, `provider_unavailable`, `provider_not_configured` | Index still loading, provider down, overloaded or rate-limited, or API key missing |

---

## Key decisions and trade-offs

The full research, with arguments for and against each option, is in [`documentation/taskdocs/`](documentation/taskdocs/) (`research.md`, `storage.md`, `ideas.md`, `steps.md`).

| Decision | Why | Trade-off / when to revisit |
|---|---|---|
| **Python + FastAPI** | Best RAG and numeric ecosystem; Pydantic contracts and generated OpenAPI; native async streaming | Two languages in the repo (TypeScript frontend) |
| **Raw SDKs, no LangChain/LlamaIndex** | The pipeline is about 200 lines: every step is visible, testable and explainable; full control of the prompt, citations and refusals; fewer dependencies | Features like query rewriting or re-ranking must be written by hand |
| **In-memory exact vector search + disk cache** | About 50 chunks: brute force is *exact* and takes microseconds (p95 15 ms even at **50,000** chunks); no extra database container; the cache avoids re-embedding on restart | Single process, no metadata filters or incremental updates. The `VectorStore` interface lets pgvector replace it past about 100k chunks or with several replicas |
| **Heading-aware chunking** | Sections stay coherent, and the heading path gives human-readable citations | Tuned for structured Markdown articles, not arbitrary PDFs |
| **Similarity threshold before the LLM** | Off-topic questions are refused in about 50 ms at zero token cost | Can't separate *near-topic* unanswerable questions (they score like real ones), so the prompt handles those; calibration data is in `storage.md` |
| **"No valid citation = refusal"** | Language-independent refusal detection, no second LLM call | Depends on the model following the citation rule; measured at 100% on the eval set |
| **Provider registries (LLM and embeddings separate)** | Switch models by configuration or per request; fakes in tests; Anthropic has no embeddings API, so embeddings are their own interface | More indirection than hard-coding one model |
| **`claude-opus-5` default for Claude, server-side refusal fallback, cached system prompt** | Anthropic's current recommended default; a safety-filter refusal is retried on a fallback model; prompt caching cuts input cost | Opus costs more than Sonnet or Haiku: change `ANTHROPIC_MODEL` to trade quality for cost |
| **`gemma3:4b` + `embeddinggemma` for local use** | The best quality that runs on a CPU in about 6 GB of RAM; both are multilingual (German questions work over English documents) | About 5 tokens/s on a laptop CPU, so answers take about a minute (see below) |
| **SSE over POST (not WebSockets)** | One-directional token stream, works through nginx and plain HTTP, easy to test | `EventSource` only supports GET, so the frontend parses the stream itself (`src/api/sse.ts`) |
| **Background index loading** | The container is healthy at once; a slow first build doesn't block health checks | Clients must handle `503 not_ready` (the UI does) |
| **nginx serves the UI and forwards `/api`** | Same origin, so no CORS; security headers and CSP; gzip; SSE without buffering | One more container |
| **Future features as seams, not code** | Stats, costs, history, languages and the admin tabs are planned (`ideas.md`); `ChatResult`, `EventStore`, `options` and the registries already exist for them | Some structure exists before its feature does |

---

## Testing and evaluation

Details and raw numbers: **[`documentation/evaluation.md`](documentation/evaluation.md)**.

```bash
cd backend
uv run pytest                    # 101 unit + API tests, offline (fakes, mock HTTP), 95% coverage with --cov
uv run pytest -m perf -s         # speed tests: vector search to 50k chunks, API throughput
uv run pytest -m "integration or eval" -s                 # needs Ollama (docker compose up -d ollama)
uv run python -m app.evaluation.answers --provider anthropic --show    # 18-question benchmark (~$0.20)
uv run python -m app.evaluation.answers --provider ollama              # the same, locally
cd ../frontend && npm test       # 14 Vitest + Testing Library tests
```

CI (`.github/workflows/ci.yml`) runs the offline suites on every push: backend lint, types, tests, coverage and perf; frontend lint, types, tests and build; and a Docker image build.

**Evaluation set:** 18 questions (`backend/tests/eval/questions.yaml`):
- 10 answered by a single document
- 4 that need two documents
- 1 in German
- 3 that the knowledge base **can't** answer

An answerable question passes when it is answered, cites an expected document **and** contains every key fact. An unanswerable one passes when it is refused.

| | Claude `claude-opus-5` | Local `gemma3:4b` (4-core i5 laptop CPU) |
|---|---|---|
| Passed | **18 / 18** | 14 / 18 |
| Refusals correct | 3 / 3 | 2 / 3 (stated *"does not integrate with LDAP"*, which isn't in the docs) |
| Time to first token (p50) | 2.6 s | 59 s (mostly reading the ~1,300-token prompt) |
| Full answer (p50 / p95) | 4.8 s / 11.5 s | 79 s / 101 s |
| Cost per question | about $0.011 | $0 |

The local model's other three misses are incomplete answers (a missing header name, ratio or response time), not wrong ones. The recommendation: **Claude for quality and speed; local for privacy or offline use**, ideally with a GPU.

**Retrieval** (`embeddinggemma`, top 6):
- recall of the expected documents: **0.97**
- at least one expected document for every question
- query embedding: about 50 ms; retrieval p50 60 ms

**Off-topic refusals** (no LLM call) take about 50 ms. **Without the model:** the API handles about 450 requests/s (p95 54 ms). The index builds in 16 s and loads from cache in 5 ms.

---

## Configuration

All settings are environment variables, read from `.env` (see [`.env.example`](.env.example) for every option with comments). Only non-secret defaults are committed; `.env` is git-ignored.

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | Default chat provider: `ollama` or `anthropic` |
| `ENABLED_LLM_PROVIDERS` | `ollama,anthropic` | Providers that may be used; others are rejected |
| `ANTHROPIC_API_KEY` | – | Your key (bring your own) |
| `ANTHROPIC_MODEL` | `claude-opus-5` | e.g. `claude-sonnet-5` or `claude-haiku-4-5` for lower cost |
| `ANTHROPIC_EFFORT` | – | Optional: `low`/`medium` for faster, cheaper answers |
| `OLLAMA_CHAT_MODEL` / `OLLAMA_EMBED_MODEL` | `gemma3:4b` / `embeddinggemma` | Local models, pulled automatically |
| `OLLAMA_TIMEOUT_S` | `300` | Maximum wait for the first token |
| `TOP_K` / `MIN_SCORE` | `6` / `0.35` | Chunks sent to the LLM; refusal threshold (calibrated) |
| `CHUNK_MAX_WORDS` / `CHUNK_OVERLAP_WORDS` | `300` / `45` | Chunk size; changing them rebuilds the index |
| `FRONTEND_PORT` | `8080` | Web UI port |

---

## Project structure

```text
backend/
  app/
    api/            FastAPI routes (v1), schemas, error mapping, SSE, request-id middleware, startup state
    core/           settings (pydantic-settings), JSON logging
    rag/            chunking, ingest + index cache, retrieval, prompts, citations, pipeline
    prompts/        system.md, no_answer.md (prompt templates)
    providers/      llm/ (Ollama, Anthropic), embeddings/ (Ollama), config-driven registries
    stores/         vector/ (in-memory numpy store), events/ (per-turn hook, log-only)
    evaluation/     retrieval + answer benchmarks (CLI; reusable by a future admin tab)
  data/kb/          5 mock OmniCorp articles (SSO, API limits, retention/GDPR, webhooks, support SLAs)
  tests/            unit/, integration/, eval/ (questions.yaml), perf/, fakes.py
frontend/src/
  api/              typed client, SSE parser, types mirroring the backend schemas
  features/chat/    useChat hook, answer bubble with citation chips, source cards, page
  features/admin/   placeholder for the planned hidden tabs
documentation/
  taskdocs/         goal, research, storage, ideas, step-by-step plan (with results per phase)
  evaluation.md     test and benchmark results;  eval/  raw JSON summaries
  ai-logs/          complete AI assistant conversation logs (Markdown)
scripts/            export_ai_logs.py (transcript -> Markdown, secrets redacted)
docker-compose.yml  ollama, ollama-init, backend, frontend (nginx)
```

---

## Known limitations and future work

- **Single-turn questions.** Each question is answered on its own: `conversation_id` is returned and reused, but earlier turns aren't used as context, so a follow-up like *"and on the Enterprise plan?"* loses the topic. Multi-turn context (question rewriting over the history) is part of the planned response-history feature (`ideas.md` #5).
- **No authentication or rate limiting.** Fine for a local prototype. Before exposing it (especially with a Claude key), add auth such as SSO or an API gateway and per-user rate limits.
- **Ollama is always required** for embeddings, even when Claude answers. Anthropic has no embeddings API. A "Claude only" mode needs an in-process or Voyage embedding provider (`ideas.md` #7; the interface exists).
- **Local answers are slow on a CPU** (about 80 s per answer on a 4-core laptop CPU, mostly reading the prompt) and less reliable than Claude (14/18 vs 18/18; one unsupported claim). A GPU or Claude is recommended for interactive use.
- **Small knowledge base and evaluation set** (5 articles, 18 questions). Enough to validate the design, not to tune it statistically.
- **English knowledge base.** Questions in other languages work, and the answer comes in the question's language; there's no language selector yet (`ideas.md` #4).
- **Planned** (with the seams already in the code, see [`ideas.md`](documentation/taskdocs/ideas.md)): hidden statistics, costs, history and tests tabs; concise vs detailed answers; a model on/off toggle.

---

## AI assistant usage

The assignment asks which AI tools were used, and for which parts.

**The whole chat history is saved in the repository**, in **[`documentation/ai-logs/`](documentation/ai-logs/)**: one Markdown file per Claude Code session, with an index in its README.
- **Included:** every prompt I wrote, verbatim and timestamped, and every reply from Claude in full, including the context summaries written when a long session was compacted.
- **Shortened:** the tool calls Claude made (commands, file edits, their output) are kept but collapsed, with long ones cut at 1,500 characters.
- **Removed:** secrets are redacted. Claude's internal reasoning isn't part of the log.

A Claude Code hook (`.claude/settings.json` → `scripts/export_ai_logs.py`) regenerates the log after every assistant turn, so it never falls behind the conversation. The logs are committed with each phase. `python3 scripts/export_ai_logs.py --all` re-exports every session by hand.

| Tool | Used for |
|---|---|
| **Claude Code** (CLI, Claude Opus 5.5 model) | Everything in this repository was built in Claude Code sessions, directed and reviewed by me phase by phase (see the prompts in the logs): the research and decision documents in `documentation/taskdocs/`; the mock knowledge-base articles and evaluation set; all backend and frontend code and tests; the Docker and nginx setup; CI; the evaluation runs; this README; and the log exporter |
| **Me (the developer)** | The goal, requirements and task documents; approving the plan and each phase; decisions (Claude vs local model, branch and commit workflow, VM CPU change); reviewing results |
| **Claude API** (`claude-opus-5`) at runtime | Answer generation when the *anthropic* provider is selected. Part of the product, not a development tool |

Also used during development: a throwaway headless Chromium (Playwright) for browser end-to-end checks, which isn't part of the project dependencies.

---

<h1 id="assignment-brief">Assignment brief</h1>

Customer Success Managers (CSMs) at OmniCorp Solutions currently spend hours manually searching through hundreds of internal product manuals to answer complex client configuration questions. You have been contracted to build a prototype Retrieval-Augmented Generation (RAG) chatbot that allows CSMs to ask natural language questions and receive accurate, cited answers based strictly on internal documentation.

Your task is to build a full-stack application consisting of a backend API and a frontend chat interface. The backend should ingest a small set of provided text documents (you should create 3-5 mock enterprise knowledge base articles), chunk them, store them in a local or in-memory vector store, and expose a chat endpoint. The frontend must be a web-based UI where users can type questions, view the AI's response, and critically, see the specific document citations used to generate the answer.

As a Lead Engineer, we expect you to focus on system architecture, API design, and operational readiness. You are free to choose the backend language you are most comfortable with (we recommend **C# / .NET** or **Python** based on your background). The solution should be easy to run locally (e.g., via Docker Compose), well-structured, and include basic tests. You may use any external LLM provider (e.g., OpenAI, Anthropic, Groq) by allowing the reviewer to supply their own API key via environment variables, or use a local model via Ollama. Do not include any paid API keys in your submission.

<h2>DELIVERABLES</h2>
* A single public GitHub repository (or gist URL) containing your complete solution.<br />
* A backend service (e.g., C#/.NET Core, Python, or Node.js) implementing the document ingestion, RAG pipeline, and API endpoints.<br />
* A frontend UI (e.g., React, Next.js, or Vite in TypeScript) demonstrating the chat workflow and displaying source citations.<br />
* A docker-compose.yml file (or equivalent automated script) that spins up the entire stack seamlessly.<br />
* A README.md explaining your architectural decisions, API design, trade-offs, and instructions on how to run and test the system.<p>

**MANDATORY:** An export of your AI assistant conversation logs (e.g., Cursor chat history, Copilot export, or Claude transcripts) committed to the repository.

<h2>SUGGESTED TOOLS</h2>

**Frontend:** React, Next.js, or Vite + TailwindCSS<br />
**Backend:** ASP.NET Core (C#), FastAPI/Flask (Python), or Express/NestJS (Node.js)<br />
**Vector Store:** ChromaDB, pgvector (via Docker), or a simple in-memory cosine similarity implementation<br />
**AI/RAG:** Microsoft Semantic Kernel, LangChain, LlamaIndex, or raw SDKs<br />
**LLM:** OpenAI API, Anthropic API (Bring Your Own Key), Groq API, or local Ollama<p>

<h2>ON AI ASSISTANTS & FOLLOW-UP</h2>

We expect and encourage you to use AI assistants (GitHub Copilot, ChatGPT, Claude, Cursor, etc.) to accelerate your work.

**MANDATORY:** You must commit your AI assistant conversation logs to the repository and add a brief note in the README describing which tools were used and for what parts of the codebase. Be prepared to walk us through any block of code you submit. We will ask deep-dive questions on your architectural choices, API design, and trade-offs during the technical interview.

<h2>Plan</h2>
<b>- [x] Get better understanding of the task</b><br />
<b>- [x] Read information about every unknown term</b><br />
<b>- [x] Research which coding languages are the best to be used for the task</b><br />
<b>- [x] Check the "SUGGESTED TOOLS" and choose the best approaches</b><br />
<b>- [x] Check how to use local Ollama and Anthropic API together</b><br />
<b>- [x] Choose AI assistant - Claude</b><br />
<b>- [x] Make sure you log all the communication with the AI Assistant</b> (automatic export to `documentation/ai-logs/`)<br />
<b>- [x] Create a plan step by step</b><br />
- [ ] Create a hidden menu with statistics (planned; data is already recorded per turn)<br />
<b>- [x] Create documentation</b> (this README, `documentation/`)<br />
- [ ] Check if its possible to have hidden menu with casts. Check for a method / AI suggestions how to optimize them (planned; token usage is already recorded per turn)<br />
<b>- [x] Professional language in the response</b> (enforced by the system prompt; "more detail on request" is planned)<br />
- [ ] Option to Question / Answer in different language (partly: answers come in the question's language; a language selector is planned)<br />
- [ ] Add response history (planned)<br />
<b>- [x] If the client insists to have the answer (if there is no in documentation) choose what to do - like forward to human, or disregard in polite way</b> (polite refusal that points to an Internal SME Request)<br />
<b>- [x] Unit, speed, and performance test</b> (see `documentation/evaluation.md`)<br />
<b>- [x] Proceed with the plan</b><br />
