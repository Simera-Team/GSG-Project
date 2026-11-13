from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

import app.infrastructure.persistence.models
from app.core.exceptions import PermissionDeniedError
from app.infrastructure.persistence.db.session import get_db
from app.presentation.routers.auth_router import router as auth_router
from app.presentation.routers.cv_router import router as cv_router
from app.presentation.routers.review_router import router as review_router
from app.presentation.routers.profile_router import router as profile_router
from app.presentation.routers.admin_router import router as admin_router


app = FastAPI(
    title="Simera API",
    description=(
        "CVerge - many sources, one profile. Upload CVs and LinkedIn exports; text is "
        "extracted (OCR for scans), fields are read with an LLM, checked against the "
        "source text, merged into one profile, and anything uncertain goes to a reviewer.\n\n"
        "**To try it here:** call `POST /api/v1/auth/login`, copy the `access_token`, "
        "click **Authorize**, paste the token, then call any endpoint."
    ),
    openapi_tags=[
        {"name": "Authentication", "description": "Register (candidates), log in, get a token"},
        {"name": "CV", "description": "Upload files and follow their processing (candidates)"},
        {"name": "Profile", "description": "The unified profile and its change history"},
        {"name": "Review", "description": "Human review queue (reviewers, administrators)"},
        {"name": "Admin", "description": "Dashboard, jobs, re-runs, staff accounts (administrators)"},
    ],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(cv_router, prefix="/api/v1")
app.include_router(review_router, prefix="/api/v1")
app.include_router(profile_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def root():
    # Opening the server address in a browser goes straight to Swagger.
    return RedirectResponse(url="/docs")


@app.exception_handler(PermissionDeniedError)
def permission_denied_handler(
    request: Request,
    exc: PermissionDeniedError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": str(exc)}
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    tables = db.execute(text(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
    )).scalar()
    countries = db.execute(text("SELECT count(*) FROM country")).scalar()
    return {"database": "connected", "tables": tables, "countries": countries}
