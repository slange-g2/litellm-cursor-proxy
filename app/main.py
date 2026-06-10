import json
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from app.config import settings
from app.rewrite import fix_prefill

logger = logging.getLogger("litellm-prefill-proxy")

CHAT_PATHS = {"/v1/chat/completions", "/chat/completions"}

# Headers that must not be copied verbatim between client/upstream/response.
HOP_BY_HOP = {
    "host",
    "content-length",
    "connection",
    "keep-alive",
    "transfer-encoding",
    "te",
    "trailer",
    "upgrade",
    "proxy-authorization",
    "proxy-authenticate",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(base_url=settings.upstream_base_url, timeout=None)
    try:
        yield
    finally:
        await app.state.client.aclose()


app = FastAPI(lifespan=lifespan, title="litellm-prefill-proxy")


def _maybe_rewrite_body(method: str, path: str, body: bytes) -> bytes:
    """Apply the prefill fix to chat-completions request bodies; fail open otherwise."""
    if method != "POST" or path not in CHAT_PATHS:
        return body
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return body
    new_data, changed = fix_prefill(data, settings.continue_text)
    if not changed:
        return body
    if settings.debug:
        logger.info("appended user turn (model=%s)", data.get("model"))
    return json.dumps(new_data).encode("utf-8")


@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy(request: Request, full_path: str):
    client: httpx.AsyncClient = request.app.state.client
    path = request.url.path

    body = await request.body()
    body = _maybe_rewrite_body(request.method, path, body)

    headers = [
        (k, v) for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP
    ]

    upstream_req = client.build_request(
        request.method,
        path,
        params=request.query_params,
        headers=headers,
        content=body,
    )

    try:
        upstream_resp = await client.send(upstream_req, stream=True)
    except httpx.RequestError as exc:
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "message": f"litellm-prefill-proxy: upstream request failed: {exc}",
                    "type": "upstream_error",
                }
            },
        )

    resp_headers = {
        k: v for k, v in upstream_resp.headers.items() if k.lower() not in HOP_BY_HOP
    }

    return StreamingResponse(
        upstream_resp.aiter_raw(),
        status_code=upstream_resp.status_code,
        headers=resp_headers,
        background=BackgroundTask(upstream_resp.aclose),
    )
