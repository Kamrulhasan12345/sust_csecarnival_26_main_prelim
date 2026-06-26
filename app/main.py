# Load .env (if present) BEFORE importing routers, so llm_client picks up keys.
# In deployment, platform-injected env vars already exist and take precedence
# (load_dotenv does not override existing environment variables).
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routers import health, analyze

app = FastAPI(
    title="QueueStorm Investigator",
    description="AI/API SupportOps service for digital finance ticket investigation.",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(analyze.router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Spec 4.1: malformed input (invalid JSON, missing required fields, wrong
    # types) -> 400 with a non-sensitive error message.
    return JSONResponse(
        status_code=400,
        content={"error": "malformed request: invalid or missing required fields"},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": "internal error"})
