from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from server.app.services.auth import (
    COOKIE_NAME, authenticate, find_practice, issue_token, practice_info, require_auth, verify_origin,
)
from server.core.config import settings
from server.core.database import get_session
from server.models.context import Practice
from server.schemas.auth import AuthSession, LoginRequest, PracticeInfo

router = APIRouter(tags=["auth"])


@router.get("/practices", response_model=list[PracticeInfo])
def practices(session: Session = Depends(get_session)):
    return [practice_info(row) for row in session.scalars(select(Practice).order_by(Practice.name))]


@router.get("/practices/{practice}", response_model=PracticeInfo)
def practice_details(practice: str, session: Session = Depends(get_session)):
    return practice_info(find_practice(session, practice))


@router.post("/practices/{practice}/auth/login", response_model=AuthSession,
             dependencies=[Depends(verify_origin)])
def login(practice: str, payload: LoginRequest, response: Response, session: Session = Depends(get_session)):
    auth = authenticate(session, find_practice(session, practice), payload.username, payload.password)
    response.set_cookie(COOKIE_NAME, issue_token(auth), httponly=True, secure=settings.cookie_secure,
                        samesite="lax", path="/", max_age=settings.session_seconds)
    response.headers["Cache-Control"] = "no-store"
    return auth


@router.get("/practices/{practice}/auth/me", response_model=AuthSession)
def me(response: Response, auth: AuthSession = Depends(require_auth)):
    response.headers["Cache-Control"] = "no-store"
    return auth


@router.post("/practices/{practice}/auth/logout", status_code=204,
             dependencies=[Depends(verify_origin)])
def logout():
    # Logout must also work with an expired cookie.
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True,
                           secure=settings.cookie_secure, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return response
