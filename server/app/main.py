from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from server.app.api import auth, conversations, events, simulations, records, directory
from server.core.config import settings
from server.core.database import engine
from server.core.seed import initialize_database


@asynccontextmanager
async def lifespan(app):
    initialize_database()
    yield
    engine.dispose()


app = FastAPI(title="Kyron Conversation Simulator", lifespan=lifespan)
for router in (conversations.router, auth.router):
    app.include_router(router, prefix="/api")
for router in (simulations.router, events.router, records.router, directory.router):
    app.include_router(router, prefix="/api/practices/{practice}")


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse(settings.client_url)


@app.get("/health", tags=["health"])
def health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok"}
