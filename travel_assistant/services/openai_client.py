import json

from django.conf import settings
from openai import OpenAI

from travel_assistant.constants import PLAN_SUMMARY_SYSTEM_PROMPT, SYSTEM_PROMPT_TEMPLATE


class OpenAIConfigurationError(RuntimeError):
    """Raised when OPENAI_API_KEY is missing."""


def generate_trip_response(city_name: str, country: str, user_prompt: str) -> str:
    if not settings.OPENAI_API_KEY:
        raise OpenAIConfigurationError("OPENAI_API_KEY is not set.")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(city_name=city_name, country=country)
    response = client.responses.create(
        model=settings.OPENAI_MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.output_text.strip()


def stream_trip_response(city_name: str, country: str, user_prompt: str):
    if not settings.OPENAI_API_KEY:
        raise OpenAIConfigurationError("OPENAI_API_KEY is not set.")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(city_name=city_name, country=country)

    with client.responses.stream(
        model=settings.OPENAI_MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
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
