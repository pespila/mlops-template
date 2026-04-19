from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    from aipacken import __version__

    return HealthResponse(status="ok", version=__version__)
