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

_To be filled when Phase 1 is built._ Multi-turn conversation feels responsive
(visible feedback within 1s always); stranger messages ignored; ask in Spanish →
Spanish answer; `/usage` shows real costs.

<!-- Subsequent gates G2–G10 appended as each phase is built. -->
