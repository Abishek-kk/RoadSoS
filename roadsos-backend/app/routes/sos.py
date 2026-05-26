from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.dependencies import DbSession
from app.models.sos import SOSCreate
from app.services.sos_service import trigger_sos_workflow


router = APIRouter(prefix="/sos", tags=["SOS"])


@router.post("")
async def trigger_sos(payload: SOSCreate, db: Session = DbSession):
    return trigger_sos_workflow(db, payload)

