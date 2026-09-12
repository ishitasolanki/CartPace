"""FastAPI entrypoint.

CORS is restricted to the Vite dev origin, per modular-plan.md section 4.6 --
"CORS restricted to the Vite dev origin in development and to nothing in
production." No wildcard.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from backend.db import init_db          # noqa: E402
from backend.routes import auth, config, runs, stats  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="CartPace", version="0.1.0", lifespan=lifespan)

_origin = os.environ.get("CORS_ORIGIN", "")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_origin] if _origin else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router)
app.include_router(config.router)
app.include_router(runs.router)
app.include_router(stats.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
