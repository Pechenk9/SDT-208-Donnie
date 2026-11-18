
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_session
from app.models import Branch, LoginSession, User


COOKIE_NAME = "session_token"
SESSION_LIFETIME_SECONDS = int(
    os.getenv("SESSION_LIFETIME_SECONDS", str(12 * 60 * 60))
)
if SESSION_LIFETIME_SECONDS <= 0:
    raise ValueError("SESSION_LIFETIME_SECONDS must be positive")

_secure_setting = os.getenv("SESSION_COOKIE_SECURE")
if _secure_setting is None:
    COOKIE_SECURE = os.getenv(
        "ENVIRONMENT",
        os.getenv("APP_ENV", "development"),
    ).lower() in {"production", "prod"}
else:
    if _secure_setting.lower() not in {"1", "true", "yes", "0", "false", "no"}:
        raise ValueError("SESSION_COOKIE_SECURE must be a boolean value")
    COOKIE_SECURE = _secure_setting.lower() in {"1", "true", "yes"}


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
) -> User | None:
    token = request.cookies.get(COOKIE_NAME)

    if not token:
        request.state.current_user = None
        return None

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    login_session = session.get(LoginSession, token_hash)

    if login_session is None:
        request.state.current_user = None
        return None

    expires_at = login_session.expires_at

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= datetime.now(timezone.utc):
        request.state.current_user = None
        return None

    user = login_session.user
    request.state.current_user = user

    return user


def get_current_branch(
    request: Request,
    session: Session = Depends(get_session),
) -> Branch | None:
    branch_code = request.cookies.get("selected_branch")
    if not branch_code:
        return None

    return session.scalar(
        select(Branch).where(Branch.code == branch_code)
    )


def create_login_session(
    user: User,
    session: Session,
    response: Response,
) -> None:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=SESSION_LIFETIME_SECONDS
    )

    session.add(
        LoginSession(
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            user_id=user.id,
            expires_at=expires_at,
        )
    )
    session.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_LIFETIME_SECONDS,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )


def invalidate_login_session(
    request: Request,
    session: Session,
) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    login_session = session.get(LoginSession, token_hash)
    if login_session is not None:
        session.delete(login_session)
        session.commit()


def login_required(
    user: User | None = Depends(get_current_user),
) -> User:
    if user is None:
        raise HTTPException(status_code=401)

    return user
