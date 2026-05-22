from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from datetime import datetime
import os
import stripe
import httpx

from .database import engine, get_db
from .models import Base, User
from .schemas import EmailCapture, QuizSubmit, PaymentConfirm, UserResponse

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Ease & Aura API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://easeandaura.com",
        "https://www.easeandaura.com",
        "http://localhost:3000",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "price_1TZgYzPT8zsJs3qkDDGwMhiA")

# Kit (ConvertKit)
KIT_API_KEY = os.getenv("KIT_API_KEY")
KIT_FORM_ID = os.getenv("KIT_FORM_ID")


# ── HEALTH ──────────────────────────────────────────────────────────────────
@app.get("/")
def health():
    return {"status": "Ease & Aura API is live"}


# ── EMAIL CAPTURE ────────────────────────────────────────────────────────────
@app.post("/capture-email")
def capture_email(data: EmailCapture, db: Session = Depends(get_db)):
    """Capture email at start of quiz — before payment."""
    user = db.query(User).filter(User.email == data.email.lower()).first()
    if not user:
        user = User(email=data.email.lower())
        db.add(user)
        db.commit()
        db.refresh(user)
    return {"success": True, "email": user.email, "paid": user.paid}


# ── SAVE QUIZ + CAPSULE ──────────────────────────────────────────────────────
@app.post("/save-quiz")
def save_quiz(data: QuizSubmit, db: Session = Depends(get_db)):
    """Save quiz answers and capsule data after AI generates it."""
    user = db.query(User).filter(User.email == data.email.lower()).first()
    if not user:
        user = User(email=data.email.lower())
        db.add(user)

    user.age         = data.age
    user.lifestyle   = data.lifestyle
    user.frustration = data.frustration
    user.style       = data.style
    user.coloring    = data.coloring
    user.fit         = data.fit
    user.climate     = data.climate
    user.occasions   = data.occasions
    user.budget      = data.budget

    if data.capsule_data:
        user.capsule_data = data.capsule_data
        user.capsule_at   = datetime.utcnow()

    db.commit()
    db.refresh(user)
    return {"success": True}


# ── CREATE STRIPE CHECKOUT SESSION ──────────────────────────────────────────
@app.post("/create-checkout")
def create_checkout(data: EmailCapture, db: Session = Depends(get_db)):
    """Create a Stripe Checkout session for the user."""
    user = db.query(User).filter(User.email == data.email.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="Email not found. Please start the quiz first.")

    if user.paid:
        return {"already_paid": True}

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            mode="payment",
            customer_email=user.email,
            success_url=f"https://easeandaura.com/app.html?unlocked=true&email={user.email}",
            cancel_url="https://easeandaura.com/app.html?cancelled=true",
            metadata={"email": user.email},
        )
        user.stripe_session_id = session.id
        db.commit()
        return {"checkout_url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── STRIPE WEBHOOK ───────────────────────────────────────────────────────────
@app.post("/webhook/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Stripe payment confirmation webhook."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        email = session.get("metadata", {}).get("email") or session.get("customer_email")

        if email:
            user = db.query(User).filter(User.email == email.lower()).first()
            if user:
                user.paid = True
                user.paid_at = datetime.utcnow()
                user.stripe_session_id = session["id"]
                db.commit()

                # Sync to Kit
                if KIT_API_KEY and KIT_FORM_ID and not user.kit_synced:
                    await sync_to_kit(user)
                    user.kit_synced = True
                    db.commit()

    return {"received": True}


# ── GET USER (for returning users) ───────────────────────────────────────────
@app.get("/user/{email}")
def get_user(email: str, db: Session = Depends(get_db)):
    """Retrieve user data — capsule, payment status, profile."""
    user = db.query(User).filter(User.email == email.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "email": user.email,
        "paid": user.paid,
        "capsule_data": user.capsule_data if user.paid else None,
        "style": user.style,
        "age": user.age,
    }


# ── KIT SYNC ─────────────────────────────────────────────────────────────────
async def sync_to_kit(user: User):
    """Add subscriber to Kit with style profile tags."""
    if not KIT_API_KEY or not KIT_FORM_ID:
        return

    tags = []
    if user.age:       tags.append(f"age_{user.age.replace('+','plus').replace('–','-').replace(' ','_').lower()}")
    if user.style:     tags.append(f"style_{user.style.replace(' ','_').replace('&','and').lower()}")
    if user.climate:   tags.append(f"climate_{user.climate.replace(' ','_').replace('&','and').lower()}")
    if user.lifestyle: tags.append(f"lifestyle_{user.lifestyle.replace(' ','_').replace('&','and').lower()}")

    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.convertkit.com/v3/forms/{KIT_FORM_ID}/subscribe",
            json={
                "api_key": KIT_API_KEY,
                "email": user.email,
                "tags": tags,
                "fields": {
                    "style":      user.style or "",
                    "age":        user.age or "",
                    "climate":    user.climate or "",
                    "lifestyle":  user.lifestyle or "",
                    "frustration": user.frustration or "",
                }
            }
        )


# ── ADMIN: basic stats ────────────────────────────────────────────────────────
@app.get("/admin/stats")
def stats(db: Session = Depends(get_db)):
    """Quick stats — total leads, paid, conversion rate."""
    total  = db.query(User).count()
    paid   = db.query(User).filter(User.paid == True).count()
    unpaid = total - paid
    rate   = round((paid / total * 100), 1) if total > 0 else 0
    return {
        "total_leads":    total,
        "paid_customers": paid,
        "unpaid_leads":   unpaid,
        "conversion_rate": f"{rate}%",
    }
