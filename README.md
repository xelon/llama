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

## Subscriber data (admin CRUD)

Subscription rows live in **`SubscriberAccess`** (SQLite by default). Use Django admin for a full list/add/change/delete UI (staff accounts only):

1. Create a superuser (once per environment):
   ```bash
   .venv/bin/python manage.py createsuperuser
   ```
2. Open [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/) and sign in.
3. Under **Travel assistant → Subscriber accesses**, inspect emails, Stripe IDs, and status after deploys or webhooks.

If rows disappear after each deploy, the database file is not on persistent storage: confirm Coolify mounts `/data` (or your `DATABASE_PATH` directory) and run:

```bash
.venv/bin/python manage.py print_database_path
```

The printed path should point inside that mounted volume in production.

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

### `POST /api/billing/request-restore-link/`

Requests a magic-link email to restore subscription access on a new browser for existing active subscribers. If the email is unknown/inactive, frontend should continue checkout flow.

### `GET /billing/restore/?token=...`

Consumes a signed restore token, restores subscription cookie for the browser, and redirects to the planner with `?subscription=success` (toast on the home page).

### `GET /billing/success/?state=...`

Legacy URL kept for bookmarks and external links; responds with **302** to `/?subscription=...` (same query states as checkout completion).

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
  - `RESEND_API_KEY`
  - `RESEND_FROM_EMAIL`
  - `MAGIC_LINK_EXPIRY_SECONDS` (defaults to `3600`)
- Database persistence:
  - Set `DATABASE_PATH=/data/db.sqlite3` in production and mount `/data` as persistent volume in Coolify.
  - If unset, local dev defaults to `db.sqlite3` in project root; production defaults to `/data/db.sqlite3`.
- Local webhook forwarding example:
  ```bash
  stripe listen --forward-to http://127.0.0.1:8000/api/billing/webhook/
  ```
