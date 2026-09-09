from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from server.app.api import conversations, events, simulations
from server.core.database import engine
from server.core.seed import initialize_database


@asynccontextmanager
async def lifespan(app):
    initialize_database()
    yield
    engine.dispose()


app = FastAPI(title="Kyron Conversation Simulator", lifespan=lifespan)
for router in (conversations.router, simulations.router, events.router):
    app.include_router(router, prefix="/api")

STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/health", tags=["health"])
def health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok"}
