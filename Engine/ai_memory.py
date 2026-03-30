from __future__ import annotations

import os
from typing import Iterable

from Engine import db

SYSTEM_PROMPT = (
    "You are JARVIS / ASTER, a professional automotive infotainment voice assistant. "
    "Respond concisely, safely, and in a natural spoken tone. Avoid unnecessary verbosity."
)


def _format_history(history: list[tuple[str, str, str]]) -> str:
    lines = []
    for user_input, assistant_reply, source in history:
        lines.append(f"User[{source}]: {user_input}")
        lines.append(f"Assistant: {assistant_reply}")
    return "\n".join(lines)


def _offline_reply(query: str, history: list[tuple[str, str, str]]) -> str:
    lower_query = query.lower()
    if "music" in lower_query:
        return "Opening music controls."
    if "weather" in lower_query:
        return "Weather data is not available offline."
    if "time" in lower_query:
        return "The time is available on the dashboard."
    if history:
        return f"I heard you. {history[-1][1]}"
    return "I am ready."


def generate_response(query: str) -> str:
    query_text = str(query or "").strip()
    if not query_text:
        return ""

    history = db.fetch_recent_conversations(limit=12)
    context = _format_history(history)
    prompt = f"{SYSTEM_PROMPT}\n\nConversation context:\n{context}\n\nUser: {query_text}\nAssistant:"

    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        reply = _offline_reply(query_text, history)
        return reply

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        result = client.responses.create(model=model, input=prompt)
        reply = getattr(result, "output_text", "").strip()
        if reply:
            return reply
    except Exception:
        pass

    try:
        import openai

        openai.api_key = api_key
        response = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{context}\n\nUser: {query_text}"},
            ],
        )
        reply = response["choices"][0]["message"]["content"].strip()
        if reply:
            return reply
    except Exception:
        pass

    reply = _offline_reply(query_text, history)
    return reply
