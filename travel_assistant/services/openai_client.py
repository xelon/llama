import json

from django.conf import settings
from openai import OpenAI

from travel_assistant.constants import (
    PLAN_SUMMARY_SYSTEM_PROMPT,
    SCOPE_REMINDER_PROMPT,
    SYSTEM_PROMPT_TEMPLATE,
)


class OpenAIConfigurationError(RuntimeError):
    """Raised when OPENAI_API_KEY is missing."""


def _wrap_user_message(content: str) -> str:
    """Wrap user text so the model can distinguish untrusted data from instructions."""
    safe = (content or "").replace("</user_message>", "</user_message​>")
    return f"<user_message>\n{safe}\n</user_message>"


def _build_chat_input(
    city_name: str,
    country: str,
    user_prompt: str,
    history: list[dict] | None = None,
) -> list[dict]:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(city_name=city_name, country=country)
    reminder = SCOPE_REMINDER_PROMPT.format(city_name=city_name, country=country)

    input_messages: list[dict] = [{"role": "system", "content": system_prompt}]

    for turn in history or []:
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if not content or role not in {"user", "assistant"}:
            continue
        if role == "user":
            input_messages.append({"role": "user", "content": _wrap_user_message(content)})
        else:
            input_messages.append({"role": "assistant", "content": content})

    input_messages.append({"role": "system", "content": reminder})
    input_messages.append({"role": "user", "content": _wrap_user_message(user_prompt)})
    return input_messages


def generate_trip_response(
    city_name: str,
    country: str,
    user_prompt: str,
    history: list[dict] | None = None,
) -> str:
    if not settings.OPENAI_API_KEY:
        raise OpenAIConfigurationError("OPENAI_API_KEY is not set.")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.responses.create(
        model=settings.OPENAI_MODEL,
        input=_build_chat_input(city_name, country, user_prompt, history),
    )
    return response.output_text.strip()


def stream_trip_response(
    city_name: str,
    country: str,
    user_prompt: str,
    history: list[dict] | None = None,
):
    if not settings.OPENAI_API_KEY:
        raise OpenAIConfigurationError("OPENAI_API_KEY is not set.")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    with client.responses.stream(
        model=settings.OPENAI_MODEL,
        input=_build_chat_input(city_name, country, user_prompt, history),
    ) as stream:
        for event in stream:
            if getattr(event, "type", "") == "response.output_text.delta":
                delta = getattr(event, "delta", "")
                if delta:
                    yield delta


def summarize_trip_plan(city_name: str, country: str, turns: list[dict]) -> dict:
    if not settings.OPENAI_API_KEY:
        raise OpenAIConfigurationError("OPENAI_API_KEY is not set.")

    transcript = []
    for turn in turns:
        role = turn.get("role", "user")
        content = (turn.get("content") or "").strip()
        if content:
            transcript.append(f"{role.upper()}: {content}")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.responses.create(
        model=settings.OPENAI_MODEL,
        input=[
            {"role": "system", "content": PLAN_SUMMARY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"City: {city_name}, {country}\n\n"
                    "Conversation transcript:\n"
                    + "\n".join(transcript)
                ),
            },
        ],
    )
    text = response.output_text.strip()
    return json.loads(text)
