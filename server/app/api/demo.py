"""Global controls for this local demo dataset, serialized against simulator triggers."""
import asyncio
from pathlib import Path
import sys

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from server.app.api.simulations import simulator_request
from server.app.services.auth import require_auth, verify_origin
from server.core.database import get_session

router = APIRouter(prefix='/demo', tags=['demo'], dependencies=[Depends(require_auth), Depends(verify_origin)])


def clear_records(session):
    session.execute(text('SELECT pg_advisory_xact_lock(714202)'))
    session.execute(text('SELECT pg_advisory_xact_lock(714203)'))
    session.execute(text('UPDATE insurance.prior_authorization SET request_action_id = NULL'))
    session.execute(text('UPDATE kyron.conversation_transcript SET action = NULL'))
    for table in ('action_tasks', 'workflow_runs', 'conversation_event', 'action_executions', 'conversation_transcript', 'conversation_analysis', 'conversation_record'):
        session.execute(text(f'DELETE FROM kyron.{table}'))
    session.execute(text('UPDATE simulation.conversation SET is_used = false'))
    session.commit()


@router.post('/clear')
async def clear(session: Session = Depends(get_session)):
    await simulator_request('POST', '/maintenance/start')
    try:
        await run_in_threadpool(clear_records, session)
        return {'message': 'Conversation data cleared for all practices. All simulation samples are unused.'}
    finally:
        await simulator_request('POST', '/maintenance/end')


@router.post('/seed')
async def seed_data():
    await simulator_request('POST', '/maintenance/start')
    try:
        script = Path(__file__).resolve().parents[3] / 'seed_data.py'
        process = await asyncio.create_subprocess_exec(sys.executable, str(script),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            await asyncio.wait_for(process.communicate(), timeout=180)
        except (TimeoutError, asyncio.CancelledError):
            process.kill()
            await process.wait()
            raise HTTPException(503, 'Seeding did not finish. Please try again.')
        if process.returncode:
            raise HTTPException(500, 'Could not seed the demo data. Check the server configuration.')
        return {'message': 'Supporting records and simulation samples are ready. Run a simulation to create conversations.'}
    finally:
        await simulator_request('POST', '/maintenance/end')
