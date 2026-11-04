import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from core import approvals, audit  # noqa: F401  (register models)
from core.auth import NotAuthenticated
from core.db import init_db
from core.permissions import PermissionDenied
from core.routes import router as core_router
from core.routes import templates


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


@app.exception_handler(NotAuthenticated)
def redirect_to_login(request: Request, exc: NotAuthenticated):
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(PermissionDenied)
def forbidden(request: Request, exc: PermissionDenied):
    user = getattr(request.state, "user", None)
    return templates.TemplateResponse(request, "forbidden.html", {"user": user}, status_code=403)


app.include_router(core_router)
# Each tool's routes are mounted here, e.g. app.include_router(kyc_router)
