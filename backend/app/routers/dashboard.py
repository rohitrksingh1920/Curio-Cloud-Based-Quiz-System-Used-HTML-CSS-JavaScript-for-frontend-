


from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user
from backend.app.models.user import User, UserRole
from backend.app.models.quiz import Quiz, QuizStatus, QuizEnrollment
from backend.app.models.attempt import QuizAttempt
from backend.app.schemas.misc import DashboardStats
from backend.app.schemas.quiz import QuizSummary

router = APIRouter()


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role in (UserRole.admin, UserRole.teacher):
        # Stats for quizzes this teacher created
        total_quizzes = db.query(func.count(Quiz.id)).filter(
            Quiz.creator_id == current_user.id
        ).scalar() or 0

        total_participants = (
            db.query(func.count(QuizAttempt.user_id.distinct()))
            .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
            .filter(Quiz.creator_id == current_user.id)
            .scalar() or 0
        )

        avg_result = (
            db.query(func.avg(QuizAttempt.score_pct))
            .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
            .filter(Quiz.creator_id == current_user.id, QuizAttempt.is_completed == True)
            .scalar()
        )
        avg_score = round(float(avg_result), 1) if avg_result else 0.0
    else:
        # Stats for student: enrolled quizzes + their own scores
        enrolled_ids = [e.quiz_id for e in db.query(QuizEnrollment).filter(
            QuizEnrollment.user_id == current_user.id
        ).all()]

        total_quizzes = len(enrolled_ids)
        total_participants = 0  # not meaningful for students

        avg_result = (
            db.query(func.avg(QuizAttempt.score_pct))
            .filter(
                QuizAttempt.user_id == current_user.id,
                QuizAttempt.is_completed == True,
            )
            .scalar()
        )
        avg_score = round(float(avg_result), 1) if avg_result else 0.0

    return DashboardStats(
        total_quizzes=total_quizzes,
        total_participants=total_participants,
        avg_score=avg_score,
    )


@router.get("/upcoming-quizzes", response_model=list[QuizSummary])
def get_upcoming_quizzes(
    limit: int = 6,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    completed_ids = {
        r.quiz_id for r in db.query(QuizAttempt.quiz_id).filter(
            QuizAttempt.user_id == current_user.id,
            QuizAttempt.is_completed == True,
        ).all()
    }

    if current_user.role in (UserRole.admin, UserRole.teacher):
        all_quizzes = db.query(Quiz).filter(Quiz.creator_id == current_user.id).all()
    else:
        enrolled_ids = [e.quiz_id for e in db.query(QuizEnrollment).filter(
            QuizEnrollment.user_id == current_user.id
        ).all()]
        all_quizzes = db.query(Quiz).filter(Quiz.id.in_(enrolled_ids)).all()

    upcoming = []
    for quiz in all_quizzes:
        if not quiz.scheduled_date or quiz.id in completed_ids:
            continue
        quiz_dt = datetime.combine(
            quiz.scheduled_date,
            quiz.scheduled_time or datetime.min.time(),
        ).replace(tzinfo=timezone.utc)
        if now < quiz_dt:
            upcoming.append(quiz)

    upcoming.sort(key=lambda q: datetime.combine(
        q.scheduled_date, q.scheduled_time or datetime.min.time()
    ))
    return [_to_quiz_summary(q, current_user.id) for q in upcoming[:limit]]


@router.get("/active-quizzes", response_model=list[QuizSummary])
def get_active_quizzes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    completed_ids = {
        r.quiz_id for r in db.query(QuizAttempt.quiz_id).filter(
            QuizAttempt.user_id == current_user.id,
            QuizAttempt.is_completed == True,
        ).all()
    }

    if current_user.role in (UserRole.admin, UserRole.teacher):
        all_quizzes = db.query(Quiz).filter(Quiz.creator_id == current_user.id).all()
    else:
        enrolled_ids = [e.quiz_id for e in db.query(QuizEnrollment).filter(
            QuizEnrollment.user_id == current_user.id
        ).all()]
        all_quizzes = db.query(Quiz).filter(Quiz.id.in_(enrolled_ids)).all()

    active = []
    for quiz in all_quizzes:
        if quiz.id in completed_ids:
            continue
        if quiz.scheduled_date:
            quiz_dt = datetime.combine(
                quiz.scheduled_date,
                quiz.scheduled_time or datetime.min.time(),
            ).replace(tzinfo=timezone.utc)
            if now >= quiz_dt:
                active.append(quiz)
        else:
            active.append(quiz)

    return [_to_quiz_summary(q, current_user.id) for q in active]


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
        id=quiz.id, title=quiz.title, category=quiz.category,
        status=computed_status, duration_mins=quiz.duration_mins,
        total_points=quiz.total_points, scheduled_date=quiz.scheduled_date,
        scheduled_time=quiz.scheduled_time,
        enrolled_count=len(quiz.enrollments or []),
        creator_name=quiz.creator.full_name if quiz.creator else "Unknown",
        created_at=quiz.created_at, is_attempted=bool(user_attempt),
    )
