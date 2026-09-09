from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from server.app.services.auth import require_auth
from server.core.database import get_session
from server.models.conversation import ConversationRecord
from server.schemas.auth import AuthSession
from server.schemas.conversation import ConversationPage

router = APIRouter(tags=["conversations"])


@router.get("/conversations", response_model=ConversationPage)
def list_records(response: Response, limit: int = Query(50, ge=1, le=100),
                 offset: int = Query(0, ge=0), auth: AuthSession = Depends(require_auth),
                 session: Session = Depends(get_session)):
    scope = ConversationRecord.practice_id == auth.practice.practice_id
    total = session.scalar(select(func.count()).select_from(ConversationRecord).where(scope))
    rows = session.scalars(select(ConversationRecord).where(scope).order_by(
        ConversationRecord.start_time.desc(), ConversationRecord.id.desc(),
    ).offset(offset).limit(limit)).all()
    response.headers["Cache-Control"] = "no-store"
    return {"items": rows, "total": total}
