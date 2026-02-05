import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.database import async_session
from app.schemas.common import ApiResponse


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Register routers ---
from app.api import api_router  # noqa: E402
app.include_router(api_router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiResponse(
            success=False,
            message=exc.detail or "",
            statusCode=exc.status_code,
        ).model_dump(),
    )

@app.exception_handler(ValidationError)
async def pydantic_validation_handler(request: Request, exc: ValidationError):
    errors = exc.errors()
    custom_message = errors[0]["msg"] if errors else "Validation error"
    logging.warning(f"Validation errors: {errors}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ApiResponse(
            success=False,
            message=custom_message,
            statusCode=status.HTTP_422_UNPROCESSABLE_ENTITY,
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    details = []
    logging.warning(f"Validation errors: {errors}")
    for err in errors:
        loc = err.get("loc", ())
        msg = err.get("msg", "Validation error")
        # loc examples:
        # ('body', 'name')  -> normal field error
        # ('body',)         -> model-level error (your Option C)
        # ('query', 'page') -> query param error
        # ('path', 'id')    -> path param error

        field = loc[-1] if len(loc) > 1 else (loc[0] if len(loc) == 1 else "body")
        details.append({"field": str(field), "message": msg})

        logging.warning(f"Inside Validation error: {msg}")


    primary_message = details[0]["message"] if details else "Validation error"

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ApiResponse(
            success=False,
            message=primary_message,
            data={"details": details},
            statusCode=status.HTTP_422_UNPROCESSABLE_ENTITY,
        ).model_dump(),
    )


@app.get("/health", response_model=ApiResponse)
async def health_check():
    db_status = "ok"
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {str(e)}"

    status = "ok" if db_status == "ok" else "degraded"

    return ApiResponse(
        success=status == "ok",
        data={"status": status, "database": db_status},
    )