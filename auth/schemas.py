import re

from pydantic import BaseModel, EmailStr, field_validator


# --- Reusable validators ---
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,20}$")
_PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$")


def _validate_username(v: str) -> str:
    if not _USERNAME_RE.match(v):
        raise ValueError(
            "Username must be 3-20 characters and contain only letters, numbers, or underscores"
        )
    return v


def _validate_password(v: str) -> str:
    if not _PASSWORD_RE.match(v):
        raise ValueError(
            "Password must be at least 8 characters with 1 uppercase letter, "
            "1 lowercase letter, and 1 digit"
        )
    return v


# --- Request models ---
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    confirm_password: str

    @field_validator("username")
    @classmethod
    def check_username(cls, v: str) -> str:
        return _validate_username(v)

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return _validate_password(v)

    @field_validator("confirm_password")
    @classmethod
    def check_passwords_match(cls, v: str, info) -> str:
        password = info.data.get("password")
        if password and v != password:
            raise ValueError("Passwords do not match")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return _validate_password(v)

    @field_validator("confirm_password")
    @classmethod
    def check_passwords_match(cls, v: str, info) -> str:
        password = info.data.get("new_password")
        if password and v != password:
            raise ValueError("Passwords do not match")
        return v


# --- Response models ---
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    email: str

    class Config:
        from_attributes = True
