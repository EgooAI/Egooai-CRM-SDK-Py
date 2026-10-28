"""Cooperative cancellation for one agent run.

A run checks its token at turn boundaries: before each LLM request and before
each tool call. An in-flight request is never aborted mid-flight; it finishes
and its answer is thrown away, so cancellation is observable and predictable.
"""

from __future__ import annotations

from threading import Event

from agent_pipeline.errors import RunCancelledError


class CancellationToken:
    """Thread-safe one-way switch shared by a run and its canceller."""

    def __init__(self) -> None:
        self._event = Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise RunCancelledError("run cancelled")


__all__ = ["CancellationToken"]
