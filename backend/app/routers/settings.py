
import os
import uuid
import random
import string

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, verify_password, hash_password
from backend.app.core.email import send_otp_email
from backend.app.models.user import User
from backend.app.schemas.misc import (
    UserProfileOut, UserProfileUpdate,
    PasswordChangeRequest, PasswordResetVerify,
    NotificationPrefsUpdate,
)

router = APIRouter(prefix="/api/settings", tags=["Settings"])

# In-memory OTP store  { user_id: {"otp": "123456", "expires_at": datetime} }
# For production replace with Redis.
_otp_store: dict = {}

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
    Update name, dark_mode, display_language.
    Email is intentionally excluded — cannot be changed after registration.
    """
    if payload.full_name is not None:
        name = payload.full_name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Full name cannot be empty")
        current_user.full_name = name

    if payload.dark_mode is not None:
        current_user.dark_mode = payload.dark_mode

    if payload.display_language is not None:
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
    """Upload a profile picture (PNG or JPG, max 5 MB)."""
    allowed = {"image/jpeg", "image/jpg", "image/png"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=422, detail="Only PNG or JPG files are allowed")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 5 MB")

    # Delete previous avatar
    if current_user.profile_picture:
        old_path = current_user.profile_picture.lstrip("/")
        if os.path.isfile(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass

    ext      = "png" if file.content_type == "image/png" else "jpg"
    filename = f"{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(UPLOAD_DIR, filename)

    with open(save_path, "wb") as f:
        f.write(contents)

    current_user.profile_picture = f"/static/avatars/{filename}"
    db.commit()
    db.refresh(current_user)
    return current_user


# ── Security — OTP flow ───────────────────────────────────────────────────────

@router.post("/security/request-otp")
def request_otp(current_user: User = Depends(get_current_user)):
    """Step 1: Generate OTP and email it. Valid for 10 minutes."""
    from datetime import datetime, timedelta, timezone

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
        raise HTTPException(
            status_code=500,
            detail="Failed to send OTP email. Check SMTP settings in .env",
        ) from exc

    return {"message": f"OTP sent to {current_user.email}. Valid for 10 minutes."}


@router.post("/security/verify-otp")
def verify_otp(
    payload: PasswordResetVerify,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Step 2: Verify OTP and set new password in a single call."""
    from datetime import datetime, timezone

    record = _otp_store.get(current_user.id)

    if not record:
        raise HTTPException(
            status_code=400,
            detail="No OTP found. Please request a new code first.",
        )

    if datetime.now(timezone.utc) > record["expires_at"]:
        _otp_store.pop(current_user.id, None)
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
        raise HTTPException(status_code=422, detail="Passwords do not match")

    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    _otp_store.pop(current_user.id, None)
    return {"message": "Password changed successfully"}


@router.post("/security/change-password")
def change_password(
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Direct change — requires current password (no OTP needed)."""
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=422, detail="Passwords do not match")

    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return {"message": "Password updated successfully"}


# ── Notifications ─────────────────────────────────────────────────────────────

@router.patch("/notifications", response_model=UserProfileOut)
def update_notification_prefs(
    payload: NotificationPrefsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toggle email_digests and push_alerts preferences."""
    if payload.email_digests is not None:
        current_user.email_digests = payload.email_digests
    if payload.push_alerts is not None:
        current_user.push_alerts = payload.push_alerts
    db.commit()
    db.refresh(current_user)
    return current_user
