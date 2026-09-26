-- Runtime settings changed in the admin area (e.g. which models are enabled).
CREATE TABLE app_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,  -- JSON
    updated_at TEXT NOT NULL
);
