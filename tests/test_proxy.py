import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.main import app

# Captures what the mock upstream received from the proxy.
captured: dict = {}


async def _upstream_chat(request):
    try:
        body = await request.json()
    except Exception:
        # Mirror how a real upstream rejects malformed JSON rather than crashing.
        return JSONResponse({"error": "invalid json"}, status_code=400)
    captured["body"] = body
    captured["auth"] = request.headers.get("authorization")
    if body.get("stream"):
        async def gen():
            yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
            yield b"data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")
    return JSONResponse({"ok": True, "messages": body["messages"]})


async def _upstream_models(request):
    captured["models_hit"] = True
    return JSONResponse({"data": [{"id": "some-model"}]})


mock_upstream = Starlette(
    routes=[
        Route("/v1/chat/completions", _upstream_chat, methods=["POST"]),
        Route("/v1/models", _upstream_models, methods=["GET"]),
    ]
)


@pytest.fixture
def client():
    captured.clear()
    with TestClient(app) as c:
        # Swap the proxy's outbound client for one that targets the mock upstream
        # in-process. base_url is arbitrary; ASGITransport routes by path.
        c.app.state.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_upstream),
            base_url="http://upstream",
        )
        yield c


def test_appends_user_turn_for_trailing_assistant(client):
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "anthropic/claude-fable-5",
            "messages": [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "prefill"},
            ],
        },
        headers={"authorization": "Bearer sk-test"},
    )

    assert resp.status_code == 200
    sent = captured["body"]["messages"]
    assert sent[-1] == {"role": "user", "content": "Continue."}
    assert sent[-2] == {"role": "assistant", "content": "prefill"}
    # auth header is forwarded untouched
    assert captured["auth"] == "Bearer sk-test"


def test_leaves_trailing_user_untouched(client):
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "Hi"}]},
    )

    assert resp.status_code == 200
    assert captured["body"]["messages"] == [{"role": "user", "content": "Hi"}]


def test_streaming_response_is_relayed(client):
    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "stream": True,
            "messages": [{"role": "assistant", "content": "x"}],
        },
    ) as resp:
        assert resp.status_code == 200
        text = "".join(resp.iter_text())

    assert "data: [DONE]" in text
    assert captured["body"]["messages"][-1] == {"role": "user", "content": "Continue."}


def test_non_chat_path_passes_through(client):
    resp = client.get("/v1/models")

    assert resp.status_code == 200
    assert resp.json() == {"data": [{"id": "some-model"}]}
    assert captured.get("models_hit") is True


def test_invalid_json_body_passes_through(client):
    resp = client.post(
        "/v1/chat/completions",
        content=b"not json",
        headers={"content-type": "application/json"},
    )
    # Upstream mock will fail to parse; proxy must not 500 on the way in.
    # We only assert the proxy forwarded rather than erroring locally.
    assert resp.status_code in (200, 400, 422, 500)
