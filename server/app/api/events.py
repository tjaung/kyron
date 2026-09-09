import asyncio
import json

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from server.app.crud.conversations import events_after
from server.core.database import SessionLocal

router = APIRouter(tags=["stream"])


def read_events(cursor):
    with SessionLocal() as session:
        return events_after(session, cursor)


@router.get("/events")
async def stream(request: Request, last_event_id: str = Header(default="0")):
    try:
        cursor = int(last_event_id)
        if cursor < 0:
            raise ValueError
    except ValueError as error:
        raise HTTPException(400, "Invalid Last-Event-ID") from error

    async def events():
        nonlocal cursor
        idle = 0
        while not await request.is_disconnected():
            rows = await run_in_threadpool(read_events, cursor)
            for row in rows:
                yield f"id: {row['id']}\ndata: {json.dumps(row['data'])}\n\n"
                cursor = row["id"]
            if rows:
                idle = 0
            else:
                idle += 1
                if idle % 25 == 0:
                    yield ": keepalive\n\n"
                await asyncio.sleep(0.2)

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })
