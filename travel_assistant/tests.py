import json
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from travel_assistant.constants import MAX_PROMPT_LENGTH


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
        mocked_summary.return_value = self.summary
        response = self.client.post(
            self.pdf_url,
            data=json.dumps({"city": "venice", "conversationTurns": self.turns}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment;", response["Content-Disposition"])
