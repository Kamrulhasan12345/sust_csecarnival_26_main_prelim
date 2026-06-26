from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.models.request import TicketRequest
from app.models.response import TicketResponse
from app.services.investigator import investigate

router = APIRouter()


@router.post("/analyze-ticket", response_model=TicketResponse)
async def analyze_ticket(req: TicketRequest):
    if not req.complaint or not req.complaint.strip():
        raise HTTPException(status_code=422, detail="complaint field must not be empty")
    try:
        return investigate(req)
    except Exception:
        return JSONResponse(
            status_code=500,
            content={"error": "internal error"},
        )
