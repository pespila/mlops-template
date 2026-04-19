"""ASGI middleware that records every prediction.

Captures: timing, status, shape of input/output, model version, trace id.
Pushes records to an asyncio queue drained by a background task posting to
api:/internal/predictions (bulk). Drop-on-overflow; never blocks the request.

Real implementation lands in the next commit.
"""
