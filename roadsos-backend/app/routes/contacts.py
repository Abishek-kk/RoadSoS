from fastapi import APIRouter
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.dependencies import DbSession
from app.models import user as user_schema
from db import crud


router = APIRouter(prefix="/contacts", tags=["Contacts"])


class ContactPayload(BaseModel):
    name: str
    phone: str
    relation: str | None = None
    notify_whatsapp: bool | None = True
    notify_sms: bool | None = True
    notify_call: bool | None = False


def _format_contact(contact: crud.models.EmergencyContact) -> dict[str, str | int | bool | None]:
    return {
        "id": str(contact.id),
        "name": contact.name,
        "phone": contact.phone,
        "relation": contact.relation,
        "notify_whatsapp": contact.notify_whatsapp,
        "notify_sms": contact.notify_sms,
        "notify_call": contact.notify_call,
    }


@router.get("")
async def list_contacts(db: Session = DbSession):
    user = crud.get_or_create_system_user(db)
    contacts = crud.get_emergency_contacts(db, user.id)
    return [_format_contact(contact) for contact in contacts]


@router.post("")
async def add_contact(payload: ContactPayload, db: Session = DbSession):
    user = crud.get_or_create_system_user(db)
    contact_payload = user_schema.ContactCreate(**payload.model_dump())
    contact = crud.create_emergency_contact(db, contact_payload, user.id)
    return _format_contact(contact)
