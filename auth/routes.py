from fastapi import APIRouter, HTTPException, Depends, Request, Response, status
import logging

from database import User, get_db_session
from rate_limit import limiter
from .schemas import UserCreate, UserLogin, ForgotPasswordRequest, ResetPasswordRequest, TokenResponse, UserResponse
from .security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    create_reset_token,
    decode_reset_token,
    decode_refresh_token,
    REFRESH_TOKEN_EXPIRE_DAYS,
    RESET_TOKEN_EXPIRE_MINUTES,
)
from .dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

# Cookie settings shared by login / refresh / logout
_COOKIE_OPTS: dict = dict(
    key="refresh_token",
    httponly=True,
    samesite="lax",
    secure=False,  # set True behind HTTPS in production
    path="/",
)


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
def register(request: Request, payload: UserCreate):
    """Create a new user with hashed password."""
    with get_db_session() as db:
        # Check uniqueness
        if db.query(User).filter(User.email == payload.email).first():
            raise HTTPException(status_code=400, detail="Email already registered")
        if db.query(User).filter(User.username == payload.username).first():
            raise HTTPException(status_code=400, detail="Username already taken")

        user = User(
            username=payload.username,
            email=payload.email,
            hashed_password=hash_password(payload.password),
        )
        db.add(user)
        # commit handled by context manager

    return {"message": "User registered successfully"}


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(request: Request, payload: UserLogin, response: Response):
    """Validate credentials, return access token in JSON and set refresh token cookie."""
    with get_db_session() as db:
        user = db.query(User).filter(User.email == payload.email).first()

        if not user or not verify_password(payload.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        access_token = create_access_token(data={"sub": str(user.id)})
        refresh_token = create_refresh_token(data={"sub": str(user.id)})

    # Set refresh token as HTTP-only cookie
    response.set_cookie(
        **_COOKIE_OPTS,
        value=refresh_token,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )
    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request):
    """Read refresh token from cookie, validate it, and issue a new access token."""
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )

    payload = decode_refresh_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token payload",
        )

    new_access_token = create_access_token(data={"sub": user_id_str})
    return TokenResponse(access_token=new_access_token)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user's details."""
    return current_user


# --- Password Reset (API) ---

@router.post("/forgot-password")
@limiter.limit("3/minute")
def forgot_password(request: Request, payload: ForgotPasswordRequest):
    """Generate a password-reset token and log the reset link to the console.

    Always returns the same generic message regardless of whether the email
    exists, to prevent user-enumeration attacks.
    """
    from datetime import datetime, timedelta

    _GENERIC_MSG = {
        "message": "If that email is registered, a password-reset link has been sent."
    }

    with get_db_session() as db:
        user = db.query(User).filter(User.email == payload.email).first()
        if not user:
            return _GENERIC_MSG

        # Create reset token and persist it for single-use validation
        token = create_reset_token(data={"sub": str(user.id)})
        user.reset_token = token
        user.reset_token_expires = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)

    # Simulate email delivery — log reset link to console
    reset_link = f"{request.base_url}reset-password?token={token}"
    logger.info("PASSWORD RESET LINK (email simulation): %s", reset_link)
    print(f"\n{'='*60}")
    print(f"  PASSWORD RESET LINK (email simulation)")
    print(f"  {reset_link}")
    print(f"{'='*60}\n")

    return _GENERIC_MSG


@router.post("/reset-password")
@limiter.limit("5/minute")
def reset_password(request: Request, payload: ResetPasswordRequest):
    """Validate the reset token and update the user's password.

    The token must be:
      - a valid JWT with type "reset"
      - stored on the user row (single-use)
      - not expired (checked by JWT *and* DB expiry column)
    """
    from datetime import datetime

    # Decode JWT first
    token_payload = decode_reset_token(payload.token)
    if token_payload is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user_id_str = token_payload.get("sub")
    if user_id_str is None:
        raise HTTPException(status_code=400, detail="Invalid reset token")

    with get_db_session() as db:
        user = db.query(User).filter(User.id == int(user_id_str)).first()

        if not user:
            raise HTTPException(status_code=400, detail="Invalid reset token")

        # Single-use check: token stored in DB must match
        if user.reset_token != payload.token:
            raise HTTPException(status_code=400, detail="Reset token already used or invalid")

        # DB-side expiry check (belt-and-suspenders with JWT exp)
        if user.reset_token_expires is None or user.reset_token_expires < datetime.utcnow():
            raise HTTPException(status_code=400, detail="Reset token has expired")

        # All checks pass — update password and invalidate token
        user.hashed_password = hash_password(payload.new_password)
        user.reset_token = None
        user.reset_token_expires = None

    return {"message": "Password has been reset successfully"}
