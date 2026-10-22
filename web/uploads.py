"""Reading one uploaded file (a screenshot, a voice note) from a multipart form, as it arrives.

Starlette's own form parser copies the whole upload to a temporary file on disk before a route runs, so an oversize upload is only
noticed after it has been written. A screenshot or a voice note must never touch the disk, and a too-big one must be cut off the moment it
passes the limit, even when it lies about its size (a chunked upload has no Content-Length at all). So this reads the request body chunk by
chunk into memory and gives up as soon as the file would pass `limit` bytes."""
from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Request
from starlette.requests import ClientDisconnect

try:
    from python_multipart import MultipartParser
    from python_multipart.exceptions import FormParserError
    from python_multipart.multipart import parse_options_header
except ModuleNotFoundError:  # pragma: no cover  (python-multipart before 0.0.13 is called `multipart`)
    from multipart import MultipartParser
    from multipart.exceptions import FormParserError
    from multipart.multipart import parse_options_header

OVERHEAD = 16_384  # the boundaries, part headers and small text fields that surround the file
FIELD_MAX, FIELDS_MAX = 256, 8  # the small text fields (the language hint) are tiny; anything bigger is cut, more than a few are ignored


class UploadError(Exception):
    """`reason` is "too_big" (past the limit) or "no_file" (not a multipart form, no `file` part, cut off, or garbled)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class Upload:
    data: bytes = b""
    mime: str = ""  # what the browser says the file is (a hint only: the readers look at the bytes)
    fields: dict[str, str] = field(default_factory=dict)


class _Collector:
    """Receives the multipart parser's callbacks and keeps only the `file` part and a few short text fields, in memory."""

    def __init__(self, limit: int) -> None:
        self.limit, self.up = limit, Upload()
        self._hname = self._hval = b""
        self._begin()

    def _begin(self) -> None:
        self.headers: dict[bytes, bytes] = {}
        self.name, self.is_file, self.keep, self.buf = "", False, False, bytearray()

    def on_part_begin(self) -> None:
        self._begin()

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._hname += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._hval += data[start:end]

    def on_header_end(self) -> None:
        self.headers[self._hname.lower()] = self._hval
        self._hname = self._hval = b""

    def on_headers_finished(self) -> None:
        _, options = parse_options_header(self.headers.get(b"content-disposition", b""))
        self.name = options.get(b"name", b"").decode("utf-8", "replace")
        self.is_file = b"filename" in options
        self.keep = self.name == "file" if self.is_file else len(self.up.fields) < FIELDS_MAX

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if not self.keep:
            return
        room = (self.limit if self.is_file else FIELD_MAX) - len(self.buf)
        if end - start > room:
            if self.is_file:
                raise UploadError("too_big")  # never hold more than the limit
            end = start + room
        self.buf += data[start:end]

    def on_part_end(self) -> None:
        if not self.keep:
            return
        if self.is_file:
            if not self.up.data:
                self.up.data = bytes(self.buf)
                self.up.mime = self.headers.get(b"content-type", b"").decode("latin-1").split(";")[0].strip().lower()
        else:
            self.up.fields[self.name] = self.buf.decode("utf-8", "replace")

    def on_end(self) -> None:
        pass


async def read_upload(request: Request, limit: int) -> Upload:
    """The `file` part of a multipart POST (at most `limit` bytes) and its small text fields. Raises UploadError."""
    kind, params = parse_options_header(request.headers.get("content-type", ""))
    boundary = params.get(b"boundary")
    if kind != b"multipart/form-data" or not boundary:
        raise UploadError("no_file")
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit + OVERHEAD:
        raise UploadError("too_big")  # said so up front: refuse without reading it
    sink = _Collector(limit)
    callbacks = {name: getattr(sink, name) for name in (
        "on_part_begin", "on_part_data", "on_part_end", "on_header_field", "on_header_value", "on_header_end", "on_headers_finished", "on_end")}
    parser = MultipartParser(boundary, callbacks)
    total = 0
    try:
        async for chunk in request.stream():
            total += len(chunk)
            if total > limit + OVERHEAD:
                raise UploadError("too_big")  # a chunked upload has no Content-Length to check, and a header can lie: count what really arrives
            parser.write(chunk)
        parser.finalize()
    except (FormParserError, ClientDisconnect) as e:
        raise UploadError("no_file") from e
    if not sink.up.data:
        raise UploadError("no_file")
    return sink.up
