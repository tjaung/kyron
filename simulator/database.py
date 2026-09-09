"""PostgreSQL connections; the caller owns the transaction lifetime."""

import os


def connect():
    # Keep the driver out of the replay engine and its tests.
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(
        os.environ["DATABASE_URL"],
        row_factory=dict_row,
        connect_timeout=10,
        application_name="kyron-simulator",
    )
