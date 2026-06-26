from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.routers import health, analyze

app = FastAPI(
    title="QueueStorm Investigator",
    description="AI/API SupportOps service for digital finance ticket investigation.",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(analyze.router)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": "internal error"})
