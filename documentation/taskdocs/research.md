# Task - Research

## Description

1. Make a research which of the following coding languages will be the best choice for the backend of the task (documentation/taskdocs/goal.md) - Python, or Node.js. 
2. Make a research which of the following coding languages will be the best choice for the frontend of the task (documentation/taskdocs/goal.md) - React, Next.js, or Vite in TypeScript. Check also which one is better for this approach - TypeScript, or TailwindCSS
3. Check how the to implement LLM in the task described in documentation/taskdocs/goal.md file. The point is to use Ollama model that will be the best for the task. In addition, check how to add support of Claude with subscription.  
4. Document in this file your findings with explonation why we should, or should not use the approach

---

## Findings (researched 2026-09-25)

### Context that drives the decisions

- **Workload**: a small RAG prototype (3–5 KB articles), one chat endpoint, citations, `docker compose up` for the reviewer. Most of the work is orchestration (ingest → chunk → embed → retrieve → prompt → cite), not heavy compute.
- **Dev machine**: 4 CPU cores, 15 GB RAM, **no GPU**, Ollama not installed yet. The local model must run acceptably on CPU. The reviewer's machine is unknown, so we assume CPU too.
- **Planned features in the README**: multi-language Q&A, response history, a statistics menu, polite refusal or human handoff, and speed and performance tests. These affect the model and embedding choices.

### 1. Backend: Python vs Node.js → **Python (FastAPI)**

| Criterion | Python + FastAPI | Node.js + Express/NestJS |
|---|---|---|
| RAG/ML ecosystem | Best in class: official `ollama` and `anthropic` SDKs, numpy, LangChain/LlamaIndex, ChromaDB, sentence-transformers, eval tooling | Good, but smaller, and many RAG libraries are Python-first ports |
| Vector math (cosine similarity) | numpy, one line, vectorised | Manual loops or extra libraries |
| API design | Pydantic request/response models, auto-generated OpenAPI/Swagger at `/docs`, native async, SSE streaming | Similar with NestJS + class-validator, more boilerplate |
| Testing | pytest + FastAPI `TestClient`/httpx, easy to mock the LLM | Jest/Vitest, also fine |
| Brief's recommendation | Explicitly recommended ("C#/.NET or Python") | Allowed |
| One language across the stack | No (TS on the frontend) | Yes, the main advantage of Node |

**Decision: Python 3.12 + FastAPI.**
- **For**: the strongest RAG ecosystem, numpy for the in-memory vector store, free OpenAPI docs (helps the "API design" grading), clean async streaming, and the language the brief recommends.
- **Against / trade-off**: two languages in the repo. This is acceptable because the frontend is thin.
- **Why not Node.js**: its only real advantage is sharing TypeScript with the frontend, and that doesn't outweigh the weaker ML and vector tooling.
- **Orchestration: raw SDKs, not LangChain/LlamaIndex.** The pipeline is about 200 lines. Writing it directly makes every step easy to explain in the technical interview ("walk us through any block of code"). It avoids a large, fast-changing dependency and keeps full control over the prompt, the citation format, and the refusal behaviour. Semantic Kernel is .NET-centric and doesn't apply.

### 2. Frontend: React vs Next.js vs Vite + TypeScript → **Vite + React + TypeScript + TailwindCSS**

These options are not mutually exclusive. **React** is the UI library. **Next.js** is a full-stack framework built on React. **Vite** is a build tool/dev server that commonly hosts a React app. Similarly, **TypeScript vs TailwindCSS is not an either/or choice**: TypeScript is the programming language (type safety), and Tailwind is a CSS styling framework. The recommendation is to use **both**.

| Option | For | Against |
|---|---|---|
| **Vite + React + TS** | Pure SPA, instant dev server, tiny config, builds to static files served by nginx in Docker, clean separation from the FastAPI backend | No SSR (not needed for an internal chat tool) |
| Next.js | SSR, routing, API routes, strong for public/SEO sites | We already have a backend, so its server layer duplicates FastAPI. It needs a Node runtime container, adds App Router/RSC complexity, and brings no SEO benefit to an internal tool |
| Plain React (CRA-style) | Familiar | Create React App is deprecated. Vite is now the standard way to start a React SPA |

**Decision: Vite + React + TypeScript, styled with TailwindCSS.**
- **TypeScript: yes.** Typed API contracts (`ChatRequest`, `ChatResponse`, `Citation`) mirror the backend's Pydantic models, which catches integration bugs at compile time.
- **Tailwind: yes.** It's fast to build a clean chat UI with collapsible citation cards and a hidden stats panel, and there's no separate CSS architecture to maintain.
- **Streaming**: the UI consumes Server-Sent Events from the backend so tokens appear as they're generated. This matters a lot for CPU-bound local models.

### 3. LLM integration: Ollama + Claude

**Architecture**: the backend defines a small `LLMProvider` interface (`generate(messages) -> stream of tokens`) with two implementations, `OllamaProvider` and `AnthropicProvider`, selected by the environment variable `LLM_PROVIDER=ollama|anthropic`. Retrieval, prompting and citations are provider-independent.

> **Important**: Anthropic has **no embeddings API**. Embeddings are therefore **always produced locally by Ollama**, whichever chat LLM is selected. This also keeps the vector index stable when you switch the chat provider.

#### 3a. Best Ollama models for this task (CPU-only)

On CPU, chat workloads are limited to about 3–4B-parameter models. Anything larger is too slow for interactive chat. The candidates are:

| Model (Ollama tag) | Size | Why / why not |
|---|---|---|
| **`gemma3:4b`** ✅ default | ~3.3 GB | Strong instruction following for its size, 128K context, 140+ languages (covers the multi-language feature), no "thinking" tokens to wait for on CPU |
| `qwen3:4b` (alternative) | ~2.6 GB | Very good reasoning and multilingual support. It has a thinking mode, which **must be disabled** (`think=false`), or CPU latency explodes. Good second choice to benchmark |
| `llama3.2:3b` | ~2.0 GB | Fastest and very popular, but officially supports only 8 languages and follows grounding/citation rules less reliably |
| `phi4-mini` (3.8B) | ~2.5 GB | Good reasoning, weaker multilingual |
| `llama3.1:8b` / larger | 5 GB+ | Better answers, but too slow on 4 CPU cores. Worth considering only if the reviewer has a GPU (the tag is configurable) |

**Embedding model**: **`embeddinggemma`** (300M params, 768-dim, 100+ languages, fast on CPU). It matches the multi-language requirement. The fallback is `nomic-embed-text` (the most popular English default), and `qwen3-embedding:0.6b` / `bge-m3` if retrieval quality needs a boost. Note that embeddinggemma expects task prefixes (`task: search result | query: …` for queries, `title: … | text: …` for documents).

**Decision**: `OLLAMA_CHAT_MODEL=gemma3:4b`, `OLLAMA_EMBED_MODEL=embeddinggemma`, both configurable. We validate them with a small evaluation set of question/expected-source pairs, which becomes part of the tests, and switch to `qwen3:4b` if it scores better. Docker Compose runs the official `ollama/ollama` image with a one-shot init service that pulls both models on first start, stored on a named volume.

Ways to keep it fast on CPU: low `temperature` (0.1–0.2), `num_ctx` of about 4096, only the top 4–5 chunks in the prompt, streaming output, and `keep_alive` so the model stays loaded between questions.

#### 3b. Claude support: "with subscription"

There are two different Claude credentials, and they have different rules:

1. **Anthropic API key (BYOK)**: ✅ **the primary, recommended path.**
   - The reviewer sets `ANTHROPIC_API_KEY` in `.env` (never committed; we ship `.env.example`). The backend uses the official `anthropic` Python SDK and the Messages API with streaming.
   - Model configurable via `ANTHROPIC_MODEL`, default `claude-sonnet-5` (best quality/price for grounded Q&A). `claude-haiku-4-5` is the cheaper, faster option.
   - This is exactly what the brief asks for ("allowing the reviewer to supply their own API key via environment variables") and what Anthropic's terms prescribe for apps.
   - Claude also handles the multi-language and "politely refuse when not in docs" requirements very well.

2. **Claude subscription (Pro/Max/Team)**: ⚠️ **optional, for the developer's own local use only.**
   - Since 2026-06-15, subscription plans include a **monthly Agent SDK credit** (Pro $20, Max 5x $100, Max 20x $200). It covers the Claude Agent SDK, `claude -p`, and apps that authenticate with **your own** subscription through the Agent SDK.
   - **But**: Anthropic's docs say that "unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products". The credit is also per-user and cannot be shared.
   - Therefore **we should not** build "log in with your Claude subscription" for end users (the CSMs), and we should not ship a subscription token in the repo.
   - What we **can** do is add a third provider, `LLM_PROVIDER=claude-agent-sdk`. It uses the `claude-agent-sdk` Python package (which runs the Claude Code binary), authenticated by the developer's own subscription token supplied via env var. This lets the developer test with Claude using their subscription credit instead of paying for API usage.
   - Trade-offs: heavier container (it needs the Claude Code binary), higher latency than the raw API, and the agent's built-in tools must be disabled (we only need plain text generation).
   - **Recommendation**: implement the API-key provider first. Add the subscription provider only if you want it, clearly documented as "personal dev use".

### Summary of decisions

| Area | Decision |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic, raw `ollama` + `anthropic` SDKs, pytest |
| Frontend | Vite + React + TypeScript + TailwindCSS, SSE streaming, nginx container |
| Local LLM | Ollama `gemma3:4b` (alt. `qwen3:4b`, `think=false`), configurable |
| Embeddings | Ollama `embeddinggemma` (alt. `nomic-embed-text`), always local |
| Claude | `ANTHROPIC_API_KEY` BYOK via Messages API (`claude-sonnet-5` default). Optional personal-use Agent SDK provider for subscription credit |
| Provider switch | `LLM_PROVIDER` env var behind an `LLMProvider` interface |

### Sources

- [Best Ollama models 2026 (Morph)](https://www.morphllm.com/best-ollama-models), [Ollama models for CPU-only computers](https://www.nextaipulse.com/ollama-models-for-cpu-only-computers), [Best Ollama models for RAG (LMSA)](https://lmsa.app/blog/the-ultimate-guide-to-the-best-ollama-models-for-rag-in-2026/)
- [Best Ollama embedding models 2026 (Morph)](https://www.morphllm.com/ollama-embedding-models), [Ollama embeddings docs](https://docs.ollama.com/capabilities/embeddings)
- [Use the Claude Agent SDK with your Claude plan](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan), [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview)

### Addendum (2026-09-25): impact of `ideas.md`

Idea #7 ("work only with Claude, stop using Ollama") changes one earlier assumption. Embeddings are *by default* produced by Ollama, but they sit behind their own `EmbeddingProvider` interface, so a non-Ollama option (in-process `embeddinggemma` via sentence-transformers, or Voyage AI) can be added later. The Ollama container becomes an optional Docker Compose profile. LLM providers must also return **token usage**, which the future costs tab needs. See `ideas.md` → "Future-readiness design".

### Addendum (2026-09-25): findings from implementation (Phase 2)

- **Claude default model is now `claude-opus-5`** (instead of `claude-sonnet-5`), following Anthropic's current guidance to default to Opus 5 unless a model is chosen explicitly. `ANTHROPIC_MODEL` still switches it (e.g. `claude-sonnet-5` is cheaper, `claude-haiku-4-5` is the cheapest).
- **The Anthropic provider sends no `temperature`.** Opus 5 and Sonnet 5 reject sampling parameters. Answer style is controlled by the prompt, and latency and cost by the optional `ANTHROPIC_EFFORT`.
- **Refusal fallback is on by default.** Opus 5 can decline some requests through its safety classifiers (HTTP 200, `stop_reason: "refusal"`). The request uses `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`), which re-runs a declined request on Anthropic's recommended fallback model. It can be switched off with `ANTHROPIC_REFUSAL_FALLBACK=false`.
- **Prompt caching**: the system prompt is marked `cache_control: ephemeral`, and cache hits are reported in `usage.cache_read_input_tokens` (relevant for the costs tab, ideas.md #2).
- **CPU performance on the dev VM is much lower than expected.** The VM's virtual CPU is "QEMU Virtual CPU version 2.5+" with no AVX flags, so llama.cpp falls back to slow scalar code. Measured with `gemma3:4b`: about 2.5 tokens/s generation and 4–13 tokens/s prompt processing. A RAG prompt of about 1,500 tokens would take minutes. Options:
  1. expose the host CPU to the VM (e.g. `cpu: host` in Proxmox/libvirt), which is expected to be 5–10× faster
  2. use a smaller model (`gemma3:1b`, `qwen3:1.7b`) and fewer or shorter chunks
  3. use Claude for generation and keep Ollama only for embeddings (embedding one query takes about 0.1 s even here)
