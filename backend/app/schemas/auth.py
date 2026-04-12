
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime
from backend.app.models.user import UserRole


class SignupRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("full_name")
    @classmethod
    def name_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Full name cannot be empty")
        return v.strip()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    """Step 1: user provides their registered email to receive an OTP."""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Step 2: user provides email + OTP they received + new password."""
    email: EmailStr
    otp: str
    new_password: str
    confirm_password: str

    @field_validator("otp")
    @classmethod
    def otp_is_digits(cls, v):
        v = v.strip()
        if len(v) != 6 or not v.isdigit():
            raise ValueError("OTP must be exactly 6 digits")
        return v

    @field_validator("new_password")
    @classmethod
    def pw_min_length(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    id: int
    full_name: str
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    # Preference fields needed by frontend Theme.apply() and localStorage
    dark_mode: bool = False
    display_language: str = "English"
    email_digests: bool = True
    push_alerts: bool = False
    profile_picture: Optional[str] = None

    model_config = {"from_attributes": True}


TokenResponse.model_rebuild()
