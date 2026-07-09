"""A short, scripted first-run interview.

Kept deterministic (not LLM-driven) so it reliably completes in a few taps and
seeds clean structured data — the assistant's cold-start cure (plan weakness #6).
State lives in `context.user_data['onboarding']`; answers are persisted to the
DB only at the end.
"""

from __future__ import annotations

import re

from telegram import Update
from telegram.ext import ContextTypes

from mia.memory import db as dbm

# (key, question). Order is the interview flow.
_STEPS: list[tuple[str, str]] = [
    ("name", "First — what should I call you?"),
    ("timezone", "Which city or timezone are you in? (so I get times right)"),
    ("work", "What do you do, and what are you focused on these days?"),
    ("projects", "Name up to 3 active projects (comma-separated), or say “skip”."),
    ("briefing_time", "What time would you like a morning briefing? (e.g. 08:00, or “skip”)"),
    ("quiet", "Any quiet hours I should avoid pinging you? (e.g. 22:00-07:00, or “skip”)"),
]

_SKIP = {"skip", "-", "none", "no", "nope", "пропустити", "omitir"}

# Minimal city → IANA map for the owner's usual locations; refined by /tz (Phase 4).
_CITY_TZ = {
    "madrid": "Europe/Madrid",
    "barcelona": "Europe/Madrid",
    "spain": "Europe/Madrid",
    "kyiv": "Europe/Kyiv",
    "kiev": "Europe/Kyiv",
    "ukraine": "Europe/Kyiv",
    "mexico": "America/Mexico_City",
    "mexico city": "America/Mexico_City",
    "cdmx": "America/Mexico_City",
}


def _is_skip(text: str) -> bool:
    return text.strip().lower() in _SKIP


def _normalize_tz(answer: str, default: str) -> str:
    a = answer.strip()
    if "/" in a and " " not in a:  # already looks like an IANA id
        return a
    return _CITY_TZ.get(a.lower(), default)


def _normalize_time(answer: str) -> str | None:
    m = re.search(r"\b([0-2]?\d):([0-5]\d)\b", answer)
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    if hh > 23:
        return None
    return f"{hh:02d}:{mm:02d}"


def is_active(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return "onboarding" in context.user_data


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["onboarding"] = {"step": 0, "answers": {}}
    await update.message.reply_text(
        "Hi! I'm Mia. Let's do a quick setup so I'm useful from day one — "
        "about a minute. You can say “skip” to any question."
    )
    await update.message.reply_text(_STEPS[0][1])


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data["onboarding"]
    key, _ = _STEPS[state["step"]]
    state["answers"][key] = update.message.text
    state["step"] += 1

    if state["step"] < len(_STEPS):
        await update.message.reply_text(_STEPS[state["step"]][1])
        return

    await _finish(update, context, state["answers"])


async def _finish(
    update: Update, context: ContextTypes.DEFAULT_TYPE, answers: dict[str, str]
) -> None:
    conn = context.bot_data["conn"]
    settings = context.bot_data["settings"]
    recap: list[str] = []

    name = answers.get("name", "").strip()
    if name and not _is_skip(name):
        dbm.set_setting(conn, "owner_name", name)
        dbm.add_fact(conn, f"The owner's name is {name}.", category="profile", source="onboarding")
        recap.append(f"• Name: {name}")

    tz_answer = answers.get("timezone", "").strip()
    if tz_answer and not _is_skip(tz_answer):
        tz = _normalize_tz(tz_answer, settings.default_timezone)
        dbm.set_setting(conn, "timezone", tz)
        dbm.add_fact(
            conn, f"The owner is based in {tz_answer}.",
            category="profile", source="onboarding",
        )
        recap.append(f"• Timezone: {tz}")

    work = answers.get("work", "").strip()
    if work and not _is_skip(work):
        dbm.add_fact(conn, f"Work context: {work}", category="profile", source="onboarding")
        recap.append("• Work context saved")

    projects = answers.get("projects", "").strip()
    if projects and not _is_skip(projects):
        names = [p.strip() for p in projects.split(",") if p.strip()][:3]
        for pname in names:
            dbm.add_project(conn, pname)
        if names:
            recap.append("• Projects: " + ", ".join(names))

    briefing = _normalize_time(answers.get("briefing_time", ""))
    if briefing:
        dbm.set_setting(conn, "briefing_time", briefing)
        recap.append(f"• Morning briefing: {briefing}")

    quiet = answers.get("quiet", "")
    qm = re.findall(r"\b([0-2]?\d:[0-5]\d)\b", quiet)
    if len(qm) >= 2:
        dbm.set_setting(conn, "quiet_start", _normalize_time(qm[0]))
        dbm.set_setting(conn, "quiet_end", _normalize_time(qm[1]))
        recap.append(f"• Quiet hours: {qm[0]}–{qm[1]}")

    dbm.set_setting(conn, "onboarded", "1")
    del context.user_data["onboarding"]

    body = "\n".join(recap) if recap else "• (nothing saved — you skipped it all)"
    await update.message.reply_text(
        "Done — here's what I've got:\n" + body + "\n\n"
        "You can ask me “what do you know about me?” any time, see it with "
        "/memory, or just tell me more and I'll remember. What's on your mind?"
    )
