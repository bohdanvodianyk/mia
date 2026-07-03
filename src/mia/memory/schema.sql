-- Mia SQLite schema. Idempotent: safe to run on every startup.
-- All timestamps are UTC ISO-8601 text (SQLite CURRENT_TIMESTAMP is UTC).

PRAGMA foreign_keys = ON;

-- ── Conversation ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    started_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    ended_at    TEXT,
    summary     TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    session_id  INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    role        TEXT NOT NULL,                    -- user | assistant | system | tool
    content     TEXT NOT NULL,
    modality    TEXT NOT NULL DEFAULT 'text',     -- text | voice
    ts          TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_chat_ts ON messages(chat_id, ts);

CREATE TABLE IF NOT EXISTS summaries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id       INTEGER NOT NULL,
    period_start  TEXT,
    period_end    TEXT,
    summary       TEXT NOT NULL,
    ts            TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

-- ── Long-term memory ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT,
    content     TEXT NOT NULL,
    source      TEXT,
    created_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    archived    INTEGER NOT NULL DEFAULT 0
);

-- ── Projects ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS projects (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active',
    description  TEXT,
    next_action  TEXT,
    created_at   TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    updated_at   TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',     -- open | done
    due_date    TEXT,
    created_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    done_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);

CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    content     TEXT NOT NULL,
    source      TEXT,
    created_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

-- ── Meetings ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS meetings (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    calendar_event_id  TEXT,
    title              TEXT,
    start_ts           TEXT,
    transcript_path    TEXT,
    summary            TEXT,
    action_items_json  TEXT,
    processed_at       TEXT
);

-- ── Settings & trust ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

CREATE TABLE IF NOT EXISTS action_trust (
    action_type  TEXT PRIMARY KEY,
    level        TEXT NOT NULL DEFAULT 'confirm'  -- confirm | auto (email_send always confirm)
);

-- ── Ops ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS token_usage (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    provider       TEXT NOT NULL,
    model          TEXT,
    input_tokens   INTEGER NOT NULL DEFAULT 0,
    output_tokens  INTEGER NOT NULL DEFAULT 0,
    cost_usd       REAL NOT NULL DEFAULT 0,
    purpose        TEXT
);
CREATE INDEX IF NOT EXISTS idx_token_usage_ts ON token_usage(ts);

CREATE TABLE IF NOT EXISTS events_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    level       TEXT NOT NULL,
    component   TEXT,
    message     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events_log(ts);
