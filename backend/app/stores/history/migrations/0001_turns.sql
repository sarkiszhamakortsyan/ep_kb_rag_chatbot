-- One row per chat turn (question + answer + metrics). Times are ISO-8601 UTC strings.
CREATE TABLE turns (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at            TEXT    NOT NULL,
    conversation_id       TEXT    NOT NULL,
    message_id            TEXT    NOT NULL UNIQUE,
    question              TEXT    NOT NULL,
    answer                TEXT    NOT NULL,
    citations             TEXT    NOT NULL,  -- JSON array of cited sources
    refused               INTEGER NOT NULL,  -- 0/1
    refusal_reason        TEXT,
    provider              TEXT,              -- NULL when no LLM was called
    model                 TEXT,
    language              TEXT,
    stop_reason           TEXT,
    top_score             REAL    NOT NULL,
    sources_used          INTEGER NOT NULL,
    input_tokens          INTEGER NOT NULL,
    output_tokens         INTEGER NOT NULL,
    cache_read_tokens     INTEGER NOT NULL,
    cache_creation_tokens INTEGER NOT NULL,
    embed_ms              REAL    NOT NULL,
    search_ms             REAL    NOT NULL,
    ttft_ms               REAL,
    generation_ms         REAL    NOT NULL,
    total_ms              REAL    NOT NULL
);

CREATE INDEX turns_created_at ON turns (created_at);
CREATE INDEX turns_conversation ON turns (conversation_id);
