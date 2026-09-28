"""A scriptable `CompletionFn` for the gateway's tests (M2-FR-15; D-M2-6).

A test double, not production code: it lives under `tests/`, not `bullpit/`.
"""

from __future__ import annotations

from bullpit.llm.gateway import CompletionReply, CompletionRequest


class FakeProvider:
    """Replies (or raises) in the order it's given, and records every
    request it receives so a test can assert the model, `max_tokens` and
    messages sent.
    """

    def __init__(self, replies: list[CompletionReply | Exception]) -> None:
        self._replies = list(replies)
        self.requests: list[CompletionRequest] = []

    def __call__(self, request: CompletionRequest) -> CompletionReply:
        self.requests.append(request)
        if not self._replies:
            raise AssertionError(
                f"FakeProvider called {len(self.requests)} times but only scripted "
                f"{len(self.requests) - 1} replies"
            )
        next_reply = self._replies.pop(0)
        if isinstance(next_reply, Exception):
            raise next_reply
        return next_reply
