"""Offline ASGI integration checks for request budgets and file delivery failures.

Run from backend: python -m scripts.verify_http_readiness
Uses the production app without its database/provider startup; no unit runner,
external calls, application data, or model requests are involved.
"""
import asyncio
from contextlib import contextmanager
from threading import BoundedSemaphore
from types import SimpleNamespace
from uuid import uuid4

import anyio
import httpx
from starlette.requests import Request

from app.main import app
from app.files import delivery


async def request_checks():
    # Invalid bodies never call these services; dependencies still resolve them.
    app.state.auth_service = None
    app.state.files_service = None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://check") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        size = 2 * 1024 * 1024 + 1
        for media in (None, "application/json", "text/plain", "application/octet-stream", "multipart/form-data; boundary=check"):
            headers = {} if media is None else {"Content-Type": media}
            response = await client.post("/api/v1/auth/login", content=b" " * size, headers=headers)
            assert response.status_code == 413, (media, response.status_code)
            assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"
            async def chunks():
                yield b" " * (1024 * 1024)
                yield b" " * (1024 * 1024 + 1)
            response = await client.post("/api/v1/auth/login", content=chunks(), headers=headers)
            assert response.status_code == 413, ("chunked", media, response.status_code)
        response = await client.post("/api/v1/auth/login", content=b"{}")
        assert response.status_code == 422  # Still parsed and validated without Content-Type.
        response = await client.post("/api/v1/files/uploads", content=b"x", headers={"Content-Length": str(30 * 1024 * 1024)})
        assert response.status_code == 413
        # Exercise the real HTTP route with synthetic authorization metadata.
        from app.auth.dependencies import require_identity
        old_authorize = delivery.authorize
        delivery.authorize = lambda *_: dict(size_bytes=20, media_type="text/plain", filename="source.txt")
        app.dependency_overrides[require_identity] = lambda: SimpleNamespace(learner_id=str(uuid4()))
        try:
            response = await client.get(f"/api/v1/files/{uuid4()}/content?binding_id={uuid4()}", headers={"Range": "bytes=" + "9" * 5000 + "-"})
            assert response.status_code == 416
            assert response.headers["Content-Range"] == "bytes */20"
        finally:
            delivery.authorize = old_authorize
            app.dependency_overrides.pop(require_identity, None)
    print("HTTP integration: declared/chunked sizes across five media types, small JSON, upload budget, huge Range: passed")


async def cleanup_check(cancelled):
    """Drive delivery acquisition failure through a cancelled AnyIO scope.

    Provider/registry stand-ins fail deterministically; the real delivery layer
    must release its concurrency slot and registry lease even if provider cleanup
    also fails.
    """
    closed = []
    slots = BoundedSemaphore(1)
    @contextmanager
    def lease(*_):
        try:
            yield {}
        finally:
            closed.append("lease")
    class Upstream:
        def __enter__(self):
            if cancelled:
                scope.cancel()
            raise RuntimeError("Synthetic acquisition failure")
        def __exit__(self, *_):
            closed.append("provider")
            raise RuntimeError("Synthetic provider close failure")
    files = SimpleNamespace(slots=slots, open_original=lease, provider=SimpleNamespace(stream=lambda *_: Upstream()))
    state = SimpleNamespace(files_service=files)
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "app": SimpleNamespace(state=state)})
    old_authorize = delivery.authorize
    delivery.authorize = lambda *_: dict(size_bytes=20, media_type="text/plain", filename="source.txt")
    try:
        with anyio.CancelScope() as scope:
            try:
                await delivery.deliver(request, "owner", "file", "binding")
            except RuntimeError:
                pass
        assert closed == ["provider", "lease"], closed
        assert slots.acquire(blocking=False), "Transfer slot leaked"
        slots.release()
    finally:
        delivery.authorize = old_authorize


async def main():
    await request_checks()
    await cleanup_check(False)
    await cleanup_check(True)
    print("Delivery failure integration: provider close failure and cancellation release lease/slot: passed")


if __name__ == "__main__":
    asyncio.run(main())
