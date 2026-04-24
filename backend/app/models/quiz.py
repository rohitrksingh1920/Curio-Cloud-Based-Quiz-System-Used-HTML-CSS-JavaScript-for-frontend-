


from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey,
    Float, Text, Enum, Date, Time, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from backend.app.core.database import Base


class QuizStatus(str, enum.Enum):
    draft     = "draft"
    upcoming  = "upcoming"
    active    = "active"
    completed = "completed"


class QuizCategory(str, enum.Enum):
    computer_science = "Computer Science"
    mathematics      = "Mathematics"
    history          = "History"
    science          = "Science"
    geography        = "Geography"
    english          = "English"
    other            = "Other"


class Quiz(Base):
    __tablename__ = "quizzes"

    id             = Column(Integer, primary_key=True, index=True)
    title          = Column(String(200), nullable=False)
    category       = Column(Enum(QuizCategory), nullable=False)
    duration_mins  = Column(Integer, default=30)
    total_points   = Column(Integer, default=100)
    scheduled_date = Column(Date, nullable=True)
    scheduled_time = Column(Time, nullable=True)
    status         = Column(Enum(QuizStatus), default=QuizStatus.upcoming)
    creator_id     = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    creator     = relationship("User", back_populates="quizzes")
    questions   = relationship("Question",       back_populates="quiz", cascade="all, delete-orphan")
    attempts    = relationship("QuizAttempt",    back_populates="quiz", cascade="all, delete-orphan")
    # ── NEW: explicit enrollment records ───────────────────────────────────
    enrollments = relationship("QuizEnrollment", back_populates="quiz", cascade="all, delete-orphan")

    @property
    def enrolled_count(self):
        return len(self.enrollments)

    def __repr__(self):
        return f"<Quiz id={self.id} title={self.title}>"


class QuizEnrollment(Base):
    """
    Explicit assignment of a student to a quiz.
    Only students with a matching row here can see/attempt the quiz.
    Created by admin or teacher via POST /api/quizzes/{id}/enroll.
    """
    __tablename__ = "quiz_enrollments"
    __table_args__ = (UniqueConstraint("quiz_id", "user_id", name="uq_enrollment"),)

    id         = Column(Integer, primary_key=True, index=True)
    quiz_id    = Column(Integer, ForeignKey("quizzes.id",  ondelete="CASCADE"), nullable=False)
    user_id    = Column(Integer, ForeignKey("users.id",    ondelete="CASCADE"), nullable=False)
    enrolled_at = Column(DateTime(timezone=True), server_default=func.now())

    quiz = relationship("Quiz", back_populates="enrollments")
    user = relationship("User", back_populates="enrollments")

    def __repr__(self):
        return f"<Enrollment quiz={self.quiz_id} user={self.user_id}>"


class Question(Base):
    __tablename__ = "questions"

    id      = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False)
    text    = Column(Text, nullable=False)
    order   = Column(Integer, default=1)

    quiz    = relationship("Quiz",           back_populates="questions")
    options = relationship("QuestionOption", back_populates="question", cascade="all, delete-orphan")
    answers = relationship("AttemptAnswer",  back_populates="question")

    def __repr__(self):
        return f"<Question id={self.id} quiz_id={self.quiz_id}>"


class QuestionOption(Base):
    __tablename__ = "question_options"

    id          = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    text        = Column(String(500), nullable=False)
    is_correct  = Column(Boolean, default=False)
    order       = Column(Integer, default=1)

    question = relationship("Question", back_populates="options")

    def __repr__(self):
        return f"<Option id={self.id} correct={self.is_correct}>"
