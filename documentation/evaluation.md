# Testing & evaluation baseline

Measured on 2026-09-25 on the development VM (4 vCPU, 15 GB RAM, no GPU). The Claude results were measured before, and the local-model results after, the VM was switched from an emulated CPU to the host CPU (i5-8300H with AVX2). Claude's latency is dominated by the API, not the CPU. The raw summaries are in [`eval/`](eval/).

## Test suites

| Suite | Command (from `backend/` or `frontend/`) | Needs | Count | Result |
|---|---|---|---|---|
| Backend unit + API | `uv run pytest` | nothing (fakes, mock transports) | 101 | ✅ all pass, **95% line coverage** (`--cov`) |
| Backend performance | `uv run pytest -m perf -s` | nothing | 5 | ✅ see "Speed" below |
| Backend integration | `uv run pytest -m integration` | Ollama | 2 | ✅ |
| Retrieval benchmark | `uv run pytest -m eval -s` or `uv run python -m app.evaluation.retrieval --k 6` | Ollama | 4 tests / 18 questions | ✅ |
| Answer benchmark | `uv run python -m app.evaluation.answers --provider anthropic` (or `ollama`) | Ollama (+ `ANTHROPIC_API_KEY` for Claude, about $0.20 per run) | 18 questions | ✅ Claude 18/18, local 14/18 |
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

## Speed

### End to end with Claude (17 LLM turns)

| | p50 | p95 |
|---|---|---|
| Time to first token | 2.6 s | 9.9 s |
| Full answer | 4.8 s | 11.5 s |
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

### Local model (Ollama, `gemma3:4b`), from [`eval/answers-baseline-ollama-gemma3-4b.json`](eval/answers-baseline-ollama-gemma3-4b.json)

Measured after the VM was switched to the host CPU (Intel i5-8300H, 4 vCPU, AVX2/FMA, no GPU).

| Metric | Value |
|---|---|
| Passed | **14 / 18** (answer accuracy 0.80, key-fact coverage 0.88) |
| Refusal accuracy | 2 / 3 |
| Time to first token, p50 / p95 | 59 s / 80 s (about 1,300 prompt tokens read at about 23 tokens/s) |
| Full answer, p50 / p95 | 79 s / 101 s (answers are short: about 64 output tokens) |
| Raw speed (warm) | generation 5.4 tokens/s, prompt reading about 57 tokens/s (short prompts) |

The failures:
- **q07 and q11** are correct but miss one exact detail (the `X-Omni-Signature` header name; "1 request per 200 records").
- **q12** is incomplete: it gives the hourly P1 updates but not the 15-minute first response.
- **q17** states *"OmniCorp does not integrate with on-premise LDAP"*. The knowledge base doesn't say that, so it's an **unsupported claim**, the most serious error type for this product. Claude refused the same question correctly.

**Conclusion:** use Claude when quality and latency matter; use the local model for privacy or offline use, preferably with a GPU and possibly a larger model.

### Embeddings and index on the host CPU

| Measurement | Before (QEMU vCPU, no AVX) | After (host CPU, AVX2) |
|---|---|---|
| Query embedding | about 1 s | **about 50 ms** |
| Retrieval, p50 / p95 | 1.1 s / 3.3 s | **60 ms / 73 ms** |
| Off-topic refusal (no LLM call) | 0.8 s | **about 50 ms** |
| Full index build (49 chunks) | about 5 min | **16 s** |
| `gemma3:4b` generation | 2.5 tokens/s (RAG prompts timed out) | 5.4 tokens/s (RAG answer about 80 s) |

## Reproducing

```bash
docker compose up -d                       # Ollama on 127.0.0.1:11434, index volume
cd backend
uv run pytest                              # unit + API
uv run pytest -m perf -s                   # speed
uv run pytest -m "integration or eval" -s  # needs Ollama
uv run python -m app.evaluation.retrieval --k 6 --json ../documentation/eval/retrieval-baseline.json
uv run python -m app.evaluation.answers --provider anthropic --json ../documentation/eval/answers-baseline-claude-opus-5.json
cd ../frontend && npm test
```
