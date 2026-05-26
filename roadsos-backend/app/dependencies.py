# dependencies.py — shared FastAPI dependencies
from fastapi import Depends
from sqlalchemy.orm import Session
from db.database import get_db

# Dependency helper type for routes
DbSession = Depends(get_db)
