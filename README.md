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
   Then set `OPENAI_API_KEY` in `.env`.

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

## Notes

- Default model is `gpt-4.1-nano` for faster responses (override with `OPENAI_MODEL` in `.env`).
- The MVP is intentionally stateless (chat history is not persisted).
- Chat responses are streamed token-by-token and rendered with Markdown formatting.
- `Download Plan` opens a preview modal and saves a server-generated PDF summary of the full chat session.
