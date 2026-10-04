"""Bound request bodies before multipart parsing can spool an unlimited upload."""
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException

from newsrec.services.ingestion import MAX_BYTES


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = MAX_BYTES + 1024 * 1024 if scope["path"] == "/api/documents" else 2 * 1024 * 1024
        headers = dict(scope["headers"])
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "invalid content length"}, 400)(scope, receive, send)
        if length > limit:
            return await JSONResponse({"detail": "request body too large"}, 413)(scope, receive, send)
        total = 0

        class TooLarge(HTTPException):
            def __init__(self):
                super().__init__(413, "request body too large")

        async def bounded_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > limit:
                raise TooLarge()
            return message

        try:
            await self.app(scope, bounded_receive, send)
        except TooLarge:
            await JSONResponse({"detail": "request body too large"}, 413)(scope, receive, send)
