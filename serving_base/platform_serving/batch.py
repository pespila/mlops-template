"""Streaming batch readers for CSV / Excel uploads."""

from __future__ import annotations

import io
from pathlib import Path
from typing import IO, Iterator

import pandas as pd
from fastapi import UploadFile


def _suffix(upload: UploadFile) -> str:
    name = upload.filename or ""
    return Path(name).suffix.lower()


def iter_chunks(file: UploadFile, chunk_size: int = 1000) -> Iterator[pd.DataFrame]:
    """Yield DataFrame chunks of at most *chunk_size* rows.

    Supports CSV/TSV (true streaming via ``pandas.read_csv(chunksize=)``) and
    Excel (buffered — pandas cannot stream xlsx).
    """
    suffix = _suffix(file)
    stream: IO[bytes] = file.file  # SpooledTemporaryFile

    if suffix in (".csv", ".tsv", ".txt"):
        sep = "\t" if suffix in (".tsv", ".txt") else ","
        reader = pd.read_csv(stream, chunksize=chunk_size, sep=sep)
        for chunk in reader:
            yield chunk
        return

    if suffix in (".xlsx", ".xls"):
        buf = io.BytesIO(stream.read())
        df = pd.read_excel(buf)
        for start in range(0, len(df), chunk_size):
            yield df.iloc[start : start + chunk_size].copy()
        return

    raise ValueError(f"unsupported batch file type: {suffix!r}")


__all__ = ["iter_chunks"]
