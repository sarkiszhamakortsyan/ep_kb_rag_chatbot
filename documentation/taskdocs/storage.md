# Task - Choose storage

## Description

1. Based on documentation/taskdocs/ the backend should ingest a small set of provided text documents (you should create 3-5 mock enterprise knowledge base articles), chunk them, store them in a local or in-memory vector store, and expose a chat endpoint. Make a research which approach will be better for our goal.
2. Document in this file your findings with explonation why we should, or should not use the approach.

---

## Findings (researched 2026-09-25)

### Sizing the problem first

- 3–5 mock articles of about 1–3 pages each give **roughly 30–100 chunks** at 300–500 tokens per chunk.
- With 768-dim float32 embeddings (`embeddinggemma`), that is **< 0.5 MB of vectors**.
- A brute-force cosine similarity search over 100 vectors takes **microseconds** in numpy, and it is *exact* (no approximate-NN recall loss).
- Scale is therefore not a factor for choosing the store. The deciding factors are simplicity, restart behaviour, explainability, and a clean path to production.

### Options compared

| Option | Type | For | Against |
|---|---|---|---|
| **In-memory numpy (custom)** | In-memory | No extra dependency or container, exact results, about 60 lines of fully explainable code, trivial to unit test, fastest for small corpora | Lost on restart, so embeddings must be recomputed (slow on CPU). No metadata filtering or ANN index. Single-process only |
| ChromaDB (embedded, `PersistentClient`) | Local, on disk | Persistence, metadata filters, suggested in the brief, runs in-process | Heavy dependency tree, frequent breaking API changes, and a black box to explain. Brings no benefit at ~100 chunks |
| ChromaDB (server container) | Local service | Same as above, plus a separate service | An extra container and network hop for nothing at this size |
| pgvector (Postgres in Docker) | Local service | Production-grade, SQL + metadata + HNSW index, persists | An extra container, schema/migrations, slower startup. Overkill for a prototype |
| FAISS / LanceDB / Qdrant | Embedded/service | Fast ANN at millions of vectors | Built for scale we don't have. Extra dependency |

### Decision: **in-memory vector store + on-disk embedding cache, behind a `VectorStore` interface**

1. **`InMemoryVectorStore`**: a numpy matrix of L2-normalised embeddings plus a parallel list of chunk metadata (`doc_id`, `title`, `section`, `chunk_id`, `text`). Search is a single matrix-vector dot product followed by top-k. A **similarity threshold** is also applied: if the best score is below it, the backend replies that "the documentation doesn't cover this" instead of letting the LLM guess. This is the basis for the polite refusal / human handoff feature.
2. **Embedding cache** (fixes the restart downside): after ingestion, vectors and metadata are saved to `data/index/index.npz` + `meta.json` on a Docker volume. The key is a hash of *(document contents + chunking parameters + embedding model name)*. On startup, if the hash matches, the index loads instantly. Otherwise it is re-ingested automatically. Changing a doc or the model therefore rebuilds the index, with no stale data.
3. **Interface** (`add`, `search`, `count`): Chroma or pgvector can be swapped in later without touching the RAG pipeline. This is the trade-off story for the README and the interview: "exact in-memory search is the right tool at prototype scale; here is the seam where pgvector would plug in at 100k+ chunks or multi-replica deployment."

**Why not Chroma or pgvector now**: they add a container or heavy dependency, startup time and failure modes, but they don't improve retrieval quality at this size. Brute-force search is *more* accurate than their ANN indexes. We should move to pgvector when any of these holds: the corpus grows beyond ~50–100k chunks, several backend replicas need a shared index, or we need incremental updates and metadata-filtered queries (e.g. per-product or per-customer ACLs).

### Chunking approach (part of ingestion)

- The KB articles are written as **Markdown** with a stable front-matter `id`/`title`. This gives citations a human-readable title and section.
- **Structure-aware chunking**: split on headings (`##`/`###`) first, then split long sections into windows of about 400 tokens with about 60 tokens of overlap. Each chunk keeps `doc_id`, `title`, and `section` (the heading path), so a citation can say *"Admin Guide › SSO Configuration"* rather than just a file name.
- The chat response returns `citations: [{doc_id, title, section, snippet, score}]`. The LLM is instructed to reference sources as `[1]`, `[2]`, mapped to those citations.

### Proposed mock KB articles (OmniCorp Solutions, 5 docs)

1. **OmniCorp Platform – SSO & User Provisioning Guide** (SAML/OIDC setup, SCIM, role mapping)
2. **API Rate Limits & Quotas Reference** (per-plan limits, burst rules, 429 handling, raising limits)
3. **Data Retention, Backup & GDPR Policy** (retention windows, export, deletion requests, regions)
4. **Webhooks & Integrations Configuration Manual** (event types, signing secrets, retries, Salesforce/Slack connectors)
5. **Support Tiers, SLAs & Escalation Process** (P1–P4 definitions, response times, when to hand off to a human)

These deliberately overlap a little (e.g. rate limits appear in both the API and the webhooks docs), so that retrieval has to rank sources and the answers can cite more than one document.
