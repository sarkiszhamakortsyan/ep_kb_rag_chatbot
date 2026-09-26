-- Benchmark runs started from the admin Tests tab (ideas.md #6).
CREATE TABLE eval_runs (
    id          TEXT    PRIMARY KEY,
    kind        TEXT    NOT NULL,  -- "retrieval" | "answers"
    provider    TEXT,
    model       TEXT,
    status      TEXT    NOT NULL,  -- running | done | failed | cancelled | interrupted
    started_at  TEXT    NOT NULL,
    finished_at TEXT,
    total       INTEGER NOT NULL,
    done        INTEGER NOT NULL,
    summary     TEXT,              -- JSON metrics
    results     TEXT,              -- JSON list, one entry per question
    error       TEXT
);

CREATE INDEX eval_runs_started_at ON eval_runs (started_at);
