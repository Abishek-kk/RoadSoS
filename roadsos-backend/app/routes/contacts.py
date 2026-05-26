from itertools import count

from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter(prefix="/contacts", tags=["Contacts"])

_ids = count(5)
_contacts: list[dict[str, str | None]] = [
    {"id": "1", "name": "Mom", "phone": "+919843947069", "relation": "Family"},
    {"id": "2", "name": "Dad", "phone": "+917305647064", "relation": "Family"},
    {"id": "3", "name": "Friend 1", "phone": "+919915625185", "relation": "Friend"},
    {"id": "4", "name": "Friend 2", "phone": "+916284170998", "relation": "Friend"},
]


class ContactPayload(BaseModel):
    name: str
    phone: str
    relation: str | None = None


@router.get("")
async def list_contacts():
    return _contacts


@router.post("")
async def add_contact(payload: ContactPayload):
    contact = {"id": str(next(_ids)), **payload.model_dump()}
    _contacts.append(contact)
    return contact
