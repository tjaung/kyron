"""Simple provider login and practice-scoped JWT sessions."""

from datetime import datetime, timedelta, timezone
import re
import secrets
from uuid import UUID

from fastapi import Depends, HTTPException, Request
import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from server.core.config import settings
from server.core.database import get_session
from server.models.context import Practice, Provider, ProviderPractice
from server.schemas.auth import AuthSession, PracticeInfo, ProviderInfo

COOKIE_NAME = "kyron_session"


def practice_info(practice):
    slug = re.sub(r"[^a-z0-9]+", "-", practice.name.lower()).strip("-")
    return PracticeInfo(practice_id=practice.practice_id, name=practice.name, slug=slug)


def find_practice(session, slug):
    matches = [row for row in session.scalars(select(Practice)) if practice_info(row).slug == slug]
    if len(matches) != 1:
        raise HTTPException(404, "Practice not found")
    return matches[0]


def identity(practice, provider):
    return AuthSession(practice=practice_info(practice), provider=ProviderInfo(
        provider_id=provider.provider_id, first_name=provider.first_name,
        last_name=provider.last_name, username=f"{provider.first_name}.{provider.last_name}".lower(),
    ))


def authenticate(session, practice, username, password):
    providers = session.scalars(select(Provider).join(
        ProviderPractice, ProviderPractice.provider_id == Provider.provider_id,
    ).where(
        ProviderPractice.practice_id == practice.practice_id,
        func.lower(Provider.first_name + "." + Provider.last_name) == username.strip().lower(),
    ).distinct()).all()
    if len(providers) != 1 or not secrets.compare_digest(password.encode(), b"password"):
        raise HTTPException(401, "Invalid username or password for this practice")
    return identity(practice, providers[0])


def issue_token(auth):
    now = datetime.now(timezone.utc)
    return jwt.encode({
        "sub": str(auth.provider.provider_id), "practice_id": str(auth.practice.practice_id),
        "iat": now, "exp": now + timedelta(seconds=settings.session_seconds),
        "iss": "kyron", "aud": "kyron-client",
    }, settings.jwt_secret, algorithm="HS256")


def decode_token(token):
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"],
            issuer="kyron", audience="kyron-client",
            options={"require": ["sub", "practice_id", "iat", "exp", "iss", "aud"]})
    except jwt.InvalidTokenError as error:
        raise HTTPException(401, "Session expired or invalid") from error


def require_auth(request: Request, practice: str, session: Session = Depends(get_session)):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, "Sign in to continue")
    claims = decode_token(token)
    tenant = find_practice(session, practice)
    if claims["practice_id"] != str(tenant.practice_id):
        raise HTTPException(403, "Session belongs to another practice")
    try:
        provider_id = UUID(claims["sub"])
    except (ValueError, TypeError) as error:
        raise HTTPException(401, "Invalid session") from error
    provider = session.scalar(select(Provider).join(
        ProviderPractice, ProviderPractice.provider_id == Provider.provider_id,
    ).where(Provider.provider_id == provider_id, ProviderPractice.practice_id == tenant.practice_id))
    if provider is None:
        raise HTTPException(403, "Provider is not a member of this practice")
    return identity(tenant, provider)


def verify_origin(request: Request):
    origin = request.headers.get("origin")
    allowed = {settings.client_url.rstrip("/"), str(request.base_url).rstrip("/")}
    if origin and origin not in allowed:
        raise HTTPException(403, "Request origin is not allowed")


def require_simulator(request: Request):
    expected = settings.simulator_token
    supplied = request.headers.get("authorization", "")
    if not expected or not secrets.compare_digest(supplied.encode(), f"Bearer {expected}".encode()):
        raise HTTPException(401, "Simulator authentication required")
