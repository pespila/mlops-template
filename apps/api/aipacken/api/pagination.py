"""Shared pagination params for list endpoints.

Every list router (`/datasets`, `/runs`, `/deployments`, `/experiments`,
`/models`) used to return the full table. At 10k+ rows that's a latency +
memory + payload-size cliff for the SPA (db.md P1 'Unbounded list
endpoints').

Applying `Pagination` as a FastAPI dependency gives every list endpoint a
uniform `?limit=…&offset=…` surface. Defaults are tuned for the UI's
typical page size; the hard cap stops a client from stampeding the DB
with `limit=10000000`.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query

_DEFAULT_LIMIT: int = 50
_MAX_LIMIT: int = 500


@dataclass(frozen=True, slots=True)
class Pagination:
    limit: int
    offset: int


def pagination_params(
    limit: int = Query(
        default=_DEFAULT_LIMIT,
        ge=1,
        le=_MAX_LIMIT,
        description=f"Page size (1-{_MAX_LIMIT}, default {_DEFAULT_LIMIT}).",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        le=100_000,
        description="Row offset for the page (0-based, max 100 000).",
    ),
) -> Pagination:
    return Pagination(limit=limit, offset=offset)
