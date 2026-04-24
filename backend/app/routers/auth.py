



import random
import string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.email import send_otp_email
from backend.app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from backend.app.models.notification import Notification, NotificationType
from backend.app.models.user import User, UserRole
from backend.app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
    UserOut,
)

router = APIRouter()

# In-memory OTP store for the public forgot-password flow.
# { email: {"otp": "123456", "expires_at": datetime, "user_id": int} }
# Replace with Redis for production multi-instance deployments.
_forgot_otp_store: dict = {}


# ── Signup ────────────────────────────────────────────────────────────────────

@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account (always as student)",
)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        full_name=payload.full_name,
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        role=UserRole.student,
    )
    db.add(user)
    db.flush()

    db.add(Notification(
        user_id=user.id,
        type=NotificationType.system,
        title="Welcome to Curio!",
        message=(
            f"Hi {user.full_name}! Your student account is ready. "
            "Quizzes assigned to you will appear in My Quizzes."
        ),
    ))

    db.commit()
    db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse, summary="Login and receive JWT")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Contact support.",
        )
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


# ── Me ────────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserOut, summary="Get current user info")
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


# ── Logout ────────────────────────────────────────────────────────────────────

@router.post("/logout", summary="Logout (client must discard token)")
def logout():
    return {"message": "Logged out successfully."}


# ── Forgot password — Step 1: send OTP ───────────────────────────────────────

@router.post("/forgot-password", summary="Send OTP to registered email")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Public endpoint — no authentication token required.
    Validates SMTP config before attempting to send so the frontend
    receives a clear 503 with a helpful message instead of a generic 500.
    """
    email = payload.email.lower().strip()

    # Validate SMTP is configured before hitting the database or generating an OTP
    if not settings.SMTP_USER or settings.SMTP_USER in ("your@gmail.com", ""):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Email service is not configured. "
                "SMTP_USER is missing or still set to the placeholder value. "
                "Please update SMTP_USER and SMTP_PASS in your .env file "
                "and restart the backend container."
            ),
        )
    if not settings.SMTP_PASS or settings.SMTP_PASS in ("your_app_password_here", ""):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Email service is not configured. "
                "SMTP_PASS is missing or still set to the placeholder value. "
                "Generate a Gmail App Password at "
                "myaccount.google.com → Security → App Passwords "
                "and add it to your .env file."
            ),
        )

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found with this email address.",
        )

    otp = "".join(random.choices(string.digits, k=6))
    _forgot_otp_store[email] = {
        "otp":        otp,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
        "user_id":    user.id,
    }

    try:
        send_otp_email(to_email=user.email, full_name=user.full_name, otp=otp)
    except Exception as exc:
        # Clean up so a stale OTP can't be used
        _forgot_otp_store.pop(email, None)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Failed to send verification email. "
                "Please check that your Gmail App Password is correct "
                "(generate at myaccount.google.com → Security → App Passwords) "
                "and that SMTP_USER / SMTP_PASS in your .env file are up to date. "
                "Then restart the backend container."
            ),
        ) from exc

    return {"message": f"OTP sent to {email}. Valid for 10 minutes."}


# ── Forgot password — Step 2: verify OTP + set new password ──────────────────

@router.post("/reset-password", summary="Verify OTP and set new password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    email  = payload.email.lower().strip()
    record = _forgot_otp_store.get(email)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No OTP found for this email. Please request a new code.",
        )

    if datetime.now(timezone.utc) > record["expires_at"]:
        _forgot_otp_store.pop(email, None)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Please request a new code.",
        )

    if record["otp"] != payload.otp.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect OTP. Please try again.",
        )

    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Passwords do not match.",
        )

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    _forgot_otp_store.pop(email, None)
    return {"message": "Password reset successfully. You can now log in."}
