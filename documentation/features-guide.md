# Features guide: how to use and test the add-ons

This guide covers the optional features on the **`dev-features`** branch, built on top of the official assignment (`main`). For each feature it explains what it does, how to use it, and how to check that it works. The MCP server is a separate version of the chatbot, on the `dev-mcp` branch, with its own section in that branch's copy of this guide.

**Contents**

1. [Start the stack](#1-start-the-stack)
2. [Chat features](#2-chat-features): more detail, answer language, follow-up questions, choosing the model by typing
3. [Admin area](#3-admin-area): History, Statistics, Costs, Tests, Settings
4. [Command-line client](#4-command-line-client)
5. [Claude-only mode (no Ollama)](#5-claude-only-mode-no-ollama)
6. [Automated tests and benchmarks](#6-automated-tests-and-benchmarks)
7. [A 10-minute demo script](#7-a-10-minute-demo-script)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Start the stack

```bash
git switch dev-features
cp .env.example .env            # first time only
```

Edit `.env`. Three settings matter for the features:

| Setting | Why | Example |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude answers, the Costs tab's advice, Claude benchmark runs | your key |
| `ADMIN_TOKEN` | Switches the admin area on (it doesn't exist without it) | `openssl rand -hex 24` |
| `OLLAMA_CHAT_MODEL` | The local model | `ministral-3:3b` (default) |

Then start the stack:

```bash
docker compose up -d --build
curl -s localhost:8080/api/v1/health     # wait for "ready": true
```

- **The chat** is at http://localhost:8080.
- **The admin area** is at http://localhost:8080/admin, or press **Ctrl+Shift+A** in the chat. Sign in with the `ADMIN_TOKEN` value.
- **After changing `.env`**, run `docker compose up -d backend` to apply it.
- **Switching back from `dev-mcp`:** run `rm -rf backend/app/mcp` first. It removes a Python cache folder that git leaves behind.

---

## 2. Chat features

### 2.1 More detail

**What it does:** answers are concise by default. **More detail** asks the same question again for a complete explanation: every relevant fact, condition and exception, still with citations.

**Use it:**
1. Ask a question.
2. Under the answer, click **More detail**.
3. A new turn appears, with the question tagged *More detail*.

**Check it:**
- The detailed answer is noticeably longer (about twice as long with Claude) and usually has headings.
- Every statement still has `[n]` citations.

Through the API:

```bash
curl -s localhost:8080/api/v1/chat -H 'Content-Type: application/json' \
  -d '{"message":"What happens to customer data after the contract ends?","options":{"provider":"anthropic","detail":"detailed"}}'
```

### 2.2 Answer language

**What it does:** by default the answer comes in the question's language. The **language selector** (globe icon in the header) fixes the answer language instead: English, Deutsch, Français, Español, Italiano, Português, Nederlands or Polski.

**Use it:**
1. Pick a language in the header. The browser remembers the choice.
2. Ask in any language.

**Check it:**
- Choose *Français* and ask in English: the answer is in French.
- Choose *Auto* and ask in German: the answer is in German.
- Product names and error codes stay exactly as in the sources.

API: `"options": {"language": "fr"}`. An unsupported code returns 422.

**Limitation:** the short "not covered" message for clearly off-topic questions is a fixed English template, because no model is called for it.

### 2.3 Follow-up questions

**What it does:** a follow-up like *"And on the Enterprise plan?"* keeps the topic of the conversation.
- The model first rewrites it into a self-contained question, using the last 3 turns.
- Search and the answer then use the rewritten question.
- The answer shows it as **"Understood as: …"**.

**Use it:**
1. Ask *"How many API requests per minute can a Business workspace make?"*.
2. Then ask *"And on the Enterprise plan?"*.

**Check it:**
- The second answer starts with *Understood as: … Enterprise plan?*
- It says **3,000 requests per minute**, citing *API Rate Limits & Quotas Reference*.
- **New conversation** (the pencil icon) starts fresh.

**Cost:** one extra short model call per follow-up, about 1.3 s with Claude and 4–15 s with the local model. First questions don't make this call.

### 2.4 Choose the model by typing

**What it does:** you can choose the model by typing a command in the chat, as well as with the dropdown in the header, which stays.

| Type | What happens |
|---|---|
| `/claude` or `/anthropic` | Switches to Claude. The dropdown follows, and a note confirms the switch |
| `/local`, `/ollama` or `/ministral` | Switches to the local model |
| `/claude How long are backups kept?` | Asks **only this question** with Claude. The question is tagged *Claude Opus · cloud*, and the selection stays |
| `/models` or `/help` | Lists the models, their commands and the selected one |

**Use it:**
- Type `/` to see the commands, and press **Tab** to complete the first one.
- The command names are built from the enabled models, so a model switched off in the admin **Settings** tab isn't offered.

**Check it:**
- **Switch:** with the local model selected, type `/claude`. The dropdown changes to *Claude Opus · cloud*, and a note appears.
- **One-off question:** type `/local` to switch back, then `/claude How long are backups kept?`.
  - The answer's footer says *Claude Opus*.
  - The dropdown still shows the local model.
  - **Regenerate** on that answer uses Claude again.
- **Unknown command:** `/gpt hi` shows *"Unknown command /gpt"*, and nothing is sent.
- **Paths:** `/v3/records:batch limits?` is sent as a normal question, because paths aren't commands.

---

## 3. Admin area

Open http://localhost:8080/admin, or press **Ctrl+Shift+A** in the chat, and enter the `ADMIN_TOKEN`.
- **Where the token is kept:** only in this browser tab. **Sign out** forgets it.
- **Without `ADMIN_TOKEN`** in `.env`, the sign-in explains that the admin area is switched off.
- **A wrong token** gets *"That token is not valid."*

Before trying the tabs, ask a few questions in the chat, some with Claude, some with the local model, and one off-topic (for example *"What is the weather in Paris?"*), so the tabs have data.

### 3.1 History

**What it shows:** every question and answer, newest first.

**Use it:**
- **Search** questions and answers.
- **Filter** by model (Claude, local, or *No model* for early refusals), by status (answered or not covered), and by date.
- **Click a row** for the full answer, its sources, tokens and timings. Follow-ups also show how they were understood.
- **Export CSV** downloads the filtered list.

**Check it:**
- The questions you just asked are listed.
- The off-topic one shows *Not covered* and *No model*.
- The CSV opens in Excel.

**Privacy:** entries are deleted after `HISTORY_RETENTION_DAYS` (default 90). `HISTORY_ENABLED=false` turns storage off completely.

### 3.2 Statistics

**What it shows** for the last 7, 30 or 90 days:
- questions, the share answered, the share not covered, and the median answer time
- a questions-per-day chart
- a models table: share, refusals, median and p95 time
- the most cited documents and sections
- **Documentation gaps:** recent unanswered questions, which are candidates for new articles. Click one to open it.

**Check it:** the totals match what you asked, and your off-topic question appears under *Documentation gaps*.

### 3.3 Costs

**What it shows:** estimates from the stored token counts and list prices:
- total cost, cost per question, and the saving from the prompt cache
- cost per day and per model
- **the same Claude questions with another model** (Sonnet, Haiku), to show what switching would save
- **How to reduce costs:** hints computed from the data, such as a smaller model, repeated questions an answer cache would make free, prompt size against `TOP_K`, and free early refusals

**Ask Claude for suggestions** sends **only the aggregated figures** (never questions or answers) to Claude and shows prioritised advice. One call costs about $0.02–0.03, and the exact cost is shown.

**Check it:**
- With a few Claude questions, the per-question cost is around $0.01, and Haiku shows about −80%.
- The local model costs $0, unless you set `LOCAL_COST_PER_HOUR`.

**Changing prices:** set `MODEL_PRICES` in `.env`, for example
`MODEL_PRICES={"claude-opus-5": {"input": 5, "output": 25, "cache_read": 0.5, "cache_write": 6.25}}` (USD per million tokens).

### 3.4 Tests

**What it does:** runs the 18-question benchmark against the live system, in the background.

**Use it:**
- **Retrieval:** checks that the right documents are found. It's free and takes a few seconds.
- **Answers:** the full pipeline with a chosen model, checking facts, citations and refusals.
  - With Claude it costs about **$0.20** and asks you to confirm first.
  - The local model is free but takes about 20 minutes on a CPU.
- While a run is going, a progress bar and a **Cancel** button appear. Only one run can happen at a time.
- **Recent runs** compares each run with the previous one of the same kind and model. Click a run for per-question results, failures first, with the answers.

**Expected results:**
- Retrieval: *recall 0.97 · hit rate 1.00*.
- Answers with Claude: *18 / 18 passed*.
- Answers with `ministral-3:3b`: 15–17 of 18, depending on the run.

Benchmark answers are not written to the history, so they don't affect the statistics or costs.

### 3.5 Settings

**What it does:**
- **Answer models:** switch Claude or the local model on or off and choose the **default**. This applies at once, with no restart; the chat's model picker updates on the next page load.
- **Limit:** only models allowed in `.env` (`ENABLED_LLM_PROVIDERS`) are listed.
- **Persistence:** choices survive a restart.
- **Embeddings:** shows what the search uses; it's set in the configuration.

**Check it:**
1. Switch the local model off and make Claude the default, then save.
2. Reload the chat: only Claude is offered.
3. Restart the backend: the choice is still there.
4. Switch back afterwards.

---

## 4. Command-line client

The CLI uses the same API, so the stack must be running. Run it from `backend/`:

```bash
uv run python -m app.cli health
uv run python -m app.cli providers
uv run python -m app.cli ask "How long are backups kept?" --model anthropic
uv run python -m app.cli ask "What happens after the contract ends?" --language de --detailed
uv run python -m app.cli ask "…" --json                      # the full JSON result
uv run python -m app.cli ask "/claude How long are backups kept?"   # model chosen by command
uv run python -m app.cli                                      # interactive session
```

**Without a local Python:**

```bash
docker compose exec backend python -m app.cli --url http://localhost:8000 ask "…"
```

**Interactive session commands:**
- `/model anthropic`: use Claude.
- `/lang de`: fix the answer language (`/lang auto` resets it).
- `/detail on`: detailed answers.
- `/new`: start a new conversation. Follow-ups work within one conversation.
- `/claude`, `/local` (also `/anthropic`, `/ollama`, `/ministral`): switch the model. `/claude <question>` asks one question with that model and keeps the selection. `/models` lists them.
- `/help` and `/quit`.

**Exit codes:** `0` answered, `2` not covered by the knowledge base, `1` error. Colours appear only on a terminal, and never when `NO_COLOR` is set.

**Check it:**
- `ask "What is the weather in Paris?"; echo $?` prints the refusal and `2`.
- In an interactive session, ask a question, then *"And on Enterprise?"*. The answer should keep the topic.

---

## 5. Claude-only mode (no Ollama)

This mode runs with **no Ollama containers**:
- **Answers** come from Claude.
- **Embeddings** run inside the backend with the **same `embeddinggemma` model**, so search results are identical: the vectors match Ollama's (cosine 1.000).

```bash
docker compose stop ollama                                      # if it is running
docker compose -f docker-compose.yml -f docker-compose.claude-only.yml up -d --build
```

- **First start:** the model downloads once (about 1.2 GB) into the `backend-models` volume, which takes about 1.5 minutes. After that it loads in about 2 s.
- **Needs:** `ANTHROPIC_API_KEY` in `.env`.

**Check it:**
- `curl -s localhost:8080/api/v1/health` shows `"embedding_model": "local:google/embeddinggemma-300m"` and `"ollama": null`.
- `docker compose ps` lists only `backend` and `frontend`.
- Answers still cite their sources.

**Back to the default:** `docker compose up -d --build`, which starts Ollama again.

---

## 6. Automated tests and benchmarks

| What | Command | Needs |
|---|---|---|
| Backend unit and API tests (159) | `cd backend && uv run pytest` | nothing |
| Speed tests | `cd backend && uv run pytest -m perf -s` | nothing |
| Frontend tests (35) | `cd frontend && npm test` | nothing |
| Retrieval benchmark | `cd backend && uv run python -m app.evaluation.retrieval --k 6` | Ollama |
| Answer benchmark (18 questions) | `cd backend && uv run python -m app.evaluation.answers --provider anthropic` | Ollama + key (about $0.20) |
| Follow-up benchmark (5 conversations) | `cd backend && uv run python -m app.evaluation.followups --provider anthropic` | Ollama + key (about $0.17) |

Expected benchmark results:
- **Retrieval:** recall 0.97, hit rate 1.00.
- **Answers:** Claude 18/18, local model 15–17/18.
- **Follow-ups:** 5/5 in context, against 0–1/5 when the same follow-ups are asked alone.

The feature tests live in `backend/tests/unit/`:
- `test_admin_api.py` covers history, statistics, costs, benchmark runs and settings.
- `test_followups.py`, `test_cli.py`, `test_pricing.py` and `test_local_embeddings.py` cover the rest.

On the frontend, the admin tests are in `src/features/admin/*.test.tsx`.

---

## 7. A 10-minute demo script

1. **Chat:**
   - Ask *"Which plans support SCIM user provisioning?"* with Claude. Show the citations and click a `[n]` chip.
   - Click **More detail**.
   - Ask *"And what about Business?"* to show a follow-up and its *Understood as* line.
   - Type `/` to show the model commands, then `/local How long are backups kept?` to ask one question with the local model while Claude stays selected.
2. **Language:** pick *Deutsch* and ask in English: the answer comes in German.
3. **Refusal:** ask *"What does the Enterprise plan cost?"*: it's not covered, and it points to an SME request.
4. **Admin area** (Ctrl+Shift+A):
   - **History:** filter to *Not covered* and open the entry.
   - **Statistics:** the documentation gaps.
   - **Costs:** the what-if with Haiku, and optionally **Ask Claude for suggestions**.
   - **Tests:** run **Retrieval** (seconds).
   - **Settings:** switch a model off, show the chat, then switch it back on.
5. **Terminal:** `uv run python -m app.cli ask "How long are backups kept?"`.
6. **Optional:** restart in Claude-only mode (section 5) to show it works without Ollama.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Admin sign-in says the admin area is switched off | `ADMIN_TOKEN` is empty | Set it in `.env`, then `docker compose up -d backend` |
| "That token is not valid" | Wrong token, or `.env` changed without a restart | Check the value and restart the backend |
| Tabs say the history is switched off | `HISTORY_ENABLED=false` | Set it to `true` |
| Chat or tests return 503 `not_ready` | The index is still building, or Ollama isn't up yet | Wait for `/api/v1/health` to report `"ready": true` |
| Claude is marked unavailable | No `ANTHROPIC_API_KEY` | Add it to `.env` and restart the backend |
| A benchmark says another run is in progress (409) | Only one run at a time | Wait, or **Cancel** it in the Tests tab |
| The local model is slow (about 1 minute per answer) | CPU-only inference | Use Claude for demos, or a GPU |
| An empty `app/mcp` package appears after switching from `dev-mcp` | A Python cache folder left behind by git | `rm -rf backend/app/mcp`, then rebuild |
