"""Shared HTTP utilities for all model client connections.

Provides a keep-alive ``OpenerDirector`` (avoids TCP/TLS handshake per call)
and streaming helpers shared across providers.
"""

import urllib.request
from typing import Iterator


_opener = urllib.request.build_opener(
    urllib.request.HTTPHandler(),
    urllib.request.HTTPSHandler(),
)
_opener.addheaders = [("Connection", "keep-alive")]


def open_request(request, timeout=None):
    """Open *request* through the shared keep-alive opener.

    Drop-in replacement for ``urllib.request.urlopen(request, timeout=...)``.
    """
    if timeout is not None:
        return _opener.open(request, timeout=timeout)
    return _opener.open(request)


def iter_stream_lines(response, buffer_size: int = 4096) -> Iterator[str]:
    """Read a streaming HTTP response and yield individual non-empty lines.

    Handles chunk boundaries transparently so callers can focus on per-line
    processing (NDJSON, SSE, etc.) without buffering logic.

    Lines are buffered as bytes and decoded whole: a multi-byte UTF-8
    character split across two network chunks is reassembled before decoding,
    so a stream never raises UnicodeDecodeError at a chunk boundary.
    """
    buffer = b""
    while True:
        chunk = response.read(buffer_size)
        if not chunk:
            break
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            line = line.strip()
            if line:
                yield line.decode("utf-8", errors="replace")
    # Flush any trailing partial line (no final newline in the stream)
    if buffer.strip():
        yield buffer.decode("utf-8", errors="replace")


def resolve_env_var(value: str) -> str:
    """Resolve ``${VAR}`` patterns in *value* from ``os.environ``."""
    import os
    import re

    if not isinstance(value, str) or "${" not in value:
        return value

    def _replace(match: re.Match) -> str:
        return os.environ.get(match.group(1), "")

    return re.sub(r"\$\{(\w+)\}", _replace, value)
