

import os
import uuid
import random
import string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, verify_password, hash_password
from backend.app.core.email import send_otp_email
from backend.app.core.config import settings
from backend.app.models.user import User
from backend.app.schemas.misc import (
    UserProfileOut,
    UserProfileUpdate,
    PasswordChangeRequest,
    PasswordResetVerify,
    NotificationPrefsUpdate,
)

router = APIRouter()

# In-memory OTP store { user_id: {"otp": "123456", "expires_at": datetime} }
# Replace with Redis for production multi-instance deployments.
_otp_store: dict = {}

# Avatar upload directory — relative to uvicorn working dir (/app in Docker)
UPLOAD_DIR = os.path.join("static", "avatars")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ── Profile ───────────────────────────────────────────────────────────────────

@router.get("/profile", response_model=UserProfileOut)
def get_profile(current_user: User = Depends(get_current_user)):
    """Return the current user's full profile."""
    return current_user


@router.patch("/profile", response_model=UserProfileOut)
def update_profile(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update full_name, dark_mode, display_language.
    Email cannot be changed after registration.
    """
    if payload.full_name is not None:
        name = payload.full_name.strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Full name cannot be empty.",
            )
        current_user.full_name = name

    if payload.dark_mode is not None:
        current_user.dark_mode = payload.dark_mode

    if payload.display_language is not None:
        allowed_langs = {"English", "Hindi", "Spanish", "French", "German", "Japanese"}
        if payload.display_language not in allowed_langs:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid language. Allowed: {', '.join(sorted(allowed_langs))}",
            )
        current_user.display_language = payload.display_language

    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/profile/avatar", response_model=UserProfileOut)
async def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a profile picture (PNG or JPG, max 5 MB).
    Returns the updated user profile including the new profile_picture URL.
    """
    allowed_types = {"image/jpeg", "image/jpg", "image/png"}
    # Some browsers send "image/jpg" instead of "image/jpeg"
    content_type = (file.content_type or "").lower()
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only PNG or JPG/JPEG files are allowed.",
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty.",
        )
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum size is 5 MB.",
        )

    # Delete the old avatar file if it exists
    if current_user.profile_picture:
        old_path = current_user.profile_picture.lstrip("/")
        if os.path.isfile(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass  # Non-critical — old file stays, new one is still saved

    ext       = "png" if content_type == "image/png" else "jpg"
    filename  = f"{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(UPLOAD_DIR, filename)

    try:
        with open(save_path, "wb") as f:
            f.write(contents)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save the uploaded file. Please try again.",
        ) from exc

    current_user.profile_picture = f"/static/avatars/{filename}"
    db.commit()
    db.refresh(current_user)
    return current_user


# ── Security — OTP-based password change ─────────────────────────────────────

@router.post("/security/request-otp")
def request_otp(current_user: User = Depends(get_current_user)):
    """
    Step 1: Generate a 6-digit OTP, store it in memory, and email it.
    Valid for 10 minutes.

    Returns a clear error if SMTP is not configured, rather than a generic
    "server error", so the frontend can show a helpful message.
    """
    # Validate SMTP is configured before generating an OTP
    if not settings.SMTP_USER or settings.SMTP_USER in ("your@gmail.com", ""):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Email service is not configured. "
                "Please set SMTP_USER and SMTP_PASS in your environment or .env file. "
                "You can use the 'Change Password' option below instead."
            ),
        )
    if not settings.SMTP_PASS or settings.SMTP_PASS in ("your_app_password_here", ""):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Email service is not configured. "
                "SMTP_PASS is missing or still set to the placeholder value. "
                "You can use the 'Change Password' option below instead."
            ),
        )

    otp        = "".join(random.choices(string.digits, k=6))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    _otp_store[current_user.id] = {"otp": otp, "expires_at": expires_at}

    try:
        send_otp_email(
            to_email  = current_user.email,
            full_name = current_user.full_name,
            otp       = otp,
        )
    except Exception as exc:
        # Clean up the OTP — user will need to retry anyway
        _otp_store.pop(current_user.id, None)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Failed to send verification email. "
                "Please check your SMTP credentials in docker-compose.yml "
                "and make sure you are using a Gmail App Password "
                "(not your regular Gmail password). "
                "Alternatively, use the 'Change Password' section below."
            ),
        ) from exc

    return {
        "message": f"Verification code sent to {current_user.email}. Valid for 10 minutes."
    }


@router.post("/security/verify-otp")
def verify_otp(
    payload: PasswordResetVerify,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Step 2: Verify the OTP and set the new password.
    The OTP and new password are verified in a single call.
    """
    record = _otp_store.get(current_user.id)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No verification code found. Please request a new code first.",
        )

    if datetime.now(timezone.utc) > record["expires_at"]:
        _otp_store.pop(current_user.id, None)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has expired. Please request a new code.",
        )

    if record["otp"] != payload.otp.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect verification code. Please try again.",
        )

    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Passwords do not match.",
        )

    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    _otp_store.pop(current_user.id, None)
    return {"message": "Password changed successfully."}


@router.post("/security/change-password")
def change_password(
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Direct password change — requires the current password.
    No OTP or email needed. Use this when SMTP is not configured.
    """
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    if payload.new_password == payload.current_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="New password must be different from the current password.",
        )
    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Passwords do not match.",
        )

    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return {"message": "Password updated successfully."}


# ── Notification preferences ──────────────────────────────────────────────────

@router.patch("/notifications", response_model=UserProfileOut)
def update_notification_prefs(
    payload: NotificationPrefsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toggle email_digests and/or push_alerts preferences."""
    if payload.email_digests is not None:
        current_user.email_digests = payload.email_digests
    if payload.push_alerts is not None:
        current_user.push_alerts = payload.push_alerts
    db.commit()
    db.refresh(current_user)
    return current_user
