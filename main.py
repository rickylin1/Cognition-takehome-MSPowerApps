import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from core.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


# No /docs, /redoc or /openapi.json: every route except /login requires authentication.
app = FastAPI(
    title="Internal Tools", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
)
app.add_middleware(
    SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", "dev-only-insecure-secret")
)

# Each tool's routes are mounted here, e.g. app.include_router(kyc_router)
