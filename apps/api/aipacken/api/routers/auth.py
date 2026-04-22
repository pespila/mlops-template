from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.api.ratelimit import LOGIN_LIMIT, rate_limit
from aipacken.api.schemas.auth import LoginRequest, UserRead
from aipacken.db import get_db
from aipacken.db.models import User
from aipacken.services.auth import (
    get_current_user,
    hash_password,
    needs_rehash,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=UserRead,
    dependencies=[Depends(rate_limit(LOGIN_LIMIT))],
)
async def login(
    payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")
    # Opportunistic hash upgrade: a user whose stored hash is bcrypt (pre
    # the argon2 swap) or stale-parameter argon2 gets rewritten to the
    # current argon2id defaults on successful login. Zero-downtime
    # migration of every active account.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
        await db.commit()
    request.session["user_id"] = user.id
    return user


@router.post("/logout", status_code=204, response_class=Response)
async def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=204)


@router.get("/me", response_model=UserRead)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
