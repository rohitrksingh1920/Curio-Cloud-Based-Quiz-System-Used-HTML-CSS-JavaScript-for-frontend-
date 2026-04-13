




from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone, timedelta

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user
from backend.app.models.user import User
from backend.app.models.quiz import Quiz, Question, QuestionOption, QuizStatus, QuizCategory
from backend.app.models.attempt import QuizAttempt, AttemptAnswer
from backend.app.models.notification import Notification, NotificationType
from backend.app.schemas.quiz import (
    QuizCreate, QuizUpdate, QuizSummary, QuizDetail, QuizPublic
)
from backend.app.schemas.misc import AttemptSubmit, AttemptResult

router = APIRouter(prefix="/api/quizzes", tags=["Quiz"])


#  Create 

@router.post("", response_model=QuizDetail, status_code=status.HTTP_201_CREATED)
def create_quiz(
    payload: QuizCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new quiz with questions and options."""
    new_quiz = Quiz(
        title=payload.title,
        category=payload.category,
        duration_mins=payload.duration_mins,
        total_points=payload.total_points,
        scheduled_date=payload.scheduled_date,
        scheduled_time=payload.scheduled_time,
        status=QuizStatus.upcoming if payload.scheduled_date else QuizStatus.active,
        creator_id=current_user.id,
    )
    db.add(new_quiz)
    db.flush()

    for q_data in payload.questions:
        question = Question(
            quiz_id=new_quiz.id,
            text=q_data.text,
            order=q_data.order,
        )
        db.add(question)
        db.flush()

        for opt_data in q_data.options:
            option = QuestionOption(
                question_id=question.id,
                text=opt_data.text,
                is_correct=opt_data.is_correct,
                order=opt_data.order,
            )
            db.add(option)

    db.commit()
    db.refresh(new_quiz)
    return _to_quiz_detail(new_quiz)


#  List / Filter 
# FIX 1: Changed @router.get("/") to @router.get("") to remove trailing slash.
# The old "/" caused FastAPI to issue a 307 redirect for requests to /api/quizzes
# which stripped the Authorization header, causing silent 401s and empty lists.
#
# FIX 2: Now returns ALL quizzes (not just creator's) so students see quizzes too.
# Quizzes created by others are shown only if not yet completed by this user.

@router.get("", response_model=list[QuizSummary])
def list_my_quizzes(
    search: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return all quizzes visible to the current user.
    - Quizzes they CREATED (always shown)
    - Quizzes created by others (shown so students can see them too)
    Status is computed in real-time from scheduled datetime + attempt state.
    Optional ?status= filter applies after computing status.
    """
    query = db.query(Quiz)

    if search:
        term = f"%{search.lower()}%"
        query = query.filter(
            Quiz.title.ilike(term) | Quiz.category.ilike(term)
        )

    quizzes   = query.order_by(Quiz.created_at.desc()).all()
    summaries = [_to_quiz_summary(q, current_user.id) for q in quizzes]

    if status_filter:
        summaries = [s for s in summaries if s.status.value == status_filter.lower()]

    return summaries


#  Get Single 

@router.get("/{quiz_id}", response_model=QuizDetail)
def get_quiz(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get full quiz detail (creator only)."""
    quiz = _get_quiz_or_404(quiz_id, db)
    if quiz.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your quiz")
    return _to_quiz_detail(quiz)


#  Take Quiz 

@router.get("/{quiz_id}/take", response_model=QuizPublic)
def take_quiz(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return quiz questions for a student to answer.
    Blocks if: quiz hasn't started yet, or user already completed it.
    Auto-closes timed-out incomplete attempts.
    """
    quiz = _get_quiz_or_404(quiz_id, db)
    now  = datetime.now(timezone.utc)

    quiz_datetime = None
    if quiz.scheduled_date:
        quiz_datetime = datetime.combine(
            quiz.scheduled_date,
            quiz.scheduled_time or datetime.min.time(),
        ).replace(tzinfo=timezone.utc)

    if quiz_datetime and now < quiz_datetime:
        raise HTTPException(
            status_code=403,
            detail=f"Quiz not yet available. Starts at {quiz_datetime.isoformat()}",
        )

    existing_attempt = (
        db.query(QuizAttempt)
        .filter(QuizAttempt.user_id == current_user.id, QuizAttempt.quiz_id == quiz.id)
        .order_by(QuizAttempt.started_at.desc())
        .first()
    )

    if existing_attempt:
        if existing_attempt.is_completed:
            raise HTTPException(status_code=400, detail="You have already completed this quiz")

        end_time = existing_attempt.started_at + timedelta(minutes=quiz.duration_mins)
        if now > end_time:
            existing_attempt.is_completed = True
            existing_attempt.completed_at = now
            db.commit()
            raise HTTPException(
                status_code=400,
                detail="Your previous attempt timed out and has been closed",
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="You already have an active attempt for this quiz",
            )

    attempt = QuizAttempt(user_id=current_user.id, quiz_id=quiz.id, started_at=now)
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    return QuizPublic(
        id=quiz.id,
        title=quiz.title,
        category=quiz.category,
        duration_mins=quiz.duration_mins,
        total_points=quiz.total_points,
        questions=[
            {
                "id": q.id,
                "text": q.text,
                "order": q.order,
                "options": [
                    {"id": o.id, "text": o.text, "order": o.order}
                    for o in sorted(q.options, key=lambda x: x.order)
                ],
            }
            for q in sorted(quiz.questions, key=lambda x: x.order)
        ],
    )


#  Submit Attempt 

@router.post("/{quiz_id}/submit", response_model=AttemptResult)
def submit_quiz(
    quiz_id: int,
    payload: AttemptSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit answers and receive the scored result."""
    quiz = _get_quiz_or_404(quiz_id, db)

    attempt = (
        db.query(QuizAttempt)
        .filter(
            QuizAttempt.user_id == current_user.id,
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.is_completed == False,
        )
        .order_by(QuizAttempt.started_at.desc())
        .first()
    )

    if not attempt:
        raise HTTPException(
            status_code=400,
            detail="No active attempt found. You may have already submitted.",
        )

    now = datetime.now(timezone.utc)

    correct_map: dict[int, int] = {}
    for q in quiz.questions:
        for opt in q.options:
            if opt.is_correct:
                correct_map[q.id] = opt.id

    correct_count = 0
    for ans in payload.answers:
        is_correct = correct_map.get(ans.question_id) == ans.selected_option_id
        if is_correct:
            correct_count += 1
        db.add(AttemptAnswer(
            attempt_id=attempt.id,
            question_id=ans.question_id,
            selected_option_id=ans.selected_option_id,
            is_correct=is_correct,
        ))

    total_questions = len(quiz.questions)
    score_pct = round((correct_count / total_questions) * 100, 2) if total_questions else 0
    raw_score = round((score_pct / 100) * quiz.total_points, 2)
    passed    = score_pct >= 60

    attempt.score        = raw_score
    attempt.score_pct    = score_pct
    attempt.is_completed = True
    attempt.completed_at = now

    if score_pct == 100:
        db.add(Notification(
            user_id=current_user.id,
            type=NotificationType.achievement,
            title="🏆 Perfect Score!",
            message=f"You scored 100% on '{quiz.title}'. Outstanding!",
        ))

    db.commit()
    db.refresh(attempt)

    return AttemptResult(
        attempt_id=attempt.id,
        quiz_title=quiz.title,
        score=raw_score,
        score_pct=score_pct,
        total_points=quiz.total_points,
        correct_count=correct_count,
        total_questions=total_questions,
        passed=passed,
        completed_at=attempt.completed_at,
    )


#  Update 

@router.patch("/{quiz_id}", response_model=QuizSummary)
def update_quiz(
    quiz_id: int,
    payload: QuizUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    quiz = _get_quiz_or_404(quiz_id, db)
    if quiz.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your quiz")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(quiz, field, value)

    db.commit()
    db.refresh(quiz)
    return _to_quiz_summary(quiz, current_user.id)


#  Delete 

@router.delete("/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quiz(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    quiz = _get_quiz_or_404(quiz_id, db)
    if quiz.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your quiz")

    db.delete(quiz)
    db.commit()


#  Internal helpers 

def _get_quiz_or_404(quiz_id: int, db: Session) -> Quiz:
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return quiz


def _to_quiz_summary(quiz: Quiz, current_user_id: int) -> QuizSummary:
    """
    Compute real-time status:
      1. User has a completed attempt  → completed
      2. Scheduled datetime is future  → upcoming
      3. Anything else                 → active
    """
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


def _to_quiz_detail(quiz: Quiz) -> QuizDetail:
    return QuizDetail(
        id=quiz.id,
        title=quiz.title,
        category=quiz.category,
        status=quiz.status,
        duration_mins=quiz.duration_mins,
        total_points=quiz.total_points,
        scheduled_date=quiz.scheduled_date,
        scheduled_time=quiz.scheduled_time,
        enrolled_count=len(quiz.attempts or []),
        creator_name=quiz.creator.full_name if quiz.creator else "Unknown",
        created_at=quiz.created_at,
        questions=[
            {
                "id": q.id,
                "text": q.text,
                "order": q.order,
                "options": [
                    {"id": o.id, "text": o.text, "is_correct": o.is_correct, "order": o.order}
                    for o in sorted(q.options, key=lambda x: x.order)
                ],
            }
            for q in sorted(quiz.questions, key=lambda x: x.order)
        ],
    )
