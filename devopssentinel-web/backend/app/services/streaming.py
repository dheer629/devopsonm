"""Server-Sent Events helpers (spec section 7 -- SSE, not WebSockets)."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Awaitable, Callable


def sse_event(event: str, data: Any) -> str:
    payload = data if isinstance(data, str) else json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n"


async def stream_operation(
    producer: Callable[[], Awaitable[Any]],
    *,
    stages: list[str] | None = None,
    heartbeat_s: float = 10.0,
) -> AsyncIterator[str]:
    """Yield progress events then the final result for a long operation."""
    yield sse_event("open", {"stages": stages or [], "status": "RUNNING"})
    task = asyncio.ensure_future(producer())
    try:
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=heartbeat_s)
            if not done:
                yield sse_event("heartbeat", {"status": "RUNNING"})
        result = task.result()
        yield sse_event("result", result)
    except Exception as exc:  # pragma: no cover - defensive
        yield sse_event("error", {"message": str(exc)})
    finally:
        if not task.done():
            task.cancel()
        yield sse_event("close", {"status": "DONE"})


async def stream_logs(lines: list[str], delay_s: float = 0.02) -> AsyncIterator[str]:
    """Replay captured log lines as an SSE stream for the log viewer."""
    for i, line in enumerate(lines, start=1):
        yield sse_event("log", {"n": i, "text": line})
        if delay_s:
            await asyncio.sleep(delay_s)
    yield sse_event("close", {"status": "DONE"})
