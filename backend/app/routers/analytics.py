


from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from collections import defaultdict

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user
from backend.app.models.user import User
from backend.app.models.quiz import Quiz
from backend.app.models.attempt import QuizAttempt
from backend.app.schemas.misc import AnalyticsSummary, ScoreTrendPoint, SubjectPerformance

router = APIRouter()


@router.get("", response_model=AnalyticsSummary)
def get_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return full analytics for the authenticated user's quiz activity."""

    completed_attempts = (
        db.query(QuizAttempt)
        .filter(
            QuizAttempt.user_id == current_user.id,
            QuizAttempt.is_completed == True,
        )
        .order_by(QuizAttempt.completed_at.asc())
        .all()
    )

    quizzes_taken = len(completed_attempts)

    if quizzes_taken == 0:
        return AnalyticsSummary(
            avg_score=0.0,
            quizzes_taken=0,
            pass_rate=0.0,
            total_points=0,
            score_trend=[],
            subject_performance=[],
        )

    scores = [a.score_pct for a in completed_attempts if a.score_pct is not None]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
    passed = sum(1 for s in scores if s >= 60)
    pass_rate = round((passed / len(scores)) * 100, 1) if scores else 0.0
    total_points = sum(
        int(a.score or 0) for a in completed_attempts
    )

    # Score trend: group by date (use completed_at date)
    trend_map: dict[str, list[float]] = defaultdict(list)
    for attempt in completed_attempts:
        if attempt.completed_at and attempt.score_pct is not None:
            date_key = attempt.completed_at.strftime("%Y-%m-%d")
            trend_map[date_key].append(attempt.score_pct)

    score_trend = [
        ScoreTrendPoint(
            date=d,
            score_pct=round(sum(vals) / len(vals), 1),
        )
        for d, vals in sorted(trend_map.items())
    ]

    # Subject performance: avg score per category
    category_map: dict[str, list[float]] = defaultdict(list)
    for attempt in completed_attempts:
        if attempt.score_pct is not None:
            cat = attempt.quiz.category.value if attempt.quiz else "Other"
            category_map[cat].append(attempt.score_pct)

    subject_performance = [
        SubjectPerformance(
            category=cat,
            avg_score=round(sum(vals) / len(vals), 1),
        )
        for cat, vals in sorted(category_map.items())
    ]

    return AnalyticsSummary(
        avg_score=avg_score,
        quizzes_taken=quizzes_taken,
        pass_rate=pass_rate,
        total_points=total_points,
        score_trend=score_trend,
        subject_performance=subject_performance,
    )
