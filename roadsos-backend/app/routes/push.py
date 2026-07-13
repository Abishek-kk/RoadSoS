from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import APIRouter

from app.config import get_vapid_public_key
from app.dependencies import DbSession
from db import crud


router = APIRouter(prefix="/push", tags=["Push Notifications"])


class PushKeys(BaseModel):
    p256dh: str = Field(..., min_length=1)
    auth: str = Field(..., min_length=1)


class PushSubscriptionPayload(BaseModel):
    endpoint: str = Field(..., min_length=1)
    keys: PushKeys


@router.get("/vapid-public-key")
async def vapid_public_key():
    return {"publicKey": get_vapid_public_key()}


@router.post("/subscribe")
async def subscribe(payload: PushSubscriptionPayload, db: Session = DbSession):
    user = crud.get_or_create_system_user(db)
    subscription = crud.upsert_push_subscription(
        db,
        user.id,
        payload.endpoint,
        payload.keys.p256dh,
        payload.keys.auth,
    )
    return {"ok": True, "id": subscription.id}


@router.delete("/subscribe")
async def unsubscribe(payload: PushSubscriptionPayload, db: Session = DbSession):
    user = crud.get_or_create_system_user(db)
    deleted = crud.delete_push_subscription(db, user.id, payload.endpoint)
    return {"ok": True, "deleted": deleted}
