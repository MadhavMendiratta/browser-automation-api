from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from database import User, get_db_session
from .security import decode_access_token

# Bearer scheme — auto_error=False so we can make auth optional
_bearer = HTTPBearer(auto_error=False)


def _resolve_user(user_id: int) -> Optional[User]:
    """Look up a user by ID and detach from session."""
    try:
        with get_db_session() as db:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                db.expunge(user)
            return user
    except Exception:
        return None


def _user_from_payload(payload: Optional[dict]) -> Optional[User]:
    """Given a decoded JWT payload, resolve the user or return None."""
    if payload is None:
        return None
    user_id_str = payload.get("sub")
    if user_id_str is None:
        return None
    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        return None
    return _resolve_user(user_id)


def _get_user_from_token(
    credentials: Optional[HTTPAuthorizationCredentials],
) -> Optional[User]:
    """Shared logic: extract user from JWT Bearer token, or return None."""
    if credentials is None:
        return None
    payload = decode_access_token(credentials.credentials)
    return _user_from_payload(payload)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> User:
    """Strict dependency — raises 401 if not authenticated."""
    user = _get_user_from_token(credentials)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[User]:
    """Optional dependency — returns None if no valid token."""
    return _get_user_from_token(credentials)


def get_user_from_cookie(request: Request) -> Optional[User]:
    """Resolve the current user from the refresh_token cookie.

    This is a pure read — no token minting, no response mutation.
    It decodes the refresh token to identify the user and returns
    the User object (or None).  Access tokens are NOT stored in
    cookies; the refresh cookie is only used to keep the UI session.
    """
    from .security import decode_refresh_token

    token = request.cookies.get("refresh_token")
    if not token:
        return None
    payload = decode_refresh_token(token)
    return _user_from_payload(payload)
