# Cost & Guardrails — Separate Plan (parked)

**Status:** Not started. Parked deliberately — current spend is trivial
(~$0.005 per chat exchange), so this only pays off once usage or the memory
context grows. Revisit when `/usage` month-to-date starts mattering.
**Created:** 2026-07-08 (from a discussion about subscription vs API billing)
**Relates to:** `personal_assistant_dev_plan_v2.md` §2 cost guardrail (< $20/mo)

---

## 0. Settled question: subscription vs API (no action)

Powering the bot with a Claude Pro/Max **subscription** instead of an API key is
**not supported**. The Claude Agent SDK docs state Anthropic does not allow
third-party developers to use claude.ai login for products/agents built on it,
and Claude Code's scripting mode (`--bare`) deliberately skips OAuth/keychain
auth and requires `ANTHROPIC_API_KEY`.

**Conclusion:** subscription = interactive use; API key = programmatic use. Mia's
current setup (Messages API + `ANTHROPIC_API_KEY`) is correct. Nothing to change.
Do not pursue workarounds.

---

## 1. Prompt caching (biggest lever — but not yet)

**Idea:** cache the stable prefix (tools + system prompt) so repeat messages pay
~0.1x on that span instead of full input price.

**Why it's parked — the blocker is size, not effort:**
- Caching is a **prefix match**, and the minimum cacheable prefix on
  Sonnet 4.6 is **2048 tokens** (Haiku 4.5: 4096). Shorter prefixes silently
  don't cache — no error, just `cache_creation_input_tokens: 0`.
- Our current tools + system prompt is well under that, so a breakpoint today
  would do nothing.

**Design note for when we do it** (render order is `tools` → `system` → `messages`):
- Stable prefix must come first: tool schemas + the frozen system template +
  tool guidance. These already are stable — good.
- **The trap:** `memory/context.py` appends facts/projects/summary to the system
  prompt, and that block changes whenever a fact is added. It sits *after* the
  stable text, so a `cache_control` breakpoint placed on the stable part is
  safe — but the cached span would then be only the template (too small today).
- Also volatile: `system_prompt()` interpolates **today's date**. Any date change
  invalidates. Fine at 1/day granularity, but be aware.
- Options when memory grows: (a) breakpoint after the stable template once
  tools+template exceed the minimum, or (b) move the memory block out of
  `system` into a leading `messages` entry so system stays frozen.
- **Verify with `usage.cache_read_input_tokens`** — if it's 0 across repeats, a
  silent invalidator is at work.

**Trigger to revisit:** when the injected memory context routinely exceeds
~1–2k tokens (i.e. lots of stored facts + a long rolling summary).

---

## 2. Daily budget hard-stop (already scheduled — could pull forward)

Already on the roadmap as a **Phase 10** item (`/health`, watchdog, budget). The
`DAILY_BUDGET_USD` setting and the `token_usage` table already exist; nothing
reads the budget yet.

**Minimal version if pulled forward:**
- Before each turn, sum `cost_usd` from `token_usage` for the current UTC day.
- If over `DAILY_BUDGET_USD`, reply plainly ("I've hit today's budget — resuming
  tomorrow, or raise `DAILY_BUDGET_USD`") and skip the model call.
- Notify the owner once per day when it trips, not on every message.

**Pull forward if:** web search usage grows, or a runaway loop is a worry.

---

## 3. Web search cost control (partly done)

Web search is the single most expensive operation today:
- Sonnet 4.6 dynamic variant (`web_search_20260209`) runs code execution under
  the hood → **~$0.10 per search-y query** (measured live).
- Haiku 4.5 basic variant (`web_search_20250305`) → **~$0.03** (measured live).
- Surcharge itself is only $0.01/search; the **result tokens dominate**.

**Done:** `max_uses=5` cap per turn; system prompt tells it to search only for
current/live info; router biases current-info queries to Sonnet.

**Ideas if cost bites:**
- Drop `max_uses` to 2–3.
- Prefer the basic variant even on Sonnet (cheaper, no code-execution overhead)
  — trade some result quality for ~3x cost cut.
- Route search-y queries to Haiku instead of Sonnet.

---

## 4. Other levers (unranked)

- **Trim history window** — `_COMPLEX_HISTORY = 20` turns; could shrink.
- **Rolling summary instead of raw turns** — the nightly job already produces
  one; could rely on it more and send fewer raw turns.
- **Skip the router call** for very short messages (a regex/length heuristic
  could bypass the Haiku classification, saving ~$0.0001 + latency per message).
