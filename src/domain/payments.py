import json
import uuid
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session
import stripe

from app.core.auth import get_current_user, get_current_user_id
from app.core.config import settings
from app.db.dependencies import get_db
from app.domain.model import MemoirProject, Order, User
from app.domain.schemas import (
    CheckoutSummaryOut,
    OrderCreate,
    OrderOut,
    PaymentConfirmRequest,
    PaymentIntentCreate,
    PaymentIntentOut,
)

router = APIRouter(tags=["Checkout & Payments"])


@router.get("/projects/{project_id}/checkout-summary", response_model=CheckoutSummaryOut)
def get_checkout_summary(
    project_id: UUID,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    GET /projects/:id/checkout-summary — Returns project title, relationship focus,
    est. pages/interview time, and MVP flat-rate price ($299.00).
    """
    project = db.query(MemoirProject).filter(
        MemoirProject.id == project_id,
        MemoirProject.owner_id == user_id,
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    price = float(settings.FLAT_RATE_PRICE_USD)
    title = project.subject_name or "The Golden Years: A Family Tapestry"
    relationship = project.relationship_to_subject or "Family"

    return CheckoutSummaryOut(
        project_id=project.id,
        project_title=title,
        relationship_focus=relationship,
        estimated_length="50-75 Pages",
        interview_time="2-3 hours",
        subtotal=price,
        tax=0.0,
        total_due=price,
        currency="usd",
    )


@router.post("/payments/create-intent", response_model=PaymentIntentOut)
def create_payment_intent(
    payload: PaymentIntentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a Stripe PaymentIntent for the project with flat MVP rate ($299.00).
    """
    project = db.query(MemoirProject).filter(
        MemoirProject.id == payload.project_id,
        MemoirProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    amount_cents = int(settings.FLAT_RATE_PRICE_USD * 100)

    if settings.STRIPE_SECRET_KEY:
        try:
            stripe.api_key = settings.STRIPE_SECRET_KEY
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency="usd",
                metadata={
                    "project_id": str(project.id),
                    "user_id": str(current_user.id),
                    "user_email": current_user.email,
                },
                automatic_payment_methods={"enabled": True},
            )
            return PaymentIntentOut(
                client_secret=intent.client_secret,
                payment_intent_id=intent.id,
                amount=amount_cents,
                currency="usd",
                publishable_key=settings.STRIPE_PUBLISHABLE_KEY,
                status=intent.status,
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Stripe PaymentIntent creation failed: {str(e)}",
            )

    # Mock mode for testing / development without live Stripe credentials
    mock_id = f"pi_mock_{uuid.uuid4().hex[:16]}"
    mock_secret = f"{mock_id}_secret_{uuid.uuid4().hex[:16]}"
    return PaymentIntentOut(
        client_secret=mock_secret,
        payment_intent_id=mock_id,
        amount=amount_cents,
        currency="usd",
        publishable_key=settings.STRIPE_PUBLISHABLE_KEY,
        status="requires_payment_method",
    )


@router.post("/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def record_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    POST /orders — Record order on successful payment.
    """
    project = db.query(MemoirProject).filter(
        MemoirProject.id == payload.project_id,
        MemoirProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    amount_cents = int(settings.FLAT_RATE_PRICE_USD * 100)

    # Check if order already recorded for this payment intent
    if payload.payment_intent_id:
        existing_order = db.query(Order).filter(
            Order.stripe_payment_intent_id == payload.payment_intent_id
        ).first()
        if existing_order:
            return existing_order

    order = Order(
        user_id=current_user.id,
        project_id=project.id,
        stripe_payment_intent_id=payload.payment_intent_id,
        amount=amount_cents,
        currency="usd",
        status="completed",
        customer_email=current_user.email,
        customer_name=current_user.full_name,
        billing_details=payload.billing_details,
    )
    db.add(order)
    project.is_paid = True

    db.commit()
    db.refresh(order)
    return order


@router.get("/orders", response_model=List[OrderOut])
def list_orders(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    List all orders for the current user.
    """
    return db.query(Order).filter(Order.user_id == user_id).order_by(Order.created_at.desc()).all()


@router.get("/orders/{order_id}", response_model=OrderOut)
def get_order(
    order_id: UUID,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    Get details of a specific order.
    """
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    return order


@router.post("/payments/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    """
    Stripe webhook endpoint to confirm payment server-side (do not trust client alone).
    Verifies signature and processes payment_intent.succeeded and payment_intent.payment_failed.
    """
    body = await request.body()

    event = None
    if settings.STRIPE_WEBHOOK_SECRET and stripe_signature:
        try:
            event = stripe.Webhook.construct_event(
                payload=body,
                sig_header=stripe_signature,
                secret=settings.STRIPE_WEBHOOK_SECRET,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Webhook signature verification failed: {str(e)}")
    else:
        # Parse JSON directly if webhook secret is not set (e.g. testing)
        try:
            event = json.loads(body.decode("utf-8"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    event_type = event.get("type") if isinstance(event, dict) else getattr(event, "type", "")
    event_data = event.get("data", {}).get("object", {}) if isinstance(event, dict) else getattr(event, "data", {}).get("object", {})

    if event_type == "payment_intent.succeeded":
        payment_intent_id = event_data.get("id")
        amount = event_data.get("amount", int(settings.FLAT_RATE_PRICE_USD * 100))
        currency = event_data.get("currency", "usd")
        metadata = event_data.get("metadata", {})
        project_id_str = metadata.get("project_id")
        user_id_str = metadata.get("user_id")

        if project_id_str:
            try:
                project_id = UUID(project_id_str)
                project = db.query(MemoirProject).filter(MemoirProject.id == project_id).first()
                if project:
                    project.is_paid = True

                    # Upsert order
                    order = db.query(Order).filter(
                        Order.stripe_payment_intent_id == payment_intent_id
                    ).first()
                    if not order:
                        user_id = int(user_id_str) if user_id_str else project.owner_id
                        order = Order(
                            user_id=user_id,
                            project_id=project.id,
                            stripe_payment_intent_id=payment_intent_id,
                            amount=amount,
                            currency=currency,
                            status="completed",
                            customer_email=metadata.get("user_email"),
                        )
                        db.add(order)
                    else:
                        order.status = "completed"

                    db.commit()
            except Exception as e:
                db.rollback()
                print(f"Error updating project order from webhook: {e}")

    elif event_type == "payment_intent.payment_failed":
        payment_intent_id = event_data.get("id")
        order = db.query(Order).filter(
            Order.stripe_payment_intent_id == payment_intent_id
        ).first()
        if order:
            order.status = "failed"
            db.commit()

    return {"status": "success", "event_type": event_type}
