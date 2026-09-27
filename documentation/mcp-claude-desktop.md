# The knowledge base in Claude Desktop (MCP)

This guide covers the `dev-mcp` branch. It explains how Claude Desktop uses the OmniCorp knowledge base through the project's MCP server, how to set it up, and how to use it day to day.

- The MCP server itself (tools, resources, the HTTP endpoint, tests) is described in the [features guide, section 6](features-guide.md#6-mcp-server-dev-mcp-only).
- Claude Code works the same way; the differences are noted where they matter.

## Contents

1. [How it works](#1-how-it-works)
2. [Setup](#2-setup)
3. [Usage](#3-usage)
4. [Checking that it is used](#4-checking-that-it-is-used)
5. [Keeping it up to date](#5-keeping-it-up-to-date)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. How it works

The [Model Context Protocol](https://modelcontextprotocol.io) (MCP) lets Claude Desktop use external tools. This project's MCP server (`backend/app/mcp/`) offers the knowledge base as such a tool. Claude Desktop starts it as a subprocess and talks to it over stdin/stdout ("stdio").

```text
Laptop                                         Machine with the repo (the same laptop, or a VM)
┌──────────────────────────────┐   SSH (stdio)  ┌──────────────────────────────────────────────────┐
│ Claude Desktop               │ ─────────────► │ uv run python -m app.mcp   (MCP server)          │
│  - /kb, /kb-claude, /kb-local│                │  ├─ retrieval: vector index + embeddings (Ollama) │
│    (skills)                  │ ◄───────────── │  └─ answer: Claude (API key) or local Ollama model│
│  - Claude decides to call    │  JSON-RPC      │                                                  │
│    ask_knowledge_base        │                │ Docker stack: Ollama on 127.0.0.1:11434          │
└──────────────────────────────┘                └──────────────────────────────────────────────────┘
```

1. You ask a question in Claude Desktop, either directly or with a `/kb` command.
2. Claude calls the server's `ask_knowledge_base` tool with the question and, optionally, a model.
3. The server runs the same pipeline as the web chat: it finds the best-matching documentation sections, has the chosen model write an answer from them only, and returns the answer with numbered citations. When the documentation doesn't cover the question, it returns `refused: true` instead of guessing.
4. Claude shows the answer, the citations and which model wrote it.

**What the server offers:**

| Name | Kind | Purpose |
|---|---|---|
| `ask_knowledge_base(question, model?, language?)` | tool | A cited answer from the full pipeline |
| `search_knowledge_base(query, k?)` | tool | The best-matching sections, for Claude to write its own answer |
| `kb://documents`, `kb://documents/{doc_id}` | resources | The article list, and one article in full |
| `ask`, `ask_claude`, `ask_local` | prompts | Ready-made requests for clients that show MCP prompts (Claude Code, a Claude Desktop chat's **+** menu) |

`model` accepts the same names as the web chat and the CLI: `claude` or `anthropic`, `local` or `ollama`, the model family (`ministral`) or the full model id (`ministral-3:3b`). Without it, the server's default model answers (`LLM_PROVIDER`).

**Two models are involved, and they are different things:**

- The **Claude Desktop model** (chosen in Desktop's model picker) is the assistant you talk to. It decides to call the tool and presents the result.
- The **knowledge-base model** (`claude` or `local`, chosen per question) writes the cited answer inside the server.

The MCP server is a tool, not a model, so it can't be added to Claude Desktop's model picker. The `/kb` commands are the shortcut instead.

**Where the server runs:** the chatbot needs the repo, `uv`, the vector index and Ollama for the embeddings. If they are on another machine (for example a VM), Claude Desktop starts the server there over SSH. That is what this project's setup uses; the steps below also cover the single-computer case.

---

## 2. Setup

### 2.1 Requirements

On the **machine with the repo**:
- the `dev-mcp` branch (or `main-mcp`), with `cd backend && uv sync` done
- the Docker stack running (`docker compose up -d`, or `python3 scripts/start.py docker`), because Ollama provides the embeddings
- `.env` in the repo root. For Claude answers it needs `ANTHROPIC_API_KEY`; for local answers the Ollama model is enough

On the **computer with Claude Desktop** (if it is a different one):
- Python 3 and an SSH client
- SSH login to the repo machine **with a key and without a password prompt**. Claude Desktop can't type a password, so check it first:

  ```bash
  ssh -T -o BatchMode=yes user@repo-host 'echo ok'   # must print "ok"
  ```

  If it asks for a password or fails, run `ssh-copy-id user@repo-host`, or load a key that has a passphrase with `ssh-add`.

### 2.2 A checkout that always has the MCP code (recommended)

The MCP code exists only on `dev-mcp`/`main-mcp`. If the same checkout is also used for other branches (such as `dev-features`), Claude Desktop's server breaks whenever that checkout is switched. A separate worktree avoids that:

```bash
cd /path/to/ep_kb_rag_chatbot
git worktree add ../ep_kb_rag_chatbot-mcp main-mcp
ln -s "$PWD/.env" ../ep_kb_rag_chatbot-mcp/.env         # share the settings and keys
cd ../ep_kb_rag_chatbot-mcp/backend && uv sync
cp -r ../../ep_kb_rag_chatbot/backend/data/index data/    # optional: reuse the index (else built in ~16 s)
```

Use `../ep_kb_rag_chatbot-mcp/backend` as the backend path below.

### 2.3 Install with the script (recommended)

`scripts/install_claude_desktop_mcp.py` does the whole setup. Run it **on the computer with Claude Desktop**.

**Repo on another machine** (the script is fetched from there and piped into Python):

```bash
ssh user@repo-host cat /path/to/ep_kb_rag_chatbot-mcp/scripts/install_claude_desktop_mcp.py \
  | python3 - --ssh user@repo-host --backend /path/to/ep_kb_rag_chatbot-mcp/backend
```

**Repo on the same computer:**

```bash
python3 /path/to/ep_kb_rag_chatbot-mcp/scripts/install_claude_desktop_mcp.py
```

What it does:
1. With `--ssh`, checks that the SSH login works without a password prompt, and that `uv` and the backend directory exist there. Nothing is changed if this fails.
2. Backs up `claude_desktop_config.json` (as `…json.bak-<date>`), then adds or replaces the `omnicorp-kb` entry. Other servers and Claude Desktop's own settings in that file are kept.
3. Starts the server exactly as Claude Desktop will and runs an MCP handshake. It prints the tools and prompts it found.
4. Writes the `/kb`, `/kb-claude` and `/kb-local` skills to `~/.claude/skills`.

Expected output:

```text
[ok] SSH to user@repo-host works without a password prompt
[ok] Backup: ~/.config/Claude/claude_desktop_config.json.bak-20260927-222107
[ok] Updated ~/.config/Claude/claude_desktop_config.json (servers: omnicorp-kb)
[ok] MCP handshake with 'omnicorp-knowledge-base'
     tools: search_knowledge_base, ask_knowledge_base
     prompts: ask, ask_claude, ask_local
[ok] Skills /kb, /kb-claude, /kb-local in ~/.claude/skills
```

Then **quit Claude Desktop completely and start it again**. Closing the window isn't enough if it keeps running in the tray.

Options: `--name` (server name, default `omnicorp-kb`), `--config` (another config file), `--skills-dir`, `--no-skills`. The config file is found automatically on Linux (`~/.config/Claude/`), macOS (`~/Library/Application Support/Claude/`) and Windows (`%APPDATA%\Claude\`).

### 2.4 Manual setup (alternative)

Open the config in Claude Desktop (*Settings → Developer → Edit config*) and add the server inside `"mcpServers"`. The file also holds Claude Desktop's own settings (`"preferences"` and others). Keep them, and make sure the result is valid JSON: a missing comma or a block outside `"mcpServers"` makes Claude Desktop ignore the whole file.

**Repo on another machine:**

```json
{
  "preferences": { "…": "Claude Desktop's own settings, keep them" },
  "mcpServers": {
    "omnicorp-kb": {
      "command": "/usr/bin/ssh",
      "args": [
        "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=30",
        "user@repo-host",
        "PATH=\"$HOME/.local/bin:$HOME/.cargo/bin:$PATH\" uv run --quiet --directory /path/to/ep_kb_rag_chatbot-mcp/backend python -m app.mcp"
      ]
    }
  }
}
```

**Repo on the same computer:**

```json
"omnicorp-kb": {
  "command": "/home/you/.local/bin/uv",
  "args": ["run", "--quiet", "--directory", "/path/to/ep_kb_rag_chatbot-mcp/backend", "python", "-m", "app.mcp"]
}
```

Use absolute paths: Claude Desktop doesn't load your shell's `PATH`. Check the file with `python3 -m json.tool ~/.config/Claude/claude_desktop_config.json`, then restart Claude Desktop. The `/kb` skills are only installed by the script.

### 2.5 Claude Code

```bash
claude mcp add omnicorp-kb -- uv run --directory /path/to/ep_kb_rag_chatbot-mcp/backend python -m app.mcp
```

Claude Code also offers the server's prompts as `/mcp__omnicorp-kb__ask …`, and it uses the same `~/.claude/skills`, so `/kb` works there too once the script has run.

---

## 3. Usage

### 3.1 The `/kb` commands (Claude Desktop's Code sessions and Claude Code)

Type the command, a space and the question:

```text
/kb What is the first-response time for a P1 ticket on Enterprise?
/kb-claude How long are backups kept?
/kb-local Which webhook events exist?
```

| Command | Model that writes the answer |
|---|---|
| `/kb` | the server's default (`LLM_PROVIDER`; `ollama` unless changed) |
| `/kb-claude` | Claude (needs `ANTHROPIC_API_KEY` on the repo machine) |
| `/kb-local` | the local Ollama model (`ministral-3:3b`) |

Each command passes the question unchanged to `ask_knowledge_base` and asks Claude to show the answer as returned, the citations as `[n] title › section (doc_id)`, and which model answered. If the knowledge base doesn't cover the question, Claude says so instead of answering from general knowledge.

A session only knows the commands that existed when it started. After installing, open a new session.

`/mcp__omnicorp-kb__ask` does **not** work in Claude Desktop: its Code sessions don't offer MCP prompts as commands and answer *"isn't a command here"*. Claude often still answers the text after it, but use `/kb` instead.

### 3.2 Plain questions

The server tells Claude what it covers, so a plain question such as *"What is the first-response time for a P1 ticket on Enterprise?"* usually makes Claude use it. To be sure, add *"use omnicorp-kb"*. To pick the model, add *"with claude"*, *"with local"* or *"with ministral-3:3b"*.

### 3.3 Regular chats (not Code sessions)

- The tools menu next to the message box (**+** / *Search and tools*) lists `omnicorp-kb`, where it can be switched on or off per chat.
- The server's prompts `ask`, `ask_claude` and `ask_local` are in the same **+** menu. They ask for the question in a small form.

### 3.4 Always using the knowledge base

To have every question answered from the knowledge base without a command, create a Claude Desktop project (for example *"OmniCorp KB"*) with these instructions:

```text
For every question, use the omnicorp-kb tool ask_knowledge_base (model "local" unless I say
"claude"). Show its answer with the numbered citations (document and section) and say which
model answered. If it returns refused: true, say that the knowledge base doesn't cover the
question; don't answer from general knowledge.
```

### 3.5 Permissions

The first time Claude uses the tool, Claude Desktop may ask for permission (**Allow once** / **Always allow**). In a Code session the session's permission mode decides; if it allows tools, there is no prompt.

---

## 4. Checking that it is used

- **In the conversation:** a collapsible step named `ask_knowledge_base` (or `omnicorp-kb`) appears above the answer. Expand it to see the question and model that were sent and the raw reply: `answer`, `citations`, `refused`, `model`.
- **Settings → Developer** lists `omnicorp-kb` with its status (running or failed, with a link to the log).
- **Logs on the Claude Desktop computer** (Linux paths; on macOS `~/Library/Logs/Claude/`):

  ```bash
  grep chat_turn ~/.config/Claude/logs/mcp-server-omnicorp-kb.log   # one line per answer: model, cited documents, timings
  grep omnicorp-kb ~/.config/Claude/logs/mcp.log | tail               # "Server started and connected successfully"
  grep -i "config" ~/.config/Claude/logs/main.log | tail              # config file errors
  ```

- **On the repo machine**, the running servers: `pgrep -af "python -m app.mcp"`.

Questions asked through Claude Desktop don't appear in the web app's admin History tab: the stdio server doesn't record them. The HTTP transport (`/api/mcp/`) does.

---

## 5. Keeping it up to date

After `main-mcp` changes:

```bash
cd /path/to/ep_kb_rag_chatbot-mcp
git fetch && git merge --ff-only origin/main-mcp
cd backend && uv sync          # only needed when dependencies changed
```

Then restart Claude Desktop, which starts the server again with the new code. Rerun the install script only when the command, the skills or the SSH host change, for example when the VM gets a new IP address.

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `main.log`: *Error reading or parsing config file (SyntaxError)*; no MCP servers at all | `claude_desktop_config.json` isn't valid JSON (missing comma, block outside `"mcpServers"`) | Restore a backup or rerun the install script (it stops on invalid JSON, so fix or move the file first). Check with `python3 -m json.tool` |
| `/mcp__omnicorp-kb__ask` *isn't a command here* | Claude Desktop's Code sessions don't offer MCP prompts as commands | Use `/kb`, `/kb-claude`, `/kb-local` |
| `/kb` isn't offered | The skills aren't installed, or the session started before they were | Rerun the install script (without `--no-skills`), then open a new session |
| `omnicorp-kb (CONNECTION_CLOSED)`, or the server fails right after starting | The backend path has no `app/mcp` (for example, the checkout is on `dev-features`), or `uv sync` wasn't run there | Point the config at a `main-mcp` worktree (section 2.2) |
| Install script: *SSH … without a password prompt did not work* | No key login, or the key needs a passphrase that isn't loaded | `ssh-copy-id user@repo-host` or `ssh-add`, then rerun |
| SSH timeout | The repo machine is off or has a new IP address | Start it, or rerun the script with the new address |
| Tool error *"The knowledge base is still loading"* or Ollama errors | The index is being built, or the Docker stack (Ollama) isn't running | Wait about 16 s, or start the stack |
| Tool error *Unknown model 'gpt'; use one of: …* | An unsupported model name | Use one of the names listed in the error |
| Claude answers but doesn't cite the knowledge base | Claude didn't call the tool | Use `/kb`, or add *"use omnicorp-kb"* |
| The model picker has no "omnicorp-kb" | Expected: it's a tool, not a model | Use `/kb-claude` or `/kb-local`, or a project (section 3.4) |
