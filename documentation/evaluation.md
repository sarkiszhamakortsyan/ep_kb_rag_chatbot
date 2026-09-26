# Testing & evaluation baseline

Measured on 2026-09-25 on the development VM (4 vCPU, 15 GB RAM, no GPU). The Claude results were measured before, and the local-model results after, the VM was switched from an emulated CPU to the host CPU (i5-8300H with AVX2). Claude's latency is dominated by the API, not the CPU. The raw summaries are in [`eval/`](eval/).

## Test suites

| Suite | Command (from `backend/` or `frontend/`) | Needs | Count | Result |
|---|---|---|---|---|
| Backend unit + API | `uv run pytest` | nothing (fakes, mock transports) | 101 | ✅ all pass, **95% line coverage** (`--cov`) |
| Backend performance | `uv run pytest -m perf -s` | nothing | 5 | ✅ see "Speed" below |
| Backend integration | `uv run pytest -m integration` | Ollama | 2 | ✅ |
| Retrieval benchmark | `uv run pytest -m eval -s` or `uv run python -m app.evaluation.retrieval --k 6` | Ollama | 4 tests / 18 questions | ✅ |
| Answer benchmark | `uv run python -m app.evaluation.answers --provider anthropic` (or `ollama`) | Ollama (+ `ANTHROPIC_API_KEY` for Claude, about $0.20 per run) | 18 questions | ✅ Claude 18/18, local `ministral-3:3b` 17/18 |
| Frontend | `npm test` | nothing | 14 | ✅ |
| Browser E2E (manual) | headless Chromium against `docker compose up` | full stack | 3 questions, reset, `/admin` | ✅ (Phases 6–7) |

CI (`.github/workflows/ci.yml`) runs the offline suites on every push:
- backend: lint, type check, unit tests with coverage, and the perf tests
- frontend: lint, type check, tests and build
- Docker: image build

The LLM-dependent benchmarks run locally, because CI has no model or API key.

## Quality: evaluation set

`backend/tests/eval/questions.yaml` has 18 questions:
- 10 answered by a single document
- 4 that need two documents
- 1 in German
- 3 that the knowledge base does **not** answer (pricing, LDAP, mobile offline mode)

### Retrieval (`embeddinggemma`, k = 6), from [`eval/retrieval-baseline.json`](eval/retrieval-baseline.json)

| Metric | Value |
|---|---|
| Mean recall of the expected documents | **0.97** (the only miss is the support-process document for q13) |
| Hit rate (at least one expected document retrieved) | **1.00** |
| Top score: weakest answerable question / strongest unanswerable question | 0.416 / 0.516 |
| Top score of clearly off-topic questions | 0.03–0.18 |
| Retrieval latency, p50 / p95 (host CPU) | 60 ms / 73 ms |

`MIN_SCORE = 0.35` rejects off-topic questions without an LLM call and never rejects an answerable one. Near-topic unanswerable questions (LDAP 0.52, mobile 0.45) can't be separated by similarity alone, so the prompt makes the model refuse them (next table).

### Answers (Claude, `claude-opus-5`), from [`eval/answers-baseline-claude-opus-5.json`](eval/answers-baseline-claude-opus-5.json)

A question passes when:
- answerable: it isn't refused, it cites an expected document, **and** every key fact appears in the answer
- unanswerable: it's refused

| Metric | Value |
|---|---|
| Passed | **18 / 18** |
| Answer accuracy (15 answerable) | 1.00 |
| Refusal accuracy (3 unanswerable) | 1.00: 1 refused by `MIN_SCORE`, 2 by the model (no citations) |
| Key-fact coverage | 1.00 |
| German question answered in German | ✅ |

How the prompt got there (Phase 4): 13/18 → 17/18 → 18/18. The fixes were an explicit answer-language rule, no "related information" in refusals, and `TOP_K` raised from 5 to 6.

### Embedding models compared (2026-09-26)

The source cards used to show the raw cosine similarity as "N% match", and "61%" read like a grade. It isn't one: it measures how similar the question and the chunk are, not whether the answer is correct. With `embeddinggemma`, the right document is ranked first for every question even though its score is usually only 0.55–0.75. Four embedding models were compared on the 18 questions (k = 6):

| Embedding model | Recall | Right document first (MRR) | Top score, answerable: min / median | Top score, unanswerable: max | Query time p50 | Index build |
|---|---|---|---|---|---|---|
| **`embeddinggemma`** (kept) | 0.97 | 1.00 | 0.42 / 0.63 | 0.52 | **65 ms** | 16 s |
| `embeddinggemma`, "question answering" query prompt | 0.97 | 1.00 | 0.47 / 0.65 | 0.53 | 78 ms | 16 s |
| `qwen3-embedding:0.6b` | 0.97 | 1.00 | 0.65 / 0.75 | 0.61 | 261 ms | 77 s |
| `bge-m3` | 0.97 | 1.00 | 0.59 / 0.69 | 0.57 | 129 ms | 46 s |
| `nomic-embed-text` | 0.93 | 1.00 | 0.63 / 0.76 | 0.68 | 60 ms | 16 s |

**Findings:**
- **Ranking:** all models rank the right document first for every question. Other models score higher only because their scores run on a different scale, not because they retrieve better.
- **Thresholds:** only `qwen3-embedding` and `bge-m3` separate answerable from unanswerable questions by score, and only by a small margin that rests on three unanswerable questions. That doesn't justify a query 2–4× slower.
- **Decision:** `embeddinggemma` stays.

**Changes made:**
- **Source cards** now show a calibrated match level: **strong match** (at least 0.55), **good match** (at least 0.40) or **related**, with the exact similarity in the tooltip. Every source shown is cited by the answer, and correctly used sources can score below 0.45, so no level sounds negative.
- **The index fingerprint** now includes the embedding prompt format, so changing the format rebuilds the index. Previously only the model name counted.

## Speed

### End to end with Claude (17 LLM turns)

| | p50 | p95 |
|---|---|---|
| Time to first token | 1.4 s | 6.8 s |
| Full answer | 3.8 s | 10.8 s |
| Low-score refusal (no LLM call) | 0.8 s | – |

Tokens per answer: about 1,360 input (38% served from the prompt cache) and about 275 output. At the list prices for `claude-opus-5` ($5 / $25 per million input/output tokens, cache reads about 10% of the input price), that is roughly **$0.011 per question**. The whole 18-question benchmark costs about $0.20.

### Backend without the model (`pytest -m perf -s`)

| Measurement | Result |
|---|---|
| Vector search, 1,000 chunks × 768 dims | p95 0.2 ms |
| Vector search, **50,000** chunks × 768 dims | p95 15 ms (so exact brute-force search is fine far beyond this prototype) |
| Chunking the 5 articles | 1 ms |
| Loading the cached index (49 chunks) | 5 ms |
| API with a fake model, 200 requests at concurrency 20 | **450 req/s**, p50 36 ms, p95 54 ms |

### Local models (Ollama), compared on the host CPU

Measured after the VM was switched to the host CPU (Intel i5-8300H, 4 vCPU, AVX2/FMA, no GPU). Each model got the same 18 questions, retrieval and prompt. The raw summaries are in [`eval/ollama-models/`](eval/ollama-models/).

| Model | Passed | Answerable (15) | Unanswerable refused (3) | Key-fact coverage | Time to first token p50 | Full answer p50 / p95 |
|---|---|---|---|---|---|---|
| **`ministral-3:3b`** (default) | **16 / 18** (run 1: 15) | 13 | 3 | 0.92 | 43 s | **61 s** / 198 s* |
| **`ministral-3:3b` + prompt fix** (current) | **17 / 18** | 14 | 3 | 0.96 | 60 s | 74 s / 104 s |
| `qwen3.5:4b` (`think=false`) | 16 / 18 | 13 | 3 | 0.92 | 80 s | 119 s / 172 s |
| `gemma3:4b` (previous default) | 14 / 18 | 12 | 2 | 0.88 | 59 s | 79 s / 101 s |
| `llama3.2:3b` | 12 / 18 | 9 | 3 | 0.84 | 33 s | 48 s / 68 s |
| `granite4.2:3b` | 10 / 18 | 7 | 3 | 0.88 | 40 s | 61 s / 77 s |
| `phi4-mini` (3.8B) | 9 / 18 | 6 | 3 | 0.80 | 44 s | 66 s / 85 s |

\* One outlier: q13 generated the same 92 tokens as in run 1 but took 198 s instead of 58 s, which points to a busy VM rather than the model. Run 1 had p95 92 s.

The default, `ministral-3:3b` ([`eval/answers-baseline-ollama-ministral-3-3b.json`](eval/answers-baseline-ollama-ministral-3-3b.json)), was run twice:
- **Run 2 (baseline): 16/18.** It missed q06, which is correct but says "read-only for 30 days" instead of the checked phrase "30-day grace period". It also missed q11, which leaves out "1 request per 200 records".
- **Run 1: 15/18.** It had the same two misses plus q10, where it gave the 10% credit for 98.7% uptime instead of 25%.
- **Both runs** refused every unanswerable question and answered the German question in German.

`gemma3:4b` missed q07, q11 and q12 by leaving out one detail each. Its fourth miss, q17, was the only **unsupported claim** in the whole comparison: *"OmniCorp does not integrate with on-premise LDAP"*, which the knowledge base doesn't say.

**Prompt fix (2026-09-26).** Rule 4 of the system prompt ("give only the details the CSM needs") made the small model drop specific facts. It now also says: keep the specific numbers, ratios, limits, periods and conditions from the sources, use the sources' own terms (for example "grace period"), and check which row of a threshold table a value falls into. Results:
- **`ministral-3:3b`:** 17/18. q06 now passes, and q11 still leaves out "1 request per 200 records".
- **Claude:** still 18/18, with a median answer time of 3.8 s.

The local run was also slower than the earlier ones (p50 74 s against 61 s). The prompt only grew by about 60 tokens, worth about 3 s, so most of the difference is variance between runs on the shared VM.

**Conclusion:**
- **`ministral-3:3b`** gives the best trade-off on a CPU and is the default.
- **`qwen3.5:4b`** is the choice when answer quality matters more than speed.
- **Claude** is the choice when both matter.
- **A GPU** would make any of the local models interactive.

### Embeddings and index on the host CPU

| Measurement | Before (QEMU vCPU, no AVX) | After (host CPU, AVX2) |
|---|---|---|
| Query embedding | about 1 s | **about 50 ms** |
| Retrieval, p50 / p95 | 1.1 s / 3.3 s | **60 ms / 73 ms** |
| Off-topic refusal (no LLM call) | 0.8 s | **about 50 ms** |
| Full index build (49 chunks) | about 5 min | **16 s** |
| `gemma3:4b` generation | 2.5 tokens/s (RAG prompts timed out) | 5.4 tokens/s (RAG answer about 80 s; `ministral-3:3b` about 60 s) |

## Reproducing

```bash
docker compose up -d                       # Ollama on 127.0.0.1:11434, index volume
cd backend
uv run pytest                              # unit + API
uv run pytest -m perf -s                   # speed
uv run pytest -m "integration or eval" -s  # needs Ollama
uv run python -m app.evaluation.retrieval --k 6 --json ../documentation/eval/retrieval-baseline.json
uv run python -m app.evaluation.answers --provider anthropic --json ../documentation/eval/answers-baseline-claude-opus-5.json
uv run python -m app.evaluation.answers --provider ollama --json ../documentation/eval/answers-baseline-ollama-ministral-3-3b.json
OLLAMA_CHAT_MODEL=qwen3.5:4b OLLAMA_THINK=false uv run python -m app.evaluation.answers --provider ollama   # any other model
cd ../frontend && npm test
```
