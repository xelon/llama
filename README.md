# Llama Inc Travel Assistant (MVP)

Initial Django + SQLite app for planning trips in three launch cities:
- San Francisco (USA)
- Venice (Italy)
- Cork (Ireland)

The home page includes a polished city selector and a chat interface backed by OpenAI.

## Quick start

1. Create virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
2. Add environment variables:
   ```bash
   cp .env.example .env
   ```
   Then set `OPENAI_API_KEY` and Stripe billing keys in `.env`.

3. Run migrations:
   ```bash
   .venv/bin/python manage.py migrate
   ```

4. Start development server:
   ```bash
   .venv/bin/python manage.py runserver
   ```

5. Open [http://127.0.0.1:8000](http://127.0.0.1:8000)

## API

### `POST /api/chat/`

Payload:
```json
{
  "city": "san-francisco",
  "message": "Plan one evening after meetings."
}
```

Supported `city` values:
- `san-francisco`
- `venice`
- `cork`

### `POST /api/billing/create-checkout-session/`

Starts a hosted Stripe Checkout Session for the monthly subscription.

Payload:
```json
{
  "city": "venice",
  "email": "traveler@example.com",
  "conversationTurns": [
    {"role": "user", "content": "Plan one evening in Venice."},
    {"role": "assistant", "content": "Focus on Cannaregio and reserve dinner."}
  ]
}
```

### `POST /api/billing/webhook/`

Stripe webhook endpoint for subscription lifecycle synchronization.

### `POST /api/plan/pdf/`

Requires an active Stripe subscription (email-linked entitlement) before returning a downloadable PDF.

## Notes

- Default model is `gpt-4.1-nano` for faster responses (override with `OPENAI_MODEL` in `.env`).
- The MVP is intentionally stateless (chat history is not persisted).
- Chat responses are streamed token-by-token and rendered with Markdown formatting.
- `Download Plan` is gated by hosted Stripe Checkout in subscription mode and returns PDFs only for active/trialing subscribers.
- Recommended Stripe API version is `2026-01-28.clover` (default in `.env.example`).
- Required billing environment variables:
  - `SITE_URL`
  - `STRIPE_SECRET_KEY`
  - `STRIPE_WEBHOOK_SECRET`
  - `STRIPE_MONTHLY_PRICE_ID`
  - `STRIPE_API_VERSION`
- Database persistence:
  - Set `DATABASE_PATH=/data/db.sqlite3` in production and mount `/data` as persistent volume in Coolify.
  - If unset, local dev defaults to `db.sqlite3` in project root; production defaults to `/data/db.sqlite3`.
- Local webhook forwarding example:
  ```bash
  stripe listen --forward-to http://127.0.0.1:8000/api/billing/webhook/
  ```
