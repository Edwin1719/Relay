"""Tests for http_client.iter_stream_lines — streaming line parsing.

Network calls are simulated with fake responses; no real HTTP.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from http_client import iter_stream_lines


class FakeResponse:
    """Minimal file-like object returning canned read() chunks."""

    def __init__(self, chunks):
        self._chunks = list(chunks)

    def read(self, _size):
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


# ── iter_stream_lines ──────────────────────────────────────────

class TestIterStreamLines:
    def test_yields_nonempty_lines(self):
        resp = FakeResponse([b"line1\n\nline2\n", b"line3\n"])
        assert list(iter_stream_lines(resp)) == ["line1", "line2", "line3"]

    def test_multibyte_split_across_chunk_boundary(self):
        """A UTF-8 char straddling two 4096-byte chunks must not raise.

        Regression: the old implementation decoded each chunk independently,
        raising UnicodeDecodeError at position 4094-4095 when a multi-byte
        character was split across the read() boundary.
        """
        # 4094 ASCII bytes + first byte of 'ñ' (\xc3\xb1) at the chunk edge
        chunks = [b"a" * 4094 + b"\xc3", b"\xb1\nsecond\n"]
        lines = list(iter_stream_lines(FakeResponse(chunks)))
        assert lines[0] == "a" * 4094 + "ñ"
        assert lines[1] == "second"

    def test_trailing_partial_multibyte_without_newline(self):
        """Stream cut mid-character (no trailing newline) decodes safely."""
        lines = list(iter_stream_lines(FakeResponse([b"final\xc3"])))
        assert len(lines) == 1
        assert lines[0].startswith("final")
