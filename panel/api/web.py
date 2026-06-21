from __future__ import annotations

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

from panel.config import PanelSettings
from panel.web import WEB_ROOT


def setup_web_ui(app: FastAPI, settings: PanelSettings) -> None:
    if not settings.web.enabled:
        return

    prefix = settings.web.mount_path.rstrip("/") or "/admin"
    static_dir = WEB_ROOT / "static"
    index_file = WEB_ROOT / "index.html"

    if not index_file.is_file():
        raise RuntimeError(f"Web UI index not found: {index_file}")

    app.mount(
        f"{prefix}/static",
        StaticFiles(directory=static_dir),
        name="web-static",
    )

    @app.get(prefix, include_in_schema=False)
    @app.get(f"{prefix}/{{full_path:path}}", include_in_schema=False)
    async def admin_ui(full_path: str = "") -> FileResponse:
        if full_path.startswith("static/"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return FileResponse(index_file, media_type="text/html; charset=utf-8")
