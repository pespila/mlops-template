from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.config import get_settings
from aipacken.db.models import User
from aipacken.services.auth import hash_password

logger = structlog.get_logger(__name__)


async def seed_admin(db: AsyncSession) -> User:
    settings = get_settings()
    result = await db.execute(select(User).where(User.role == "admin"))
    existing = result.scalars().first()
    if existing is not None:
        return existing

    user = User(
        email=settings.platform_admin_email,
        password_hash=hash_password(settings.platform_admin_password),
        role="admin",
        full_name="Administrator",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("seed.admin.created", email=user.email)
    return user
