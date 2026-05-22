"""JWT authentication and demo user store for MarketPulse India.

Real DB-backed users will replace DEMO_USERS in Week 5.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict

from backend.config import settings
from backend.exceptions import InvalidTokenError

# auto_error=False so a missing header gives token=None instead of raising
# HTTPException — we raise InvalidTokenError ourselves for consistent JSON shape.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

router = APIRouter()


# ---------------------------------------------------------------------------
# Password helpers — use bcrypt directly (passlib + bcrypt>=4 has compat issues)
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# Demo users — replace with DB in production (Week 5)
# ---------------------------------------------------------------------------

DEMO_USERS: dict[str, dict[str, str]] = {
    "manish@marketpulse.in": {
        "password_hash": hash_password("demo123"),
        "user_id": "00000000-0000-0000-0000-000000000001",
        "name": "Manish",
        "email": "manish@marketpulse.in",
    }
}


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    payload = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    )
    payload["exp"] = expire
    payload["iat"] = datetime.now(UTC)
    return jwt.encode(  # type: ignore[no-any-return]
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def verify_token(token: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        raise InvalidTokenError() from None


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> dict[str, Any]:
    if not token:
        raise InvalidTokenError()
    payload = verify_token(token)
    email = payload.get("sub")
    if not isinstance(email, str) or email not in DEMO_USERS:
        raise InvalidTokenError()
    user = DEMO_USERS[email]
    return {
        "email": email,
        "user_id": user["user_id"],
        "name": user["name"],
    }


CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TokenResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    access_token: str
    token_type: str
    expires_in: int


class UserResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    email: str
    user_id: str
    name: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenResponse:
    user = DEMO_USERS.get(form.username)
    if user is None or not verify_password(form.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": form.username, "user_id": user["user_id"]})
    return TokenResponse(
        access_token=token,
        token_type="bearer",  # noqa: S106
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.get("/auth/me", response_model=UserResponse)
async def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse(
        email=current_user["email"],
        user_id=current_user["user_id"],
        name=current_user["name"],
    )


__all__ = [
    "DEMO_USERS",
    "CurrentUser",
    "TokenResponse",
    "UserResponse",
    "create_access_token",
    "get_current_user",
    "hash_password",
    "router",
    "verify_password",
    "verify_token",
]
