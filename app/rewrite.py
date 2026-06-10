from copy import deepcopy
from typing import Any


def fix_prefill(body: Any, continue_text: str = "Continue.") -> tuple[Any, bool]:
    """Append a synthetic user turn when a chat request ends with an assistant message.

    Some models (e.g. newer Anthropic models) reject assistant-message prefill and
    require the conversation to end with a user message. This appends a minimal user
    turn while preserving the existing assistant prefill content.

    Returns the (possibly rewritten) body and a flag indicating whether it changed.
    The input body is never mutated. Anything unexpected is a no-op (fail-open).
    """
    if not isinstance(body, dict):
        return body, False

    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return body, False

    last = messages[-1]
    if not isinstance(last, dict) or last.get("role") != "assistant":
        return body, False

    new_body = deepcopy(body)
    new_body["messages"].append({"role": "user", "content": continue_text})
    return new_body, True
