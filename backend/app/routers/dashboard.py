

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user
from backend.app.models.user import User
from backend.app.models.quiz import Quiz, QuizStatus
from backend.app.models.attempt import QuizAttempt
from backend.app.schemas.misc import DashboardStats
from backend.app.schemas.quiz import QuizSummary

# FIX: was APIRouter() with no prefix → endpoints landed at /stats, /upcoming-quizzes etc.
# Frontend calls /api/dashboard/stats, /api/dashboard/upcoming-quizzes etc.
router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


#  Stats 

@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregate stats shown on the dashboard header cards."""
    total_quizzes = db.query(func.count(Quiz.id)).filter(
        Quiz.creator_id == current_user.id
    ).scalar() or 0

    total_participants = (
        db.query(func.count(QuizAttempt.user_id.distinct()))
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .filter(Quiz.creator_id == current_user.id)
        .scalar() or 0
    )

    avg_score_result = (
        db.query(func.avg(QuizAttempt.score_pct))
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .filter(
            Quiz.creator_id == current_user.id,
            QuizAttempt.is_completed == True,
        )
        .scalar()
    )
    avg_score = round(float(avg_score_result), 1) if avg_score_result else 0.0

    return DashboardStats(
        total_quizzes=total_quizzes,
        total_participants=total_participants,
        avg_score=avg_score,
    )


#  Upcoming Quizzes 

@router.get("/upcoming-quizzes", response_model=list[QuizSummary])
def get_upcoming_quizzes(
    limit: int = 6,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Quizzes whose scheduled datetime is in the FUTURE
    AND have NOT been completed by this user.
    Shows ALL quizzes (not just ones the user created).
    """
    now = datetime.now(timezone.utc)

    completed_quiz_ids = {
        row.quiz_id
        for row in db.query(QuizAttempt.quiz_id)
        .filter(
            QuizAttempt.user_id == current_user.id,
            QuizAttempt.is_completed == True,
        )
        .all()
    }

    # FIX: removed  .filter(Quiz.creator_id == current_user.id)
    # so all quizzes (including those created by others) are visible
    all_quizzes = db.query(Quiz).all()

    upcoming = []
    for quiz in all_quizzes:
        if not quiz.scheduled_date:
            continue
        quiz_datetime = datetime.combine(
            quiz.scheduled_date,
            quiz.scheduled_time or datetime.min.time(),
        ).replace(tzinfo=timezone.utc)
        if now < quiz_datetime and quiz.id not in completed_quiz_ids:
            upcoming.append(quiz)

    upcoming.sort(
        key=lambda q: datetime.combine(
            q.scheduled_date,
            q.scheduled_time or datetime.min.time(),
        )
    )

    return [_to_quiz_summary(q, current_user.id) for q in upcoming[:limit]]


#  Active Quizzes 

@router.get("/active-quizzes", response_model=list[QuizSummary])
def get_active_quizzes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Quizzes available to take right now:
      - scheduled datetime is in the past (or no date = always active)
      - AND have NOT been completed by this user
    Shows ALL quizzes (not just ones the user created).
    """
    now = datetime.now(timezone.utc)

    completed_quiz_ids = {
        row.quiz_id
        for row in db.query(QuizAttempt.quiz_id)
        .filter(
            QuizAttempt.user_id == current_user.id,
            QuizAttempt.is_completed == True,
        )
        .all()
    }

    # FIX: removed creator_id filter so students see all active quizzes
    all_quizzes = db.query(Quiz).all()

    active = []
    for quiz in all_quizzes:
        if quiz.id in completed_quiz_ids:
            continue
        if quiz.scheduled_date:
            quiz_datetime = datetime.combine(
                quiz.scheduled_date,
                quiz.scheduled_time or datetime.min.time(),
            ).replace(tzinfo=timezone.utc)
            if now >= quiz_datetime:
                active.append(quiz)
        else:
            active.append(quiz)

    return [_to_quiz_summary(q, current_user.id) for q in active]


#  Shared helper 

def _to_quiz_summary(quiz: Quiz, current_user_id: int) -> QuizSummary:
    now = datetime.now(timezone.utc)

    quiz_datetime = None
    if quiz.scheduled_date:
        quiz_datetime = datetime.combine(
            quiz.scheduled_date,
            quiz.scheduled_time or datetime.min.time(),
        ).replace(tzinfo=timezone.utc)

    user_attempt = next(
        (a for a in (quiz.attempts or []) if a.user_id == current_user_id and a.is_completed),
        None,
    )

    if user_attempt:
        computed_status = QuizStatus.completed
    elif quiz_datetime and now < quiz_datetime:
        computed_status = QuizStatus.upcoming
    else:
        computed_status = QuizStatus.active

    return QuizSummary(
        id=quiz.id,
        title=quiz.title,
        category=quiz.category,
        status=computed_status,
        duration_mins=quiz.duration_mins,
        total_points=quiz.total_points,
        scheduled_date=quiz.scheduled_date,
        scheduled_time=quiz.scheduled_time,
        enrolled_count=len(quiz.attempts or []),
        creator_name=quiz.creator.full_name if quiz.creator else "Unknown",
        created_at=quiz.created_at,
        is_attempted=bool(user_attempt),
    )
