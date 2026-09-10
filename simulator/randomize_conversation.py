"""Select an unused context source and reserve it until generation and analysis finish."""

from uuid import UUID


def randomize_conversation(connection, conversation_id=None):
    if conversation_id is None:
        return connection.execute(
            """
            SELECT source.conversation_id, source.name, source.context, source.next_conversation
            FROM simulation.conversation AS source
            WHERE source.is_used = FALSE
              AND NOT EXISTS (
                  SELECT 1 FROM simulation.conversation AS parent
                  WHERE parent.next_conversation = source.conversation_id
              )
            ORDER BY random()
            LIMIT 1
            FOR NO KEY UPDATE SKIP LOCKED
            """
        ).fetchone()

    return get_conversation(connection, conversation_id)


def get_conversation(connection, conversation_id):
    """Lock a particular unused source, including a follow-up conversation."""
    return connection.execute(
        """
        SELECT conversation_id, name, context, next_conversation
        FROM simulation.conversation
        WHERE is_used = FALSE AND conversation_id = %s
        FOR NO KEY UPDATE SKIP LOCKED
        """,
        (UUID(str(conversation_id)),),
    ).fetchone()


def mark_used(connection, conversation_id):
    connection.execute(
        "UPDATE simulation.conversation SET is_used = TRUE WHERE conversation_id = %s",
        (conversation_id,),
    )
