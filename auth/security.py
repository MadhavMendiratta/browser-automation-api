import os
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

# --- Configuration ---
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7
RESET_TOKEN_EXPIRE_MINUTES = 15


def _get_secret_key() -> str:
    return os.getenv("SECRET_KEY", "change-me-in-production")


# --- Password hashing ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# --- JWT ---
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, _get_secret_key(), algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a long-lived refresh token (7 days by default)."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, _get_secret_key(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and return the payload, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        # Accept tokens without a "type" claim for backward compatibility,
        # but reject tokens explicitly typed as something other than "access".
        token_type = payload.get("type")
        if token_type is not None and token_type != "access":
            return None
        return payload
    except JWTError:
        return None


def decode_refresh_token(token: str) -> Optional[dict]:
    """Decode a refresh token.  Returns the payload or None."""
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            return None
        return payload
    except JWTError:
        return None


# --- Password-reset tokens ---
def create_reset_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a short-lived reset token (15 min by default)."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "reset"})
    return jwt.encode(to_encode, _get_secret_key(), algorithm=ALGORITHM)


def decode_reset_token(token: str) -> Optional[dict]:
    """Decode a password-reset token. Returns the payload or None."""
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        if payload.get("type") != "reset":
            return None
        return payload
    except JWTError:
        return None
