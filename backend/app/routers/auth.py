
import random
import string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.security import (
    hash_password, verify_password, create_access_token, get_current_user
)
from backend.app.core.email import send_otp_email
from backend.app.models.user import User
from backend.app.models.notification import Notification, NotificationType
from backend.app.schemas.auth import (
    SignupRequest, LoginRequest, TokenResponse, UserOut,
    ForgotPasswordRequest, ResetPasswordRequest,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# In-memory OTP store keyed by EMAIL (not user_id) so it works before login.
# { "user@email.com": {"otp": "123456", "expires_at": datetime} }
# Replace with Redis for production multi-instance deployments.
_forgot_otp_store: dict = {}


#  Signup 

@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    """Register a new user account."""
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        full_name=payload.full_name,
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.flush()

    db.add(Notification(
        user_id=user.id,
        type=NotificationType.system,
        title="Welcome to Curio! 🎉",
        message=f"Hi {user.full_name}, your account is ready. Start by creating or taking a quiz!",
    ))
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


#  Login 

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with email + password (JSON body). Returns JWT + user object."""
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Please contact support.",
        )

    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


#  Me 

@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return current_user


#  Logout 

@router.post("/logout")
def logout():
    """Logout is handled client-side by discarding the JWT."""
    return {"message": "Logged out successfully"}


#  Forgot Password — Step 1: Send OTP 

@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Send a 6-digit OTP to the given email address.
    Works WITHOUT being logged in — used from the login page.

    Returns 200 even if the email isn't registered (to avoid user enumeration).
    The OTP is valid for 10 minutes.
    """
    email = payload.email.lower().strip()
    user  = db.query(User).filter(User.email == email).first()

    if not user:
        # Security: don't reveal whether the email is registered
        raise HTTPException(
            status_code=404,
            detail="No account found with this email address",
        )

    otp        = "".join(random.choices(string.digits, k=6))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    _forgot_otp_store[email] = {"otp": otp, "expires_at": expires_at, "user_id": user.id}

    try:
        send_otp_email(
            to_email  = user.email,
            full_name = user.full_name,
            otp       = otp,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to send OTP email. Check SMTP settings.",
        ) from exc

    return {"message": f"OTP sent to {email}. Valid for 10 minutes."}


#  Reset Password — Step 2: Verify OTP + Set New Password 

@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Verify OTP and set a new password.
    Works WITHOUT being logged in.
    """
    email  = payload.email.lower().strip()
    record = _forgot_otp_store.get(email)

    if not record:
        raise HTTPException(
            status_code=400,
            detail="No OTP found for this email. Please request a new code.",
        )

    if datetime.now(timezone.utc) > record["expires_at"]:
        _forgot_otp_store.pop(email, None)
        raise HTTPException(
            status_code=400,
            detail="OTP has expired. Please request a new code.",
        )

    if record["otp"] != payload.otp.strip():
        raise HTTPException(
            status_code=400,
            detail="Incorrect OTP. Please try again.",
        )

    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=422,
            detail="Passwords do not match",
        )

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    _forgot_otp_store.pop(email, None)

    return {"message": "Password reset successfully. You can now log in with your new password."}



























"""
backend/app/routers/auth.py

Signup always creates a STUDENT account.
Only an admin can promote a user to teacher/admin via the user-management API.
This prevents anyone from self-promoting to teacher by editing the request.
"""
import random, string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.security import hash_password, verify_password, create_access_token, get_current_user
from backend.app.core.email import send_otp_email
from backend.app.models.user import User, UserRole
from backend.app.models.notification import Notification, NotificationType
from backend.app.schemas.auth import (
    SignupRequest, LoginRequest, TokenResponse, UserOut,
    ForgotPasswordRequest, ResetPasswordRequest,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

_forgot_otp_store: dict = {}


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    """
    Register a new account.
    Role is ALWAYS student — admin promotes users via /api/admin/users/{id}/role.
    """
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = User(
        full_name=payload.full_name,
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        role=UserRole.student,   # always student on self-signup
    )
    db.add(user)
    db.flush()
    db.add(Notification(
        user_id=user.id,
        type=NotificationType.system,
        title="Welcome to Curio!",
        message=f"Hi {user.full_name}! Your student account is ready. You can take quizzes assigned to you.",
    ))
    db.commit()
    db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled. Contact support.")
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout")
def logout():
    return {"message": "Logged out successfully"}


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    user  = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="No account found with this email address")

    otp = "".join(random.choices(string.digits, k=6))
    _forgot_otp_store[email] = {
        "otp": otp,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
        "user_id": user.id,
    }
    try:
        send_otp_email(to_email=user.email, full_name=user.full_name, otp=otp)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to send OTP email. Check SMTP settings.") from exc

    return {"message": f"OTP sent to {email}. Valid for 10 minutes."}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    email  = payload.email.lower().strip()
    record = _forgot_otp_store.get(email)
    if not record:
        raise HTTPException(status_code=400, detail="No OTP found. Request a new code first.")
    if datetime.now(timezone.utc) > record["expires_at"]:
        _forgot_otp_store.pop(email, None)
        raise HTTPException(status_code=400, detail="OTP expired. Request a new code.")
    if record["otp"] != payload.otp.strip():
        raise HTTPException(status_code=400, detail="Incorrect OTP. Try again.")
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=422, detail="Passwords do not match")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    _forgot_otp_store.pop(email, None)
    return {"message": "Password reset successfully. You can now log in."}
