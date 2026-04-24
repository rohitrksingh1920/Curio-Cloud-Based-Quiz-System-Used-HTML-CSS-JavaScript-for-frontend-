

from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime

from backend.app.models.user import UserRole
from backend.app.models.notification import NotificationType


# ── Quiz Attempt ──────────────────────────────────────────────────────────────

class SubmitAnswerItem(BaseModel):
    question_id: int
    selected_option_id: int


class AttemptSubmit(BaseModel):
    answers: List[SubmitAnswerItem]

    @field_validator("answers")
    @classmethod
    def answers_not_empty(cls, v):
        if not v:
            raise ValueError("answers list cannot be empty")
        return v


class AttemptResult(BaseModel):
    attempt_id: int
    quiz_title: str
    score: float
    score_pct: float
    total_points: int
    correct_count: int
    total_questions: int
    passed: bool
    completed_at: datetime
    model_config = {"from_attributes": True}


# ── Enrollment ────────────────────────────────────────────────────────────────

class EnrollRequest(BaseModel):
    """Body for POST /api/quizzes/{id}/enroll"""
    user_ids: List[int]

    @field_validator("user_ids")
    @classmethod
    def must_not_be_empty(cls, v):
        if not v:
            raise ValueError("user_ids must not be empty")
        # Deduplicate while preserving order
        seen: set = set()
        deduped = []
        for uid in v:
            if uid not in seen:
                seen.add(uid)
                deduped.append(uid)
        if len(deduped) > 500:
            raise ValueError("Cannot enroll more than 500 students at once")
        return deduped


class EnrollResponse(BaseModel):
    enrolled: List[int]
    already_enrolled: List[int]
    not_found: List[int]
    message: str


# ── Dashboard ─────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_quizzes:      int
    total_participants: int
    avg_score:          float


# ── Analytics ─────────────────────────────────────────────────────────────────

class ScoreTrendPoint(BaseModel):
    date:      str
    score_pct: float


class SubjectPerformance(BaseModel):
    category:  str
    avg_score: float


class AnalyticsSummary(BaseModel):
    avg_score:           float
    quizzes_taken:       int
    pass_rate:           float
    total_points:        int
    score_trend:         List[ScoreTrendPoint]
    subject_performance: List[SubjectPerformance]


# ── Leaderboard ───────────────────────────────────────────────────────────────

class LeaderboardEntry(BaseModel):
    rank:            int
    user_id:         int
    full_name:       str
    profile_picture: Optional[str] = None
    score_pct:       float
    score:           float
    correct_count:   int
    total_questions: int
    completed_at:    datetime
    is_current_user: bool = False
    model_config = {"from_attributes": True}


class LeaderboardResponse(BaseModel):
    quiz_id:           int
    quiz_title:        str
    total_participants: int
    entries:           List[LeaderboardEntry]
    current_user_rank: Optional[int] = None


# ── User / Settings ───────────────────────────────────────────────────────────

class UserProfileUpdate(BaseModel):
    full_name:        Optional[str]  = None
    dark_mode:        Optional[bool] = None
    display_language: Optional[str]  = None

    @field_validator("full_name")
    @classmethod
    def name_not_blank(cls, v):
        if v is not None and not v.strip():
            raise ValueError("Full name cannot be blank")
        return v.strip() if v else v


class UserProfileOut(BaseModel):
    id:               int
    full_name:        str
    email:            str
    role:             UserRole
    dark_mode:        bool
    display_language: str
    email_digests:    bool
    push_alerts:      bool
    profile_picture:  Optional[str] = None
    created_at:       datetime
    model_config = {"from_attributes": True}


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password:     str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def pw_len(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v, info):
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match")
        return v


class PasswordResetVerify(BaseModel):
    otp:              str
    new_password:     str
    confirm_password: str

    @field_validator("otp")
    @classmethod
    def otp_digits(cls, v):
        v = v.strip()
        if len(v) != 6 or not v.isdigit():
            raise ValueError("OTP must be exactly 6 digits")
        return v

    @field_validator("new_password")
    @classmethod
    def pw_len(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v, info):
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match")
        return v


class NotificationPrefsUpdate(BaseModel):
    email_digests: Optional[bool] = None
    push_alerts:   Optional[bool] = None


# ── Notifications ─────────────────────────────────────────────────────────────

class NotificationOut(BaseModel):
    id:         int
    type:       NotificationType
    title:      str
    message:    str
    is_read:    bool
    created_at: datetime
    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    total:         int
    unread_count:  int
    notifications: List[NotificationOut]
