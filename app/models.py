from sqlalchemy import Column, String, Text, Boolean, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id           = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email        = Column(String, unique=True, index=True, nullable=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    # Quiz answers
    age          = Column(String, nullable=True)
    lifestyle    = Column(String, nullable=True)
    frustration  = Column(String, nullable=True)
    style        = Column(String, nullable=True)
    coloring     = Column(String, nullable=True)
    fit          = Column(String, nullable=True)
    climate      = Column(String, nullable=True)
    occasions    = Column(JSON, nullable=True)
    budget       = Column(String, nullable=True)

    # Capsule
    capsule_data = Column(JSON, nullable=True)
    capsule_at   = Column(DateTime(timezone=True), nullable=True)

    # Payment
    paid         = Column(Boolean, default=False)
    stripe_session_id = Column(String, nullable=True)
    paid_at      = Column(DateTime(timezone=True), nullable=True)

    # Email
    kit_synced   = Column(Boolean, default=False)
