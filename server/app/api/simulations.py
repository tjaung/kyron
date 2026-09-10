from uuid import UUID
import random
import logging
import time
from simulator.debug_logging import log

from fastapi import APIRouter, Depends, HTTPException
import httpx
from sqlalchemy.orm import Session

from server.app.crud.simulations import list_scenarios
from server.core.config import settings
from server.core.database import get_session
from server.models.simulation import SimulationConversation
from server.app.services.auth import require_auth, verify_origin
from server.schemas.auth import AuthSession

router = APIRouter(prefix="/simulations", tags=["simulations"])


async def simulator_request(method, path, **kwargs):
    started = time.monotonic()
    level = logging.DEBUG if method == 'GET' else logging.INFO
    log('simulator.request.started', level=level, endpoint=path)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.request(method, settings.simulator_url + path, headers={"Authorization": "Bearer " + settings.simulator_token}, **kwargs)
    except httpx.RequestError as error:
        log('simulator.request.failed', level=logging.ERROR, exc_info=True, endpoint=path)
        raise HTTPException(503, "Simulator is unavailable") from error
    log('simulator.request.completed', level=logging.WARNING if response.is_error else level,
        endpoint=path, status_code=response.status_code, duration_ms=round((time.monotonic()-started)*1000))
    if response.status_code == 409:
        raise HTTPException(409, "A simulation is already running")
    if response.is_error:
        raise HTTPException(502, "Simulator rejected the request")
    return response.json()


@router.get("")
def scenarios(session: Session = Depends(get_session), auth: AuthSession = Depends(require_auth)):
    return list_scenarios(session, auth.practice.practice_id)


@router.get("/status")
async def status(session: Session = Depends(get_session), auth: AuthSession = Depends(require_auth)):
    state = await simulator_request("GET", "/status")
    source_id = state.get("source_conversation_id")
    if source_id:
        source = session.get(SimulationConversation, UUID(source_id))
        if source is None or source.context["metadata"]["practice_id"] != str(auth.practice.practice_id):
            return {"status": "busy" if state["status"] == "running" else "idle"}
    return state


@router.post("/random", status_code=202, dependencies=[Depends(verify_origin)])
async def random_conversation(session: Session = Depends(get_session), auth: AuthSession = Depends(require_auth)):
    available = [row for row in list_scenarios(session, auth.practice.practice_id) if not row["is_used"]]
    if not available:
        raise HTTPException(409, "No unused scenarios for this practice")
    source_id = UUID(random.choice(available)["conversation_id"])
    validate_chain(session, source_id, auth.practice.practice_id)
    return await simulator_request("POST", "/trigger", json={"conversation_id": str(source_id)})


@router.post("/{conversation_id}/run", status_code=202, dependencies=[Depends(verify_origin)])
async def specific_conversation(conversation_id: UUID, session: Session = Depends(get_session),
                                auth: AuthSession = Depends(require_auth)):
    validate_chain(session, conversation_id, auth.practice.practice_id)
    return await simulator_request("POST", "/trigger", json={"conversation_id": str(conversation_id)})


def validate_chain(session, source_id, practice_id):
    visited = set()
    while source_id:
        if source_id in visited or len(visited) >= 100:
            raise HTTPException(409, "Invalid conversation chain")
        visited.add(source_id)
        source = session.get(SimulationConversation, source_id)
        if source is None or source.context["metadata"]["practice_id"] != str(practice_id):
            raise HTTPException(404, "Source conversation not found in this practice")
        if source.is_used:
            raise HTTPException(409, "Source conversation has already been used")
        source_id = source.next_conversation
