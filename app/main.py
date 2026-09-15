from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router

app = FastAPI(title="Hitbot Welding Dashboard", version="1.0.0")
app.include_router(api_router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.exception_handler(Exception)
async def json_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return JSON (not Starlette's plain-text 500) for any unhandled error so
    the dashboard's fetch().json() always has something valid to render."""
    return JSONResponse(status_code=500, content={"error": f"{type(exc).__name__}: {exc}"})


@app.get("/")
def read_root() -> FileResponse:
    return FileResponse("app/static/index.html")
