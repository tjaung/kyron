from contextlib import asynccontextmanager
import logging
import re
import time
from uuid import UUID, uuid4
from simulator.debug_logging import configure, log, log_context

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from server.app.api import auth, conversations, events, simulations, records, directory, demo, workflows, agent
from server.core.config import settings
from server.core.database import engine
from server.core.seed import initialize_database


@asynccontextmanager
async def lifespan(app):
    initialize_database()
    yield
    engine.dispose()


configure("server")

app = FastAPI(title="Kyron Conversation Simulator", lifespan=lifespan)
@app.middleware('http')
async def diagnostic_requests(request, call_next):
    try:
        request_id = str(UUID(request.headers.get('X-Request-ID', '')))
    except ValueError:
        request_id = str(uuid4())
    match = re.search(r'/conversations/([0-9a-fA-F-]{36})(?:/|$)', request.url.path)
    fields = {'service':'server', 'request_id':request_id, 'method':request.method}
    if match: fields['conversation_id'] = match.group(1)
    # High-volume ingestion and health/poll requests are DEBUG; errors stay visible.
    level = logging.DEBUG if request.method == 'GET' or request.url.path.endswith('/events') else logging.INFO
    started = time.monotonic()
    with log_context(**fields):
        log('api.request.started', level=level)
        try:
            response = await call_next(request)
        except Exception:
            log('api.request.failed', level=logging.ERROR, exc_info=True,
                duration_ms=round((time.monotonic()-started)*1000))
            raise
        route = request.scope.get('route')
        log('api.request.completed', level=logging.WARNING if response.status_code >= 400 else level,
            route=getattr(route, 'path', None), status_code=response.status_code,
            duration_ms=round((time.monotonic()-started)*1000))
        response.headers['X-Request-ID'] = request_id
        return response


for router in (conversations.router, auth.router, agent.router):
    app.include_router(router, prefix="/api")
for router in (simulations.router, events.router, records.router, directory.router, demo.router, workflows.router):
    app.include_router(router, prefix="/api/practices/{practice}")


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse(settings.client_url)


@app.get("/health", tags=["health"])
def health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok"}
