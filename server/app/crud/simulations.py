from sqlalchemy import exists, select
from sqlalchemy.orm import aliased

from server.models.simulation import SimulationConversation


def list_scenarios(session):
    parent = aliased(SimulationConversation)
    rows = session.scalars(select(SimulationConversation).where(~exists().where(
        parent.next_conversation == SimulationConversation.conversation_id,
    )).order_by(SimulationConversation.name))
    return [{"conversation_id": str(row.conversation_id), "name": row.name,
             "is_used": row.is_used, "next_conversation": row.next_conversation} for row in rows]
