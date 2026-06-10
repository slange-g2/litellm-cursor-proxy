from app.rewrite import fix_prefill


def test_appends_user_turn_when_last_message_is_assistant():
    body = {
        "model": "anthropic/claude-fable-5",
        "messages": [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "partial prefill"},
        ],
    }

    new_body, changed = fix_prefill(body, continue_text="Continue.")

    assert changed is True
    assert new_body["messages"][-1] == {"role": "user", "content": "Continue."}
    # prefill content is preserved, not dropped
    assert new_body["messages"][-2] == {"role": "assistant", "content": "partial prefill"}


def test_noop_when_last_message_is_user():
    body = {"messages": [{"role": "user", "content": "Hi"}]}

    new_body, changed = fix_prefill(body, continue_text="Continue.")

    assert changed is False
    assert new_body["messages"] == [{"role": "user", "content": "Hi"}]


def test_noop_when_messages_empty():
    body = {"messages": []}

    new_body, changed = fix_prefill(body, continue_text="Continue.")

    assert changed is False
    assert new_body == {"messages": []}


def test_noop_when_messages_missing():
    body = {"model": "x"}

    new_body, changed = fix_prefill(body, continue_text="Continue.")

    assert changed is False
    assert new_body == {"model": "x"}


def test_noop_when_body_not_a_dict():
    new_body, changed = fix_prefill(["not", "a", "dict"], continue_text="Continue.")

    assert changed is False
    assert new_body == ["not", "a", "dict"]


def test_noop_when_last_message_has_no_role():
    body = {"messages": [{"content": "no role here"}]}

    new_body, changed = fix_prefill(body, continue_text="Continue.")

    assert changed is False


def test_uses_custom_continue_text():
    body = {"messages": [{"role": "assistant", "content": "x"}]}

    new_body, changed = fix_prefill(body, continue_text="Please continue.")

    assert changed is True
    assert new_body["messages"][-1] == {"role": "user", "content": "Please continue."}


def test_does_not_mutate_input_body():
    body = {"messages": [{"role": "assistant", "content": "x"}]}

    fix_prefill(body, continue_text="Continue.")

    assert body["messages"] == [{"role": "assistant", "content": "x"}]
