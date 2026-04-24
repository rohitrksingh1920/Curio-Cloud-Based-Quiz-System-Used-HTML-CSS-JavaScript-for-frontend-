



from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user
from backend.app.models.user import User
from backend.app.models.quiz import Quiz
from backend.app.models.attempt import QuizAttempt, AttemptAnswer
from backend.app.schemas.misc import LeaderboardResponse, LeaderboardEntry

router = APIRouter()


@router.get("/{quiz_id}", response_model=LeaderboardResponse)
def get_leaderboard(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return ranked leaderboard for a quiz.
    Ranked by: highest score_pct DESC, then earliest completed_at ASC.
    """
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    # Best attempt per user
    best_subq = (
        db.query(
            QuizAttempt.user_id,
            func.max(QuizAttempt.score_pct).label("best_pct"),
        )
        .filter(QuizAttempt.quiz_id == quiz_id, QuizAttempt.is_completed == True)
        .group_by(QuizAttempt.user_id)
        .subquery()
    )

    attempts = (
        db.query(QuizAttempt)
        .join(
            best_subq,
            (QuizAttempt.user_id == best_subq.c.user_id)
            & (QuizAttempt.score_pct == best_subq.c.best_pct),
        )
        .filter(QuizAttempt.quiz_id == quiz_id, QuizAttempt.is_completed == True)
        .order_by(QuizAttempt.score_pct.desc(), QuizAttempt.completed_at.asc())
        .all()
    )

    if not attempts:
        return LeaderboardResponse(
            quiz_id=quiz_id,
            quiz_title=quiz.title,
            total_participants=0,
            entries=[],
            current_user_rank=None,
        )

    total_questions = len(quiz.questions)
    attempt_ids     = [a.id for a in attempts]

    correct_rows = (
        db.query(AttemptAnswer.attempt_id, func.count(AttemptAnswer.id))
        .filter(
            AttemptAnswer.attempt_id.in_(attempt_ids),
            AttemptAnswer.is_correct == True,
        )
        .group_by(AttemptAnswer.attempt_id)
        .all()
    )
    correct_map: dict = {r[0]: r[1] for r in correct_rows}

    entries           = []
    current_user_rank = None

    for rank, attempt in enumerate(attempts, start=1):
        u     = attempt.user
        is_me = attempt.user_id == current_user.id
        if is_me:
            current_user_rank = rank

        entries.append(LeaderboardEntry(
            rank=rank,
            user_id=attempt.user_id,
            full_name=u.full_name if u else "Unknown",
            profile_picture=u.profile_picture if u else None,
            score_pct=round(attempt.score_pct or 0, 1),
            score=round(attempt.score or 0, 1),
            correct_count=correct_map.get(attempt.id, 0),
            total_questions=total_questions,
            completed_at=attempt.completed_at,
            is_current_user=is_me,
        ))

    return LeaderboardResponse(
        quiz_id=quiz_id,
        quiz_title=quiz.title,
        total_participants=len(entries),
        entries=entries,
        current_user_rank=current_user_rank,
    )
