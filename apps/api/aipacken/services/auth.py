from __future__ import annotations

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.db import get_db
from aipacken.db.models import User

# Argon2id is the default — no-argument PasswordHasher already picks the
# RFC-9106 "second recommended" cost (t=3, m=64MiB, p=4). All NEW password
# hashes written by hash_password() are argon2id; bcrypt verification is
# kept only so admins whose hashes predate this swap can still log in
# (their next successful login upgrades them). Closes the python-pro /
# security-auditor finding 'passlib==1.7.4 unmaintained'.
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    # argon2id hashes start with "$argon2", bcrypt with "$2a"/"$2b"/"$2y".
    # Route each to the right verifier. Returning False (not raising) on
    # mismatch keeps the login endpoint's 401 path clean.
    if hashed.startswith("$argon2"):
        try:
            return _hasher.verify(hashed, password)
        except (VerifyMismatchError, InvalidHashError):
            return False
    if hashed.startswith("$2"):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except ValueError:
            return False
    return False


def needs_rehash(hashed: str) -> bool:
    """True if *hashed* should be re-written with the current argon2 params.

    Old bcrypt hashes (from before this swap) always need rehash; current
    argon2 hashes are compared against the hasher's live parameters so a
    later cost bump auto-migrates everyone on next login.
    """
    if hashed.startswith("$2"):
        return True
    try:
        return _hasher.check_needs_rehash(hashed)
    except InvalidHashError:
        return True


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_authenticated")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="inactive_user")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_required")
    return user
