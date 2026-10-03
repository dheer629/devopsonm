"""SSE endpoints for live refresh, long scans and streamed logs."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from ..security import validate_name
from ..services.streaming import sse_event, stream_operation
from .deps import Scope, invoke, scope

router = APIRouter(prefix="/api/v1/stream", tags=["stream"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.get("/live")
async def live(sc: Scope = Depends(scope)) -> StreamingResponse:
    async def producer():
        result = await invoke("workloads.triage", sc)
        return result["envelope"]

    async def gen() -> AsyncIterator[str]:
        async for chunk in stream_operation(
            producer,
            stages=["Collecting workloads", "Collecting events", "Correlating findings"],
        ):
            yield chunk

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/logs")
async def logs(
    name: str = Query(...),
    sc: Scope = Depends(scope),
    container: str = Query(""),
    tail: int = Query(500, ge=1, le=100000),
) -> StreamingResponse:
    validate_name(name, field="pod")

    async def gen() -> AsyncIterator[str]:
        yield sse_event("open", {"pod": name, "status": "RUNNING"})
        result = await invoke("workloads.triage_workload", sc, params={"kind": "Pod", "name": name})
        lines = result["raw"].get("stdout", "").splitlines()[-tail:]
        for i, line in enumerate(lines, start=1):
            yield sse_event("log", {"n": i, "text": line, "level": "INFO"})
            await asyncio.sleep(0.01)
        yield sse_event("close", {"status": "DONE"})

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)
