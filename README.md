# Mia

A single-user personal AI assistant that lives in Telegram — *Mi IA*.
Reactive (calendar, email, docs via text or voice), proactive (morning briefing,
meeting prep), and thoughtful (memory, projects, meeting knowledge).

Built phase by phase — see [`personal_assistant_dev_plan_v2.md`](personal_assistant_dev_plan_v2.md).
**Status: Phase 0 (scaffold) complete.**

## Setup (WSL2 + conda)

```bash
# 1. Activate the dedicated env (created with: conda create -n mia python=3.12)
conda activate mia

# 2. Install (editable, with dev tools)
pip install -e ".[dev]"

# 3. Configure
cp .env.example .env   # then fill in what you have (Anthropic + OpenAI to start)
```

## Gate G0 — verify the scaffold

```bash
python -m mia.main --check
```

Boots the app, creates `data/mia.db` with the full schema, logs a **redacted**
config summary (secrets shown only as `set`/`unset`), and exits `0`.

## Develop

```bash
ruff check .     # lint
pytest           # unit tests
```

## Layout (Phase 0)

```
src/mia/
├── main.py            # entrypoint; `--check` runs Gate G0
├── config.py          # typed pydantic-settings config
├── logging_setup.py   # stdout + rotating file log; events_log DB handler
└── memory/
    ├── db.py          # connect / init_db / log_event
    └── schema.sql     # full SQLite schema (idempotent)
```

Later phases add `bot/`, `agent/`, `voice/`, `tools/`, `jobs/`, etc. — only when
that phase is built.
