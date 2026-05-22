from pydantic import BaseModel, EmailStr
from typing import Optional, List, Any
from datetime import datetime

class EmailCapture(BaseModel):
    email: str

class QuizSubmit(BaseModel):
    email: str
    age: Optional[str] = None
    lifestyle: Optional[str] = None
    frustration: Optional[str] = None
    style: Optional[str] = None
    coloring: Optional[str] = None
    fit: Optional[str] = None
    climate: Optional[str] = None
    occasions: Optional[List[str]] = None
    budget: Optional[str] = None
    capsule_data: Optional[Any] = None

class PaymentConfirm(BaseModel):
    email: str
    stripe_session_id: str

class UserResponse(BaseModel):
    email: str
    paid: bool
    capsule_data: Optional[Any] = None
    age: Optional[str] = None
    style: Optional[str] = None

    class Config:
        from_attributes = True
