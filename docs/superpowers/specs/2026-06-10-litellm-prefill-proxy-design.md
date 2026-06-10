# litellm-prefill-proxy — Design

## Problem

Cursor talks to a LiteLLM proxy using the OpenAI chat-completions format. Cursor
sometimes ends the `messages` array with a trailing `assistant` message (a
"prefill" used to steer the model's next output). LiteLLM forwards this to
Anthropic, and some newer Anthropic models reject prefill with:

```
This model does not support assistant message prefill.
The conversation must end with a user message.
```

The request then fails (and LiteLLM's configured fallbacks don't help because
they hit the same constraint).

## Goal

A small local HTTP shim that sits between Cursor and LiteLLM:

```
Cursor  ->  litellm-prefill-proxy  ->  LiteLLM  ->  Anthropic
```

It transparently forwards everything to LiteLLM, with one mutation: when a chat
request ends with an `assistant` message, it appends a minimal synthetic `user`
turn so the conversation ends with a user message. The prefill content is
preserved (not dropped).

## Non-Goals

- Not a general request-transformation framework. One narrow fix only.
- Does not modify LiteLLM config or internals (kept fully decoupled).
- Does not log prompt payloads by default (privacy).

## Architecture

A single FastAPI app served by uvicorn. One catch-all route handles every
method and path and acts as a transparent reverse proxy to an upstream LiteLLM
base URL. Exactly one mutation hook runs on `POST /v1/chat/completions` (and the
`/chat/completions` variant).

### Components

- `app/config.py` — env-driven settings:
  - `UPSTREAM_BASE_URL` (default `http://localhost:4000`)
  - `LISTEN_HOST` (default `127.0.0.1`), `LISTEN_PORT` (default `8787`)
  - `CONTINUE_TEXT` (default `"Continue."`)
  - `DEBUG` (default off) — log a single line when a rewrite occurs.
- `app/rewrite.py` — pure function `fix_prefill(body: dict) -> tuple[dict, bool]`:
  if `messages` is a non-empty list and `messages[-1]["role"] == "assistant"`,
  append `{"role": "user", "content": CONTINUE_TEXT}`. Returns the (possibly
  unchanged) body and a `changed` flag. No I/O, fully unit-testable.
- `app/main.py` — FastAPI app, shared `httpx.AsyncClient`, catch-all route.
- `tests/test_rewrite.py` — unit tests for `fix_prefill`.
- `requirements.txt`, `README.md`, `.gitignore`, `run.sh`.

### Data flow

1. Cursor sends an OpenAI-format request to the shim.
2. If method is `POST` and path matches the chat-completions endpoints, read the
   JSON body, run `fix_prefill`, re-serialize. All other paths/methods pass
   through with their body untouched.
3. Forward to `UPSTREAM_BASE_URL` preserving original headers (excluding
   hop-by-hop headers `host` and `content-length`, which httpx recomputes),
   query string, and the (possibly rewritten) body.
4. Relay the upstream response back to Cursor by streaming raw bytes, preserving
   upstream status code and response headers (excluding hop-by-hop). This works
   for both SSE (`stream: true`) and normal JSON responses.

## Error handling

- Body is not valid JSON, or `messages` missing/empty, or last message has no
  `role` → skip rewrite, pass the original bytes through unchanged (fail-open;
  never break a request).
- Upstream connection/timeout error → return HTTP 502 with a small JSON error
  body describing the failure.
- With `DEBUG` on, log one line per rewrite: the request's `model` plus a note
  that a user turn was appended. Never log message contents by default.

## Testing

- Unit (`fix_prefill`):
  - trailing `assistant` → appends one user turn with `CONTINUE_TEXT`.
  - trailing `user` → no-op.
  - empty `messages` / missing `messages` / non-dict body → no-op, no error.
  - assistant prefill content is preserved (not removed).
- Manual smoke: README `curl` example posting a trailing-assistant request to
  the shim and confirming the appended user turn (against real LiteLLM or a
  mock upstream).

## Operational notes

- Run: `UPSTREAM_BASE_URL=http://localhost:4000 ./run.sh` (or uvicorn directly).
- Cursor change: point its OpenAI base URL at `http://127.0.0.1:8787/v1`
  instead of LiteLLM directly. API keys/headers Cursor sends pass through
  unchanged.
