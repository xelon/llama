import json
from unittest.mock import patch

from django.core import signing
from django.test import Client, TestCase
from django.urls import reverse

from travel_assistant.constants import MAX_PROMPT_LENGTH
from travel_assistant.models import SubscriberAccess


class StripeLikeObject:
    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        return self._data[key]


class HomePageTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.home_url = reverse("home")

    def test_home_shows_manage_subscription_when_subscribed(self):
        SubscriberAccess.objects.create(
            email="subscribed@example.com",
            stripe_customer_id="cus_home_1",
            stripe_subscription_id="sub_home_1",
            subscription_status="active",
        )
        token = signing.dumps({"email": "subscribed@example.com"}, salt="llama_subscription_access")
        self.client.cookies["llama_subscription_access"] = token
        response = self.client.get(self.home_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manage subscription")
        self.assertContains(response, reverse("billing_portal_redirect"))

    def test_home_hides_manage_subscription_without_cookie(self):
        SubscriberAccess.objects.create(
            email="subscribed@example.com",
            stripe_customer_id="cus_home_1",
            stripe_subscription_id="sub_home_1",
            subscription_status="active",
        )
        response = self.client.get(self.home_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Manage subscription")


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
        self.restore_request_url = reverse("request_restore_link_api")
        self.webhook_url = reverse("stripe_webhook")
        self.success_url = reverse("checkout_success")
        self.success_page_url = reverse("billing_success_page")
        self.portal_url = reverse("billing_portal_redirect")
        self.restore_url = reverse("billing_restore")
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
        self.assertIn("/billing/success/?state=success", response.url)
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
        self.assertIn("/billing/success/?state=success", response.url)
        access = SubscriberAccess.objects.get(email="time@example.com")
        self.assertIsNotNone(access.current_period_end)

    @patch("travel_assistant.views.settings.STRIPE_SECRET_KEY", "sk_test_123")
    @patch("travel_assistant.views._stripe_client")
    def test_checkout_success_retrieves_subscription_when_session_has_subscription_id(self, mocked_client):
        mocked_client.return_value.checkout.Session.retrieve.return_value = {
            "customer": "cus_125",
            "customer_details": {"email": "expand@example.com"},
            "subscription": "sub_125",
            "metadata": {"email": "expand@example.com"},
        }
        mocked_client.return_value.Subscription.retrieve.return_value = {
            "id": "sub_125",
            "status": "active",
            "current_period_end": 1777000000,
        }
        response = self.client.get(f"{self.success_url}?session_id=cs_test_125")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/billing/success/?state=success", response.url)
        access = SubscriberAccess.objects.get(email="expand@example.com")
        self.assertEqual(access.stripe_subscription_id, "sub_125")

    @patch("travel_assistant.views.settings.STRIPE_SECRET_KEY", "sk_test_123")
    @patch("travel_assistant.views._stripe_client")
    def test_checkout_success_handles_stripe_like_session_object(self, mocked_client):
        mocked_client.return_value.checkout.Session.retrieve.return_value = StripeLikeObject(
            {
                "customer": StripeLikeObject({"id": "cus_126"}),
                "customer_details": StripeLikeObject({"email": "sessionobj@example.com"}),
                "subscription": StripeLikeObject(
                    {
                        "id": "sub_126",
                        "status": "active",
                        "current_period_end": 1777000000,
                    }
                ),
                "metadata": StripeLikeObject({"email": "sessionobj@example.com"}),
            }
        )
        response = self.client.get(f"{self.success_url}?session_id=cs_test_126")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/billing/success/?state=success", response.url)
        access = SubscriberAccess.objects.get(email="sessionobj@example.com")
        self.assertEqual(access.stripe_subscription_id, "sub_126")
        self.assertEqual(access.stripe_customer_id, "cus_126")

    def test_billing_success_page_renders(self):
        response = self.client.get(f"{self.success_page_url}?state=success")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Subscription is active.", response.content.decode("utf-8"))

    @patch("travel_assistant.views.settings.RESEND_API_KEY", "re_test_123")
    @patch("travel_assistant.views.settings.RESEND_FROM_EMAIL", "llama@updates.xelon.it")
    @patch("travel_assistant.views.urlrequest.urlopen")
    def test_restore_request_sends_magic_link_for_active_subscriber(self, mocked_urlopen):
        SubscriberAccess.objects.create(
            email="restore@example.com",
            stripe_customer_id="cus_restore",
            stripe_subscription_id="sub_restore",
            subscription_status="active",
        )
        response = self.client.post(
            self.restore_request_url,
            data=json.dumps({"email": "restore@example.com"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["action"], "restore_sent")
        mocked_urlopen.assert_called_once()

    def test_restore_request_falls_back_to_checkout_for_unknown_email(self):
        response = self.client.post(
            self.restore_request_url,
            data=json.dumps({"email": "unknown@example.com"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["action"], "checkout_required")

    def test_billing_restore_sets_cookie_for_valid_token(self):
        SubscriberAccess.objects.create(
            email="restore-ok@example.com",
            stripe_customer_id="cus_restore_ok",
            stripe_subscription_id="sub_restore_ok",
            subscription_status="active",
        )
        token = signing.dumps(
            {"email": "restore-ok@example.com", "purpose": "restore_access"},
            salt="llama_restore_access",
        )
        response = self.client.get(f"{self.restore_url}?token={token}")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/billing/success/?state=success", response.url)
        self.assertIn("llama_subscription_access", response.cookies)

    def test_billing_restore_rejects_invalid_token(self):
        token = signing.dumps(
            {"email": "restore-fail@example.com", "purpose": "wrong"},
            salt="llama_restore_access",
        )
        response = self.client.get(f"{self.restore_url}?token={token}")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/billing/success/?state=failed", response.url)

    @patch("travel_assistant.views.settings.STRIPE_SECRET_KEY", "sk_test_123")
    @patch("travel_assistant.views._stripe_client")
    def test_billing_portal_redirect_uses_customer_from_cookie(self, mocked_client):
        SubscriberAccess.objects.create(
            email="portal@example.com",
            stripe_customer_id="cus_portal",
            stripe_subscription_id="sub_portal",
            subscription_status="active",
        )
        token = signing.dumps({"email": "portal@example.com"}, salt="llama_subscription_access")
        self.client.cookies["llama_subscription_access"] = token
        mocked_client.return_value.billing_portal.Session.create.return_value = {
            "url": "https://billing.stripe.test/session",
        }
        response = self.client.get(self.portal_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://billing.stripe.test/session")

    @patch("travel_assistant.views.settings.STRIPE_SECRET_KEY", "sk_test_123")
    @patch("travel_assistant.views._stripe_client")
    def test_billing_portal_redirect_normalizes_stringified_customer_payload(self, mocked_client):
        SubscriberAccess.objects.create(
            email="portal-json@example.com",
            stripe_customer_id='{"id":"cus_json_123","object":"customer"}',
            stripe_subscription_id="sub_portal_json",
            subscription_status="active",
        )
        token = signing.dumps({"email": "portal-json@example.com"}, salt="llama_subscription_access")
        self.client.cookies["llama_subscription_access"] = token
        mocked_client.return_value.billing_portal.Session.create.return_value = {
            "url": "https://billing.stripe.test/session-json",
        }
        response = self.client.get(self.portal_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://billing.stripe.test/session-json")
        mocked_client.return_value.billing_portal.Session.create.assert_called_once_with(
            customer="cus_json_123",
            return_url="http://127.0.0.1:8000/billing/success/?state=success",
        )

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

    @patch("travel_assistant.views.settings.STRIPE_SECRET_KEY", "sk_test_123")
    @patch("travel_assistant.views.settings.STRIPE_WEBHOOK_SECRET", "whsec_123")
    @patch("travel_assistant.views._stripe_client")
    def test_webhook_handles_stripe_like_event_objects(self, mocked_client):
        event = StripeLikeObject(
            {
                "type": "customer.subscription.updated",
                "data": StripeLikeObject(
                    {
                        "object": StripeLikeObject(
                            {
                                "id": "sub_200",
                                "customer": "cus_200",
                                "status": "active",
                                "current_period_end": 1777000000,
                                "metadata": StripeLikeObject({"email": "obj@example.com"}),
                            }
                        )
                    }
                ),
            }
        )
        mocked_client.return_value.Webhook.construct_event.return_value = event
        response = self.client.post(
            self.webhook_url,
            data=json.dumps({"id": "evt_200"}),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="sig",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            SubscriberAccess.objects.filter(
                email="obj@example.com",
                stripe_customer_id="cus_200",
                stripe_subscription_id="sub_200",
                subscription_status="active",
            ).exists()
        )
