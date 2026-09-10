from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from server.app.crud import conversations
from server.core.database import get_session
from server.schemas.conversation import ConversationCreate, ConversationEvent
from server.app.services.auth import require_simulator

router = APIRouter(prefix="/conversations", tags=["conversations"],
                   dependencies=[Depends(require_simulator)])


@router.post("", status_code=201)
def create(payload: ConversationCreate, session: Session = Depends(get_session)):
    record = conversations.create_conversation(session, payload)
    session.commit()
    return {"id": record.id}


@router.post("/{conversation_id}/events", status_code=204)
def ingest(conversation_id: UUID, event: ConversationEvent,
           session: Session = Depends(get_session)):
    conversations.append_event(session, conversation_id, event)
    session.commit()
    return Response(status_code=204)
