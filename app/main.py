import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import close, ensure_indexes
from app.realtime import ws
from app.realtime.hub import hub
from app.routers import admin, analytics, rooms

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("whiteboard")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    indexes = await ensure_indexes()
    log.info("instance %s ready with %d indexes", settings.instance_id, len(indexes))
    await hub.start()
    yield
    await hub.stop()
    await close()


app = FastAPI(
    title="Real-Time Collaborative Whiteboard",
    description=(
        "NoSQL Database course project (BCSE406L) — MongoDB document store for an "
        "append-only stroke log, Redis for ordering, presence, and cross-instance fanout."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(rooms.router)
app.include_router(analytics.router)
app.include_router(admin.router)
app.include_router(ws.router)

# The frontend is served from the same origin as the API so the demo never has to
# deal with CORS or WebSocket origin rejections.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def no_store_static(request, call_next):
    """Keep the browser from caching the frontend.

    Editing a JS or CSS file and reloading should show the change. Without this
    the browser serves a stale bundle and the page silently disagrees with the
    code on disk, which is a miserable thing to debug mid-demo.
    """
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-store, must-revalidate"
    return response


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")
