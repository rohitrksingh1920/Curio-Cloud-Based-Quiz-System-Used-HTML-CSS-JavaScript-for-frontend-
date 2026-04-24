




from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import date, time, datetime
from backend.app.models.quiz import QuizStatus, QuizCategory


#  Option Schemas 

class OptionCreate(BaseModel):
    text: str
    is_correct: bool = False
    order: int = 1


class OptionOut(BaseModel):
    id: int
    text: str
    is_correct: bool
    order: int
    model_config = {"from_attributes": True}


class OptionOutPublic(BaseModel):
    """Option without revealing the correct answer (for students taking quiz)."""
    id: int
    text: str
    order: int
    model_config = {"from_attributes": True}


#  Question Schemas 

class QuestionCreate(BaseModel):
    text: str
    order: int = 1
    options: List[OptionCreate]

    @field_validator("options")
    @classmethod
    def must_have_one_correct(cls, v):
        correct = [o for o in v if o.is_correct]
        if len(correct) == 0:
            raise ValueError("Each question must have exactly one correct option")
        if len(correct) > 1:
            raise ValueError("Only one option can be marked as correct")
        if len(v) < 2:
            raise ValueError("Each question must have at least 2 options")
        return v


class QuestionOut(BaseModel):
    id: int
    text: str
    order: int
    options: List[OptionOut]
    model_config = {"from_attributes": True}


class QuestionOutPublic(BaseModel):
    id: int
    text: str
    order: int
    options: List[OptionOutPublic]
    model_config = {"from_attributes": True}


#  Quiz Schemas 

class QuizCreate(BaseModel):
    title: str
    category: QuizCategory
    duration_mins: int = 30
    total_points: int = 100
    scheduled_date: Optional[date] = None
    scheduled_time: Optional[time] = None
    questions: List[QuestionCreate]

    student_ids: Optional[List[int]] = []

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Quiz title cannot be empty")
        return v.strip()

    @field_validator("questions")
    @classmethod
    def must_have_questions(cls, v):
        if len(v) == 0:
            raise ValueError("A quiz must have at least one question")
        return v


class QuizUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[QuizCategory] = None
    duration_mins: Optional[int] = None
    total_points: Optional[int] = None
    scheduled_date: Optional[date] = None
    scheduled_time: Optional[time] = None
    status: Optional[QuizStatus] = None


class QuizSummary(BaseModel):
    """Lightweight card view used in dashboard / my-quizzes."""
    id: int
    title: str
    category: QuizCategory
    status: QuizStatus
    duration_mins: int
    total_points: int
    scheduled_date: Optional[date] = None
    scheduled_time: Optional[time] = None
    enrolled_count: int
    creator_name: str
    created_at: datetime
    is_attempted: bool = False      
    model_config = {"from_attributes": True}


class QuizDetail(BaseModel):
    """Full quiz with questions — used by creator/admin."""
    id: int
    title: str
    category: QuizCategory
    status: QuizStatus
    duration_mins: int
    total_points: int
    scheduled_date: Optional[date] = None
    scheduled_time: Optional[time] = None
    enrolled_count: int
    creator_name: str
    created_at: datetime
    questions: list
    model_config = {"from_attributes": True}


class QuizPublic(BaseModel):
    """Quiz visible to a student while taking it — no correct answers."""
    id: int
    title: str
    category: QuizCategory
    duration_mins: int
    total_points: int
    questions: list
    model_config = {"from_attributes": True}
