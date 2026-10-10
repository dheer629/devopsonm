"""DevOpsSentinel Web -- FastAPI application.

Read-only guarantee: this process never mutates Kubernetes. The only
cluster-touching code paths are (a) the DevOpsSentinel engine invoked through
an allowlisted operation id and (b) two narrowly-scoped read-only kubectl
discovery calls. Two additional, operator-opt-in features talk to a database
and a Kafka broker directly (see ``api/live.py``); both are disabled by default.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import (
    connections,
    gitops,
    graph,
    inspect,
    live,
    network,
    operations,
    pki,
    sse,
    storage,
    system,
    workloads,
)
from .config import API_SCHEMA_VERSION, SUPERVISION_MODE, WEB_VERSION, settings
from .security import origin_allowed

logger = logging.getLogger("devopssentinel.web")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; font-src 'self' data:; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    ),
}

STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "DevOpsSentinel Web %s starting (mode=%s, engine=%s, available=%s)",
        WEB_VERSION,
        SUPERVISION_MODE,
        settings.engine_path,
        settings.engine_available(),
    )
    task: asyncio.Task[None] | None = None
    if settings.autoconnect:
        task = asyncio.create_task(_autoconnect())
    yield
    if task is not None and not task.done():
        task.cancel()
    logger.info("DevOpsSentinel Web shutting down")


async def _autoconnect() -> None:
    """Connect to a reachable cluster in the background at startup.

    Runs off the request path, so a slow probe never delays the first page, and
    never overrides a connection that already works. This exists because a
    console that opens with no cluster looks broken: the operator should not have
    to find Settings before any data appears. The Docker/WSL case in particular
    is not solvable from the kubeconfig alone -- a vcluster names a host
    port-forward that does not resolve inside a container -- so the endpoint
    discovery in ``auto_connect`` does the work.
    """
    from .services import connections

    try:
        health = await asyncio.to_thread(connections.check_active)
        if health.get("reachable"):
            logger.info(
                "cluster connection is already healthy (%s at %s)",
                health.get("context"),
                health.get("server"),
            )
            return
        if health.get("configured"):
            logger.info(
                "active connection %s is not reachable (%s); reconnecting",
                health.get("server"),
                health.get("reason") or "unknown",
            )
        report = await asyncio.to_thread(connections.auto_connect)
        activated = report.get("activated")
        if activated:
            logger.info(
                "auto-connected to %s at %s (detected via %s)",
                activated.get("context"),
                report.get("serverOverride") or activated.get("server"),
                (report.get("detected") or {}).get("source") or "kubeconfig",
            )
        else:
            logger.info(
                "auto-connect found no reachable cluster (%s)", report.get("reason")
            )
    except asyncio.CancelledError:  # pragma: no cover - shutdown
        raise
    except Exception:  # noqa: BLE001 - startup must never fail on this
        logger.warning("auto-connect failed", exc_info=True)


def create_app() -> FastAPI:
    app = FastAPI(
        title="DevOpsSentinel Web API",
        version=WEB_VERSION,
        description="Local read-only Kubernetes / GitOps / PKI / application profile control center.",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
        max_age=600,
    )

    @app.middleware("http")
    async def guard(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method in STATE_CHANGING and not origin_allowed(origin, settings.allowed_origins):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "origin not allowed",
                    "origin": origin,
                    # A page served on a port the backend does not trust fails
                    # every state-changing request while every read succeeds, so
                    # say what *is* trusted instead of only what was rejected.
                    "allowed": list(settings.allowed_origins),
                    "hint": (
                        "the page must be served from one of the allowed origins; "
                        "set DSWEB_ALLOWED_ORIGINS to add another"
                    ),
                },
            )
        if request.method in STATE_CHANGING:
            length = request.headers.get("content-length")
            if length and int(length) > 2_000_000:
                return JSONResponse(status_code=413, content={"detail": "request too large"})
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response

    for module in (
        connections,
        system,
        workloads,
        graph,
        gitops,
        pki,
        network,
        storage,
        operations,
        inspect,
        sse,
        live,
    ):
        app.include_router(module.router)

    @app.get("/api/v1/version", tags=["system"])
    async def version() -> dict:
        return {
            "webVersion": WEB_VERSION,
            "apiSchema": API_SCHEMA_VERSION,
            "mode": SUPERVISION_MODE,
        }

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    dist: Path = settings.frontend_dist
    if not dist.is_dir():
        @app.get("/", response_model=None)
        async def no_frontend() -> JSONResponse:
            return JSONResponse(
                {
                    "detail": "frontend build not found",
                    "hint": "run ./scripts/build.sh (or pnpm build in frontend/)",
                    "apiDocs": "/api/docs",
                }
            )
        return

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    index = dist / "index.html"

    @app.get("/", response_model=None)
    async def index_root() -> FileResponse:
        return FileResponse(index)

    @app.get("/{full_path:path}", response_model=None)
    async def spa(full_path: str) -> FileResponse | JSONResponse:
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "not found"})
        candidate = dist / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()


def run() -> None:  # pragma: no cover - process entrypoint
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level="debug" if settings.debug else "info",
    )


if __name__ == "__main__":  # pragma: no cover
    run()
