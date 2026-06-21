from __future__ import annotations

import argparse
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
import uvicorn
from fastapi import Depends, FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi

from panel.api.deps import get_current_user
from panel.api.middleware.security_headers import SecurityHeadersMiddleware
from panel.api.routers import auth, configs, health, metrics, share
from panel.config import PanelSettings, load_panel_settings
from panel.infrastructure.logging import configure_logging
from panel.infrastructure.observability.metrics import PrometheusMiddleware
from panel.infrastructure.persistence.database import create_engine, create_session_factory

logger = structlog.get_logger(__name__)


def create_app(settings: PanelSettings, *, with_db: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("api_starting", environment=settings.app.environment.value)
        if with_db:
            engine = create_engine(settings.database.url)
            app.state.engine = engine
            app.state.session_factory = create_session_factory(engine)
        yield
        if with_db:
            await app.state.engine.dispose()
        logger.info("api_stopped")

    app = FastAPI(
        title=settings.app.name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    if settings.security_headers.enabled:
        app.add_middleware(SecurityHeadersMiddleware, enabled=True)
    if settings.metrics.enabled:
        app.add_middleware(PrometheusMiddleware, enabled=True)
    app.include_router(health.router)
    if settings.metrics.enabled:
        app.include_router(metrics.router)
    app.include_router(auth.router)
    app.include_router(configs.router)
    app.include_router(share.public_router)
    app.include_router(share.admin_router)

    if not settings.app.max_secure:
        secured = [Depends(get_current_user)]

        @app.get("/docs", include_in_schema=False, dependencies=secured)
        async def swagger_ui() -> object:
            return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{settings.app.name} docs")

        @app.get("/redoc", include_in_schema=False, dependencies=secured)
        async def redoc_ui() -> object:
            return get_redoc_html(openapi_url="/openapi.json", title=f"{settings.app.name} docs")

        @app.get("/openapi.json", include_in_schema=False, dependencies=secured)
        async def openapi() -> dict:
            return get_openapi(
                title=settings.app.name,
                version="0.1.0",
                routes=app.routes,
            )

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the VPN Control Panel API")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to panel.yaml (default: ./panel.yaml or PANEL_CONFIG_PATH)",
    )
    args = parser.parse_args()

    settings = load_panel_settings(args.config)
    configure_logging("DEBUG" if settings.app.environment.value == "development" else "INFO")

    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.server.host,
        port=settings.server.port,
    )


if __name__ == "__main__":
    main()
