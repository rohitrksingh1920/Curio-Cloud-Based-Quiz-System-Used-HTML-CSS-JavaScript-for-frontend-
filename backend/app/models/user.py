




from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from backend.app.core.database import Base


class UserRole(str, enum.Enum):
    admin   = "admin"
    teacher = "teacher"
    student = "student"


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    full_name       = Column(String(100), nullable=False)
    email           = Column(String(150), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role            = Column(Enum(UserRole), default=UserRole.student, nullable=False)
    is_active       = Column(Boolean, default=True)
    profile_picture = Column(String(500), nullable=True)

    # Notification preferences
    email_digests = Column(Boolean, default=True)
    push_alerts   = Column(Boolean, default=False)

    # App preferences
    dark_mode        = Column(Boolean, default=False)
    display_language = Column(String(20), default="English")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    quizzes        = relationship("Quiz",           back_populates="creator",  cascade="all, delete-orphan")
    quiz_attempts  = relationship("QuizAttempt",    back_populates="user",     cascade="all, delete-orphan")
    notifications  = relationship("Notification",   back_populates="user",     cascade="all, delete-orphan")
    # ── NEW: quizzes this student is enrolled in ───────────────────────────
    enrollments    = relationship("QuizEnrollment", back_populates="user",     cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User id={self.id} email={self.email} role={self.role}>"
