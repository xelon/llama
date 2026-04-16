CITY_OPTIONS = {
    "san-francisco": {
        "label": "San Francisco",
        "country": "USA",
        "prompt_hint": "Try: 36 hours in SF with great coffee and one excellent dinner.",
        "starter_prompts": [
            "Plan 36 hours in San Francisco around two meetings in SoMa.",
            "Give me a one-evening SF plan with a strong dinner and easy transit.",
            "What neighborhood should I stay in for walkability and good coffee?",
        ],
    },
    "venice": {
        "label": "Venice",
        "country": "Italy",
        "prompt_hint": "Try: 3 calm days in Venice with fewer crowds and better meals.",
        "starter_prompts": [
            "Plan 3 calm days in Venice with low-crowd mornings and great dinners.",
            "I have one full day in Venice. Build a tight, high-quality route.",
            "Where should I stay in Venice for quiet nights and easy movement?",
        ],
    },
    "cork": {
        "label": "Cork",
        "country": "Ireland",
        "prompt_hint": "Try: one night in Cork with meetings, pubs, and no wasted time.",
        "starter_prompts": [
            "I have one night in Cork. Fit in dinner, a pub, and an early departure.",
            "Build a Cork plan around two work blocks and one memorable meal.",
            "Where should I stay in Cork for a short, efficient visit?",
        ],
    },
}

MAX_PROMPT_LENGTH = 1800
MAX_CONVERSATION_TURNS = 24

SYSTEM_PROMPT_TEMPLATE = """
You are Llama Inc's travel assistant for {city_name}, {country}.

Users are business + bleisure travelers. Write with crisp, analytical clarity.

Rules:
- Ask one short clarifying question only if needed.
- Give practical suggestions with specific neighborhoods.
- Include key logistics (timing, transit, reservations).
- Say when you're unsure; do not invent details.
- Use short sections and bullet points.
- Prefer insight over fluff; each line should add decision value.
""".strip()

PLAN_SUMMARY_SYSTEM_PROMPT = """
You generate concise, practical trip plans from a chat transcript.

Return strict JSON only with this shape:
{
  "title": "string",
  "trip_overview": ["string"],
  "day_plan": [{"day": "string", "items": ["string"]}],
  "logistics": ["string"],
  "reservations": ["string"],
  "alternatives": ["string"],
  "notes": ["string"]
}

Rules:
- Synthesize the conversation, do not copy-paste transcript lines.
- Be specific and decision-oriented.
- Keep each bullet short and useful.
- If information is missing, infer cautiously and note assumptions in notes.
""".strip()
