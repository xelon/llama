import json
import logging
from datetime import datetime

from django.conf import settings
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.template.loader import render_to_string
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST
from xhtml2pdf import pisa

from travel_assistant.constants import CITY_OPTIONS, MAX_CONVERSATION_TURNS, MAX_PROMPT_LENGTH
from travel_assistant.services.openai_client import (
    OpenAIConfigurationError,
    summarize_trip_plan,
    stream_trip_response,
)

logger = logging.getLogger(__name__)


@require_GET
def home(request):
    return render(
        request,
        "travel_assistant/home.html",
        {"city_options": CITY_OPTIONS},
    )


@require_POST
def chat_api(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request format."}, status=400)

    city_slug = (payload.get("city") or "").strip()
    user_prompt = (payload.get("message") or "").strip()

    city_data = CITY_OPTIONS.get(city_slug)
    if not city_data:
        return JsonResponse({"error": "Choose San Francisco, Venice, or Cork."}, status=400)

    if not user_prompt:
        return JsonResponse({"error": "Type a trip question first."}, status=400)
    if len(user_prompt) > MAX_PROMPT_LENGTH:
        return JsonResponse(
            {"error": f"Message is too long (max {MAX_PROMPT_LENGTH} characters)."},
            status=400,
        )

    def sse_event(event_name, payload):
        return f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"

    def event_stream():
        try:
            yield sse_event("start", {"city": city_data["label"]})
            for chunk in stream_trip_response(
                city_name=city_data["label"],
                country=city_data["country"],
                user_prompt=user_prompt,
            ):
                yield sse_event("delta", {"chunk": chunk})
            yield sse_event("end", {"ok": True})
        except OpenAIConfigurationError as exc:
            yield sse_event("error", {"error": str(exc)})
        except Exception:
            logger.exception(
                "Chat streaming failed for city=%s model=%s",
                city_slug,
                settings.OPENAI_MODEL,
            )
            yield sse_event(
                "error",
                {"error": "Assistant unavailable right now. Try again."},
            )

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def _validate_turns(payload):
    turns = payload.get("conversationTurns")
    if not isinstance(turns, list) or not turns:
        return None, JsonResponse({"error": "Start a conversation before downloading."}, status=400)
    if len(turns) > MAX_CONVERSATION_TURNS:
        return None, JsonResponse({"error": "Conversation is too long to export."}, status=400)

    cleaned = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        cleaned.append({"role": role, "content": content})

    if not cleaned:
        return None, JsonResponse({"error": "No usable conversation turns found."}, status=400)
    return cleaned, None


def _build_plan_summary(city_data, turns):
    summary = summarize_trip_plan(
        city_name=city_data["label"],
        country=city_data["country"],
        turns=turns,
    )
    # Basic shape normalization for frontend and PDF template.
    return {
        "title": summary.get("title") or f"{city_data['label']} Trip Plan",
        "trip_overview": summary.get("trip_overview") or [],
        "day_plan": summary.get("day_plan") or [],
        "logistics": summary.get("logistics") or [],
        "reservations": summary.get("reservations") or [],
        "alternatives": summary.get("alternatives") or [],
        "notes": summary.get("notes") or [],
    }


@require_POST
def plan_preview_api(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request format."}, status=400)

    city_slug = (payload.get("city") or "").strip()
    city_data = CITY_OPTIONS.get(city_slug)
    if not city_data:
        return JsonResponse({"error": "Choose San Francisco, Venice, or Cork."}, status=400)

    turns, error_response = _validate_turns(payload)
    if error_response:
        return error_response

    try:
        summary = _build_plan_summary(city_data, turns)
    except OpenAIConfigurationError as exc:
        return JsonResponse({"error": str(exc)}, status=500)
    except Exception:
        return JsonResponse({"error": "Could not build a plan preview right now."}, status=502)

    return JsonResponse({"city": city_data["label"], "summary": summary})


@require_POST
def plan_pdf_api(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request format."}, status=400)

    city_slug = (payload.get("city") or "").strip()
    city_data = CITY_OPTIONS.get(city_slug)
    if not city_data:
        return JsonResponse({"error": "Choose San Francisco, Venice, or Cork."}, status=400)

    turns, error_response = _validate_turns(payload)
    if error_response:
        return error_response

    try:
        summary = _build_plan_summary(city_data, turns)
    except OpenAIConfigurationError as exc:
        return JsonResponse({"error": str(exc)}, status=500)
    except Exception:
        return JsonResponse({"error": "Could not build a PDF right now."}, status=502)

    context = {
        "city": city_data["label"],
        "country": city_data["country"],
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "summary": summary,
    }
    html = render_to_string("travel_assistant/plan_pdf.html", context)
    response = HttpResponse(content_type="application/pdf")
    filename = f"llama-plan-{city_slug}-{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    pdf_status = pisa.CreatePDF(html, dest=response)
    if pdf_status.err:
        return JsonResponse({"error": "Could not render PDF."}, status=500)
    return response
