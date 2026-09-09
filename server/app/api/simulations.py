from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
import httpx
from sqlalchemy.orm import Session

from server.app.crud.simulations import list_scenarios
from server.core.config import settings
from server.core.database import get_session
from server.models.simulation import SimulationConversation

router = APIRouter(prefix="/simulations", tags=["simulations"])


async def simulator_request(method, path, **kwargs):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.request(method, settings.simulator_url + path, **kwargs)
    except httpx.RequestError as error:
        raise HTTPException(503, "Simulator is unavailable") from error
    if response.status_code == 409:
        raise HTTPException(409, "A simulation is already running")
    if response.is_error:
        raise HTTPException(502, "Simulator rejected the request")
    return response.json()


@router.get("")
def scenarios(session: Session = Depends(get_session)):
    return list_scenarios(session)


@router.get("/status")
async def status():
    return await simulator_request("GET", "/status")


@router.post("/random", status_code=202)
async def random_conversation():
    return await simulator_request("POST", "/trigger", json={})


@router.post("/{conversation_id}/run", status_code=202)
async def specific_conversation(conversation_id: UUID, session: Session = Depends(get_session)):
    source = session.get(SimulationConversation, conversation_id)
    if source is None:
        raise HTTPException(404, "Source conversation not found")
    if source.is_used:
        raise HTTPException(409, "Source conversation has already been used")
    return await simulator_request("POST", "/trigger", json={"conversation_id": str(conversation_id)})
