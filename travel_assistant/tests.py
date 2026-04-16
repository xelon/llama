import json
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from travel_assistant.constants import MAX_PROMPT_LENGTH
from travel_assistant.models import SubscriberAccess


class ChatApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse("chat_api")

    @patch("travel_assistant.views.stream_trip_response", return_value=iter(["Try ", "Sunset first."]))
    def test_chat_api_success(self, mocked_generate):
        response = self.client.post(
            self.url,
            data=json.dumps({"city": "san-francisco", "message": "Plan my evening."}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        stream_text = b"".join(response.streaming_content).decode("utf-8")
        self.assertIn("event: start", stream_text)
        self.assertIn("event: delta", stream_text)
        self.assertIn('"chunk": "Try "', stream_text)
        self.assertIn('"chunk": "Sunset first."', stream_text)
        self.assertIn("event: end", stream_text)
        mocked_generate.assert_called_once()

    def test_chat_api_rejects_unknown_city(self):
        response = self.client.post(
            self.url,
            data=json.dumps({"city": "paris", "message": "Hi"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Choose San Francisco, Venice, or Cork", response.json()["error"])

    def test_chat_api_rejects_empty_prompt(self):
        response = self.client.post(
            self.url,
            data=json.dumps({"city": "venice", "message": "   "}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Type a trip question first", response.json()["error"])

    def test_chat_api_rejects_oversized_prompt(self):
        response = self.client.post(
            self.url,
            data=json.dumps({"city": "cork", "message": "x" * (MAX_PROMPT_LENGTH + 1)}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("too long", response.json()["error"])


class PlanExportApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.preview_url = reverse("plan_preview_api")
        self.pdf_url = reverse("plan_pdf_api")
        self.turns = [
            {"role": "user", "content": "Plan one evening in Venice."},
            {"role": "assistant", "content": "Focus on Cannaregio and reserve dinner."},
        ]
        self.summary = {
            "title": "Venice Evening Plan",
            "trip_overview": ["Compact one-evening route."],
            "day_plan": [{"day": "Evening", "items": ["Walk, aperitivo, dinner."]}],
            "logistics": ["Use vaporetto line 1."],
            "reservations": ["Book dinner by 17:00."],
            "alternatives": ["Swap dinner neighborhood if crowded."],
            "notes": ["Check acqua alta forecast."],
        }

    @patch("travel_assistant.views._build_plan_summary")
    def test_plan_preview_success(self, mocked_summary):
        mocked_summary.return_value = self.summary
        response = self.client.post(
            self.preview_url,
            data=json.dumps({"city": "venice", "conversationTurns": self.turns}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["city"], "Venice")
        self.assertEqual(body["summary"]["title"], "Venice Evening Plan")

    def test_plan_preview_rejects_empty_turns(self):
        response = self.client.post(
            self.preview_url,
            data=json.dumps({"city": "venice", "conversationTurns": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Start a conversation", response.json()["error"])

    @patch("travel_assistant.views._build_plan_summary")
    def test_plan_pdf_success(self, mocked_summary):
        SubscriberAccess.objects.create(
            email="subscriber@example.com",
            subscription_status="active",
            stripe_customer_id="cus_123",
            stripe_subscription_id="sub_123",
        )
        mocked_summary.return_value = self.summary
        response = self.client.post(
            self.pdf_url,
            data=json.dumps(
                {
                    "city": "venice",
                    "conversationTurns": self.turns,
                    "subscriberEmail": "subscriber@example.com",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment;", response["Content-Disposition"])

    def test_plan_pdf_rejects_without_subscription(self):
        response = self.client.post(
            self.pdf_url,
            data=json.dumps({"city": "venice", "conversationTurns": self.turns}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Active subscription required", response.json()["error"])


class BillingApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.checkout_url = reverse("create_checkout_session_api")
        self.webhook_url = reverse("stripe_webhook")
        self.success_url = reverse("checkout_success")
        self.turns = [
            {"role": "user", "content": "Plan one evening in Venice."},
            {"role": "assistant", "content": "Focus on Cannaregio and reserve dinner."},
        ]

    @patch("travel_assistant.views.settings.STRIPE_MONTHLY_PRICE_ID", "price_123")
    @patch("travel_assistant.views.settings.STRIPE_SECRET_KEY", "sk_test_123")
    @patch("travel_assistant.views._stripe_client")
    def test_create_checkout_session_success(self, mocked_client):
        mocked_client.return_value.checkout.Session.create.return_value.url = "https://checkout.stripe.test/session"
        response = self.client.post(
            self.checkout_url,
            data=json.dumps(
                {
                    "city": "venice",
                    "conversationTurns": self.turns,
                    "email": "person@example.com",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checkoutUrl"], "https://checkout.stripe.test/session")

    @patch("travel_assistant.views.settings.STRIPE_MONTHLY_PRICE_ID", "")
    @patch("travel_assistant.views.settings.STRIPE_SECRET_KEY", "")
    def test_create_checkout_session_requires_config(self):
        response = self.client.post(
            self.checkout_url,
            data=json.dumps(
                {
                    "city": "venice",
                    "conversationTurns": self.turns,
                    "email": "person@example.com",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 500)
        self.assertIn("not configured", response.json()["error"])

    @patch("travel_assistant.views.settings.STRIPE_SECRET_KEY", "sk_test_123")
    @patch("travel_assistant.views._stripe_client")
    def test_checkout_success_sets_cookie_and_persists_access(self, mocked_client):
        mocked_client.return_value.checkout.Session.retrieve.return_value = {
            "customer": "cus_123",
            "customer_details": {"email": "paid@example.com"},
            "subscription": {
                "id": "sub_123",
                "status": "active",
                "current_period_end": None,
            },
            "metadata": {"email": "paid@example.com"},
        }
        response = self.client.get(f"{self.success_url}?session_id=cs_test_123")
        self.assertEqual(response.status_code, 302)
        self.assertIn("?checkout=success", response.url)
        self.assertIn("llama_subscription_access", response.cookies)
        self.assertTrue(
            SubscriberAccess.objects.filter(email="paid@example.com", subscription_status="active").exists()
        )

    @patch("travel_assistant.views.settings.STRIPE_SECRET_KEY", "sk_test_123")
    @patch("travel_assistant.views._stripe_client")
    def test_checkout_success_handles_subscription_period_end_timestamp(self, mocked_client):
        mocked_client.return_value.checkout.Session.retrieve.return_value = {
            "customer": "cus_124",
            "customer_details": {"email": "time@example.com"},
            "subscription": {
                "id": "sub_124",
                "status": "active",
                "current_period_end": 1777000000,
            },
            "metadata": {"email": "time@example.com"},
        }
        response = self.client.get(f"{self.success_url}?session_id=cs_test_124")
        self.assertEqual(response.status_code, 302)
        self.assertIn("?checkout=success", response.url)
        access = SubscriberAccess.objects.get(email="time@example.com")
        self.assertIsNotNone(access.current_period_end)

    @patch("travel_assistant.views.settings.STRIPE_SECRET_KEY", "sk_test_123")
    @patch("travel_assistant.views.settings.STRIPE_WEBHOOK_SECRET", "whsec_123")
    @patch("travel_assistant.views._stripe_client")
    def test_webhook_updates_subscription(self, mocked_client):
        mocked_client.return_value.Webhook.construct_event.return_value = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_123",
                    "customer": "cus_123",
                    "status": "active",
                    "current_period_end": None,
                    "metadata": {"email": "paid@example.com"},
                }
            },
        }
        response = self.client.post(
            self.webhook_url,
            data=json.dumps({"id": "evt_123"}),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="sig",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            SubscriberAccess.objects.filter(
                email="paid@example.com",
                stripe_customer_id="cus_123",
                stripe_subscription_id="sub_123",
                subscription_status="active",
            ).exists()
        )
