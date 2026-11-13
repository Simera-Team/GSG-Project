from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

import app.infrastructure.persistence.models
from app.core.exceptions import PermissionDeniedError
from app.infrastructure.persistence.db.session import get_db
from app.presentation.routers.auth_router import router as auth_router
from app.presentation.routers.cv_router import router as cv_router


app = FastAPI(title="Simera API")

app.include_router(auth_router, prefix="/api/v1")
app.include_router(cv_router, prefix="/api/v1")


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
