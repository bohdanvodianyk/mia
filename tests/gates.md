# Acceptance Gates — manual scripts per phase

Run each gate in order. Do not start a phase until the previous gate passes.
Check the box in `personal_assistant_dev_plan_v2.md` and commit `phase-N` at each gate.

---

## Gate G0 — Scaffold

```bash
conda activate mia
pip install -e ".[dev]"
ruff check .
pytest
python -m mia.main --check ; echo "exit=$?"
```

**Pass when:**
- `ruff check .` reports no errors.
- `pytest` is green.
- `python -m mia.main --check` boots, creates `data/mia.db`, logs a **redacted**
  config summary (secrets shown only as `set`/`unset`, never their values),
  reports 12 tables, prints `Gate G0 OK`, and exits `0`.

---

## Gate G1 — Telegram ⇄ Claude core (Phase 1)

### Prerequisites (one-time)

- Create a bot with **@BotFather**; put the token in `.env` as `TELEGRAM_BOT_TOKEN`.
- Get your numeric id from **@userinfobot**; set `OWNER_TELEGRAM_ID` in `.env`.
- `ANTHROPIC_API_KEY` set in `.env`.

### Automated pre-checks

```bash
conda activate mia
pip install -e ".[dev]"
ruff check .
pytest
```

Both must be green (offline unit tests: sessions, cost, splitting, prompts).

### Run the bot

```bash
python -m mia.main        # starts long-polling; Ctrl-C to stop
```

### Manual acceptance script (in Telegram)

1. **Feedback speed** — send "Give me three ideas for a weekend project."
   The typing indicator must appear within ~1s; a longer answer may briefly show
   "One moment…" that then becomes the reply. → responsiveness ✅
2. **Language mirroring** — send "¿Qué me recomiendas para dormir mejor?"
   The reply must be in Spanish. Repeat with a Ukrainian message → Ukrainian reply.
3. **Multi-turn** — send "My sister's name is Olena." then "What's her name?"
   in the same session → it answers "Olena" (session history works).
4. **Auto-session** — after >2h of silence a new topic starts a clean session
   (long-term memory is Phase 3; here only the working window resets). `/reset`
   forces a fresh session immediately.
5. **Owner lock** — from a *different* Telegram account, message the bot →
   no reply at all (silently ignored). Check `data/logs/mia.log` shows nothing
   for that user.
6. **Usage** — send `/usage` → month-to-date cost per provider with real,
   non-zero numbers. `/start` and `/help` (6 examples) render.

**Pass when:** every item above behaves as described — visible feedback within
1s always, strangers ignored, Spanish→Spanish, `/usage` shows real costs.

---

## Gate G2 — Voice input (Phase 2)

### Prerequisites

- `OPENAI_API_KEY` set in `.env` (Whisper). The bot now requires it to start.

### Automated pre-checks

```bash
conda activate mia
ruff check .
pytest
```

### Run the bot

```bash
python -m mia.main
```

### Manual acceptance script (in Telegram)

1. **Ukrainian voice note** — record a ~60s voice message about scheduling, e.g.
   "Нагадай, що завтра о третій зустріч з Оленою, і допоможи спланувати ранок."
   → Mia echoes the transcript in *italics* (🎤), then answers in Ukrainian.
2. **Spanish voice note** — record a short note in Spanish → transcript echoed,
   answered in Spanish.
3. **Verification value** — the italic echo should match what you said, so you
   can catch mis-hearings before acting on them.
4. **Unclear audio** — send a silent / noise-only voice note → plain "couldn't
   make out any speech" message, no crash.
5. **Cost** — send `/usage` → an `openai` line now appears alongside `anthropic`,
   with a real (small) transcription cost.

**Pass when:** a 60s Ukrainian scheduling note is transcribed correctly and
answered; a Spanish note likewise; transcription cost is visible in `/usage`.

<!-- Subsequent gates G3–G10 appended as each phase is built. -->
