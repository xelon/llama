import json
import logging
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.core import signing
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
import stripe
from xhtml2pdf import pisa

from travel_assistant.constants import CITY_OPTIONS, MAX_CONVERSATION_TURNS, MAX_PROMPT_LENGTH
from travel_assistant.models import SubscriberAccess
from travel_assistant.services.openai_client import (
    OpenAIConfigurationError,
    summarize_trip_plan,
    stream_trip_response,
)

logger = logging.getLogger(__name__)
SUBSCRIPTION_COOKIE_NAME = "llama_subscription_access"
SUBSCRIPTION_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30
ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}


def _normalized_email(raw_email):
    return (raw_email or "").strip().lower()


def _safe_get(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    try:
        return obj[key]
    except Exception:
        return default


def _stripe_client():
    stripe.api_key = settings.STRIPE_SECRET_KEY
    stripe.api_version = settings.STRIPE_API_VERSION
    return stripe


def _is_active_subscription_status(subscription_status):
    return subscription_status in ACTIVE_SUBSCRIPTION_STATUSES


def _period_end_from_unix(unix_timestamp):
    if not unix_timestamp:
        return None
    return timezone.datetime.fromtimestamp(unix_timestamp, tz=dt_timezone.utc)


def _upsert_subscriber_access(email, customer_id, subscription_id, subscription_status, current_period_end):
    if not email:
        return None
    defaults = {
        "stripe_customer_id": customer_id or "",
        "stripe_subscription_id": subscription_id or "",
        "subscription_status": subscription_status or "",
        "current_period_end": current_period_end,
    }
    access, _ = SubscriberAccess.objects.update_or_create(email=email, defaults=defaults)
    return access


def _set_subscription_cookie(response, email):
    token = signing.dumps({"email": email}, salt=SUBSCRIPTION_COOKIE_NAME)
    response.set_cookie(
        SUBSCRIPTION_COOKIE_NAME,
        token,
        max_age=SUBSCRIPTION_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Lax",
    )


def _read_subscription_email_from_cookie(request):
    signed_token = request.COOKIES.get(SUBSCRIPTION_COOKIE_NAME)
    if not signed_token:
        return ""
    try:
        payload = signing.loads(
            signed_token,
            max_age=SUBSCRIPTION_COOKIE_MAX_AGE_SECONDS,
            salt=SUBSCRIPTION_COOKIE_NAME,
        )
    except signing.BadSignature:
        return ""
    return _normalized_email(payload.get("email"))


def _has_download_access(request, payload):
    email = _read_subscription_email_from_cookie(request)
    if not email:
        email = _normalized_email(payload.get("subscriberEmail"))
    if not email:
        return False
    access = SubscriberAccess.objects.filter(email=email).first()
    if not access:
        return False
    return _is_active_subscription_status(access.subscription_status)


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

    if not _has_download_access(request, payload):
        return JsonResponse(
            {"error": "Active subscription required to download plans."},
            status=403,
        )

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


@require_POST
def create_checkout_session_api(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request format."}, status=400)

    email = _normalized_email(payload.get("email"))
    if not email:
        return JsonResponse({"error": "Email is required."}, status=400)
    if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_MONTHLY_PRICE_ID:
        return JsonResponse({"error": "Stripe checkout is not configured."}, status=500)

    city_slug = (payload.get("city") or "").strip()
    city_data = CITY_OPTIONS.get(city_slug)
    if not city_data:
        return JsonResponse({"error": "Choose San Francisco, Venice, or Cork."}, status=400)
    _, error_response = _validate_turns(payload)
    if error_response:
        return error_response

    stripe_client = _stripe_client()
    success_url = f"{settings.SITE_URL}/api/billing/checkout/success/?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{settings.SITE_URL}/?checkout=cancelled"
    try:
        checkout_session = stripe_client.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": settings.STRIPE_MONTHLY_PRICE_ID, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=email,
            metadata={"email": email, "city": city_slug},
            allow_promotion_codes=True,
        )
    except Exception:
        logger.exception("Failed creating checkout session for %s", email)
        return JsonResponse({"error": "Could not start checkout right now."}, status=502)

    return JsonResponse({"checkoutUrl": checkout_session.url})


@require_GET
def checkout_success(request):
    session_id = (request.GET.get("session_id") or "").strip()
    if not session_id:
        return redirect("/?checkout=failed")
    if not settings.STRIPE_SECRET_KEY:
        return redirect("/?checkout=failed")

    stripe_client = _stripe_client()
    try:
        session = stripe_client.checkout.Session.retrieve(
            session_id,
            expand=["subscription", "customer"],
        )
    except Exception:
        logger.exception("Failed retrieving checkout session %s", session_id)
        return redirect("/?checkout=failed")

    customer_details = _safe_get(session, "customer_details", {})
    customer_email = _normalized_email(_safe_get(customer_details, "email", ""))
    if not customer_email:
        metadata = _safe_get(session, "metadata", {})
        customer_email = _normalized_email(_safe_get(metadata, "email", ""))
    raw_subscription = _safe_get(session, "subscription")
    subscription = raw_subscription if raw_subscription and not isinstance(raw_subscription, str) else {}
    if not subscription and isinstance(raw_subscription, str):
        try:
            subscription = stripe_client.Subscription.retrieve(raw_subscription)
        except Exception:
            logger.exception(
                "Failed retrieving expanded subscription for session_id=%s subscription_id=%s",
                session_id,
                raw_subscription,
            )
            return redirect("/?checkout=failed")

    subscription_status = _safe_get(subscription, "status", "")
    if not _is_active_subscription_status(subscription_status):
        return redirect("/?checkout=processing")

    try:
        _upsert_subscriber_access(
            email=customer_email,
            customer_id=_safe_get(session, "customer"),
            subscription_id=_safe_get(subscription, "id"),
            subscription_status=subscription_status,
            current_period_end=_period_end_from_unix(_safe_get(subscription, "current_period_end")),
        )
    except Exception:
        logger.exception(
            "Failed persisting subscriber access for session_id=%s email=%s",
            session_id,
            customer_email,
        )
        return redirect("/?checkout=failed")
    response = redirect("/?checkout=success")
    _set_subscription_cookie(response, customer_email)
    return response


@csrf_exempt
@require_POST
def stripe_webhook(request):
    if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_WEBHOOK_SECRET:
        return JsonResponse({"error": "Stripe webhook is not configured."}, status=500)

    stripe_client = _stripe_client()
    signature = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    payload = request.body
    try:
        event = stripe_client.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except Exception:
        return JsonResponse({"error": "Invalid webhook signature."}, status=400)

    event_type = _safe_get(event, "type", "")
    data = _safe_get(event, "data", {})
    data_object = _safe_get(data, "object", {})

    if event_type == "checkout.session.completed":
        customer_details = _safe_get(data_object, "customer_details", {})
        email = _normalized_email(_safe_get(customer_details, "email", ""))
        if not email:
            metadata = _safe_get(data_object, "metadata", {})
            email = _normalized_email(_safe_get(metadata, "email", ""))
        subscription_id = _safe_get(data_object, "subscription")
        customer_id = _safe_get(data_object, "customer")
        subscription_status = ""
        period_end = None
        if subscription_id:
            try:
                subscription = stripe_client.Subscription.retrieve(subscription_id)
                subscription_status = _safe_get(subscription, "status", "")
                period_end = _period_end_from_unix(_safe_get(subscription, "current_period_end"))
            except Exception:
                logger.exception("Failed retrieving subscription %s from checkout event", subscription_id)
        _upsert_subscriber_access(email, customer_id, subscription_id, subscription_status, period_end)

    if event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
        metadata = _safe_get(data_object, "metadata", {})
        email = _normalized_email(_safe_get(metadata, "email", ""))
        customer_id = _safe_get(data_object, "customer", "")
        if not email and customer_id:
            access = SubscriberAccess.objects.filter(stripe_customer_id=customer_id).first()
            if access:
                email = access.email
        _upsert_subscriber_access(
            email=email,
            customer_id=customer_id,
            subscription_id=_safe_get(data_object, "id", ""),
            subscription_status=_safe_get(data_object, "status", ""),
            current_period_end=_period_end_from_unix(_safe_get(data_object, "current_period_end")),
        )

    return JsonResponse({"received": True})
