from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import text

from .auth import router as auth_router
from .db import get_engine
from .quizzes import router as quizzes_router
from .rooms import router as rooms_router

app = FastAPI(title="BrainBlitz API")
app.include_router(auth_router)
app.include_router(quizzes_router)
app.include_router(rooms_router)


@app.get("/health")
def health():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="database connection failed")
    return {"status": "ok", "database": "ok"}


# The static pages live at the repo root. Serve only top-level .html/.css/.js files,
# so nothing under backend/ (like .env) is ever reachable. Registered last so every
# API route wins over a same-named file.
FRONTEND_DIR = Path(__file__).resolve().parents[2]
FRONTEND_SUFFIXES = {".html", ".css", ".js"}


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/{name}", include_in_schema=False)
def frontend_file(name: str):
    path = FRONTEND_DIR / name
    if path.suffix not in FRONTEND_SUFFIXES or not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path)
