"""
Tests for llm_provider.complete_with_retry.

Three agents each carried their own retry loop wrapping `model.invoke` in
`except (InternalServerError, RateLimitError)`. That shape is a trap once an
agent is routed through this module: `complete()` reports provider failures on
the response rather than raising, so the except clause stops matching anything
and the retry silently becomes dead code. `complete_with_retry` is the single
replacement, and it keys on `.ok`.

The contract worth pinning: it returns the last failed response rather than
raising. The writer falls back to unpolished research on give-up, the scorecard
emits a neutral score — forcing an exception would take that choice away.
"""

import src.llm_provider as llm
from src.llm_provider import LLMResponse, complete_with_retry


def _ok(text="fine"):
    return LLMResponse(text=text, provider="cli")


def _fail(error="boom"):
    return LLMResponse(text="", provider="cli", error=error)


def _install(monkeypatch, responses):
    """Feed complete() a scripted sequence and record how it was called."""
    calls = []

    def fake_complete(prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        return responses[min(len(calls) - 1, len(responses) - 1)]

    monkeypatch.setattr(llm, "complete", fake_complete)
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    return calls


def test_first_success_calls_once(monkeypatch):
    calls = _install(monkeypatch, [_ok("first")])
    result = complete_with_retry("p")
    assert result.ok and result.text == "first"
    assert len(calls) == 1, "a successful call must not be retried"


def test_retries_until_success(monkeypatch):
    calls = _install(monkeypatch, [_fail("429"), _fail("500"), _ok("third")])
    result = complete_with_retry("p", attempts=3)
    assert result.ok and result.text == "third"
    assert len(calls) == 3


def test_returns_last_failure_without_raising(monkeypatch):
    """The give-up contract: callers choose the fallback, not an exception."""
    calls = _install(monkeypatch, [_fail("still down")])
    result = complete_with_retry("p", attempts=3)
    assert not result.ok
    assert result.error == "still down"
    assert len(calls) == 3, "every attempt should be spent before giving up"


def test_attempts_is_a_total_not_an_extra(monkeypatch):
    """attempts=1 means one call, not one call plus one retry."""
    calls = _install(monkeypatch, [_fail()])
    complete_with_retry("p", attempts=1)
    assert len(calls) == 1


def test_backoff_is_exponential(monkeypatch):
    waits = []
    monkeypatch.setattr(llm, "complete", lambda prompt, **kw: _fail())
    monkeypatch.setattr(llm.time, "sleep", lambda s: waits.append(s))
    complete_with_retry("p", attempts=4, base_delay=2.0)
    assert waits == [2.0, 4.0, 8.0]


def test_kwargs_reach_complete(monkeypatch):
    """Model, token budget and timeout must survive the wrapper."""
    calls = _install(monkeypatch, [_ok()])
    complete_with_retry(
        "prompt text", max_tokens=1234, model="some-model", timeout=99, label="x"
    )
    assert calls[0]["prompt"] == "prompt text"
    assert calls[0]["max_tokens"] == 1234
    assert calls[0]["model"] == "some-model"
    assert calls[0]["timeout"] == 99
    assert "label" not in calls[0], "label is for logging, not for the provider"


def test_empty_completion_counts_as_failure(monkeypatch):
    """LLMResponse.ok is False for whitespace-only text; retry must honour that."""
    calls = _install(monkeypatch, [LLMResponse(text="   ", provider="cli"), _ok("real")])
    result = complete_with_retry("p", attempts=2)
    assert result.text == "real"
    assert len(calls) == 2
