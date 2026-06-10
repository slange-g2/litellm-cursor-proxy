# litellm-prefill-proxy

A tiny local HTTP shim that sits between Cursor (or any OpenAI-compatible client)
and a LiteLLM proxy, and fixes the "assistant message prefill" error from newer
Anthropic models:

```
litellm.BadRequestError: AnthropicException - This model does not support
assistant message prefill. The conversation must end with a user message.
```

## What it does

```
Cursor  ->  litellm-prefill-proxy  ->  LiteLLM  ->  Anthropic
```

It transparently reverse-proxies every request to your LiteLLM upstream. The only
change it makes: when a `POST /v1/chat/completions` request ends with an
`assistant` message (a "prefill"), it appends a minimal `user` turn so the
conversation ends with a user message. The assistant prefill content is
preserved, not dropped.

Everything else — headers (including the API key Cursor sends), query strings,
other endpoints like `/v1/models`, and streaming (SSE) responses — passes through
untouched. If a body isn't valid JSON or has no trailing assistant message, the
request is forwarded unchanged (fail-open).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
# Point it at your LiteLLM proxy (default: http://localhost:4000)
UPSTREAM_BASE_URL=http://localhost:4000 ./run.sh
```

By default it listens on `127.0.0.1:8787`.

### Configuration (env vars)

| Variable            | Default                  | Description                                   |
| ------------------- | ------------------------ | --------------------------------------------- |
| `UPSTREAM_BASE_URL` | `http://localhost:4000`  | Your LiteLLM proxy base URL.                  |
| `LISTEN_HOST`       | `127.0.0.1`              | Host to bind.                                 |
| `LISTEN_PORT`       | `8787`                   | Port to bind.                                 |
| `CONTINUE_TEXT`     | `Continue.`              | Text of the appended synthetic user turn.     |
| `DEBUG`             | _(off)_                  | If set, logs one line whenever a rewrite happens (no payload contents). |

## Run with Docker

Build the image:

```bash
docker build -t litellm-prefill-proxy .
```

Run it (maps the proxy to `127.0.0.1:8787` on your machine). The image defaults
`UPSTREAM_BASE_URL` to `http://host.docker.internal:4000`, which reaches a
LiteLLM proxy running on your Docker host:

```bash
docker run --rm -p 127.0.0.1:8787:8787 \
  --add-host host.docker.internal:host-gateway \
  litellm-prefill-proxy
```

`--add-host host.docker.internal:host-gateway` is needed on Linux; on Docker
Desktop (macOS/Windows) `host.docker.internal` already resolves, but adding the
flag is harmless. Override the upstream or port via env if needed:

```bash
docker run --rm -p 127.0.0.1:9000:9000 \
  -e LISTEN_PORT=9000 \
  -e UPSTREAM_BASE_URL=http://host.docker.internal:4000 \
  --add-host host.docker.internal:host-gateway \
  litellm-prefill-proxy
```

## Point Cursor at it

In Cursor's model settings, set the OpenAI base URL to:

```
http://127.0.0.1:8787/v1
```

instead of your LiteLLM URL. Keep using the same API key — it's forwarded as-is.

## Verify manually

With the proxy running and pointed at a LiteLLM upstream:

```bash
curl -sS http://127.0.0.1:8787/v1/chat/completions \
  -H "content-type: application/json" \
  -H "authorization: Bearer $YOUR_KEY" \
  -d '{
    "model": "anthropic/claude-fable-5",
    "messages": [
      {"role": "user", "content": "Say hi"},
      {"role": "assistant", "content": "Sure,"}
    ]
  }'
```

Without the proxy this returns the prefill error; through the proxy it succeeds
because a `user` turn is appended after the assistant prefill.

## Tests

```bash
source .venv/bin/activate
python -m pytest -q
```

- `tests/test_rewrite.py` — unit tests for the pure rewrite function.
- `tests/test_proxy.py` — integration tests that run the proxy against an
  in-process mock upstream and verify body rewriting, header forwarding,
  streaming relay, and pass-through behavior.
